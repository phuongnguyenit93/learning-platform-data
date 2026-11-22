# Java 10 – Mã hóa dữ liệu biểu mẫu: Quy tắc application/x-www-form-urlencoded

> **Ngữ cảnh:** Java 10 → **Mã hóa dữ liệu biểu mẫu** → **Quy tắc application/x-www-form-urlencoded**. Bài học tập trung vào quy tắc mã hóa dữ liệu form đang được sử dụng trong HTTP và Java hiện đại. Đặc biệt, các overload `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` được bổ sung từ **Java 10**; các ví dụ sử dụng **Java 17+**. Không dùng các overload một tham số phụ thuộc charset mặc định đã bị deprecated.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác định dạng `application/x-www-form-urlencoded` cho các cặp **tên trường = giá trị**.
2. Hiểu quy tắc **space → `+`**, dấu cộng thật → `%2B`, và mã hóa ký tự khác theo **byte UTF-8 → `%HH`**.
3. Phân biệt ký tự được giữ nguyên `A-Z a-z 0-9 - . _ *` với những ký tự phải escape như `~`, `&`, `=`, `%`, `/`, `?` và `#`.
4. Dùng đúng `URLEncoder.encode(value, StandardCharsets.UTF_8)` và `URLDecoder.decode(value, StandardCharsets.UTF_8)` trên Java 10+.
5. Mã hóa **từng tên và từng giá trị** trước khi ghép `&` và `=`; giải mã sau khi tách chuỗi form thành các thành phần.
6. Giữ được nhiều giá trị cho một tên trường như `tag=a&tag=b`, thay vì âm thầm ghi đè vì dùng `Map<String,String>`.
7. Phân biệt tên trường không có giá trị, tên trường với value rỗng, tên lặp lại và phần tử trống; thiết kế một chính sách parser rõ ràng.
8. Tạo một request HTTP POST với Content-Type tương ứng bằng `java.net.http.HttpClient`/`HttpRequest` và nắm rõ sự khác nhau giữa **ký tự** và **byte trên dây**.
9. Biết vì sao `URLEncoder` **không phải** API mã hóa một đường dẫn URL/URI nói chung, và vì sao không được decode hai lần.
10. Phân biệt form-urlencoded với `multipart/form-data`, JSON, URL query và các trường hợp tải file.
11. Xử lý lỗi percent escape, Unicode, encoding thống nhất, validation, giới hạn kích thước và bảo mật dữ liệu cá nhân.
12. Biên dịch, chạy và giải thích chương trình Java 17+ với kết quả có thể đối chiếu chính xác.

**Tóm tắt một câu:** `application/x-www-form-urlencoded` biểu diễn form như chuỗi `name=value&name2=value2`; hãy **UTF-8 form-encode từng thành phần đúng một lần**, dùng `+` cho dấu cách, `%2B` cho dấu cộng thật, rồi ghép dấu phân cách `=` và `&` ở giữa những thành phần đã mã hóa.

## 2. Định dạng biểu mẫu này dùng ở đâu?

Trong HTTP, một body biểu mẫu đơn giản có thể trông như sau:

~~~http
POST /search HTTP/1.1
Host: example.test
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

q=Java+10&lang=vi&tag=api&tag=http
~~~

Đây là **ví dụ cấu trúc HTTP**, không phải một request gửi thực tế; header như Content-Length sẽ do HTTP client tính trong chương trình hoàn chỉnh.

- **MIME type**: `application/x-www-form-urlencoded`.
- **Thân dữ liệu**: danh sách các cặp được ngăn bởi dấu `&`.
- **Trong mỗi cặp**: phần bên trái dấu `=` là tên trường; phần bên phải là giá trị.
- **Tên và giá trị được form-encode riêng**. Trong ví dụ `q=Java+10`, dấu `+` biểu thị dấu cách, nên giá trị được giải mã là `Java 10`.
- Có thể xuất hiện **cùng một tên trường nhiều lần** như `tag=api&tag=http`. Ứng dụng phải xác định chính sách nhận nhiều giá trị.

Đây là một encoding quen thuộc của HTML forms khi submit dữ liệu kiểu key-value. Nó cũng thường được dùng trong **query string** của URL do web form tạo ra, nhưng **không phải mọi query string trong mọi API đều có cùng quy ước parse**; cần theo hợp đồng của server/API.

### 2.1. Nó không thay thế mọi định dạng body

| Dữ liệu | Lựa chọn thường gặp | Lý do |
| --- | --- | --- |
| Form text đơn giản gồm nhiều key/value | `application/x-www-form-urlencoded` | Có quy tắc chuẩn cho khoảng trắng, delimiters và percent encoding |
| Dữ liệu JSON có cấu trúc lồng nhau | `application/json` | Biểu diễn object/array/bool/number rõ hơn |
| Upload file và text fields | `multipart/form-data` | Có phần riêng, metadata và xử lý file phù hợp |
| Truyền nội dung binary/raw bytes | MIME type phù hợp với bytes | Tránh áp form encoding lên binary |
| Search/filter dưới URL query | Query theo API/server | Có thể dùng x-www-form-urlencoded, nhưng phải kiểm tra quy ước đối tác |

Không được nhầm **cách biểu diễn** với **ngữ nghĩa nghiệp vụ**: mã hóa form không tự xác thực, loại SQL injection, bảo đảm schema hay an toàn trước script injection. Những việc ấy thuộc bước validate và xử lý dữ liệu ở server.

## 3. Quy tắc ký tự: dấu cách, dấu cộng và `%HH`

Theo `java.net.URLEncoder`, các nhóm ký tự được xử lý như sau:

| Ký tự đầu vào | Form-encoded với UTF-8 | Giải thích |
| --- | --- | --- |
| `A–Z, a–z, 0–9` | Giữ nguyên | ASCII chữ/số |
| `- . _ *` | Giữ nguyên | Bốn ký tự đặc biệt được URLEncoder coi là safe |
| Dấu cách ` ` (U+0020) | `+` | Quy ước riêng của form encoding |
| Dấu cộng thật `+` | `%2B` | Tránh nhầm với dấu cách khi decode |
| Dấu ngã `~` | `%7E` | URLEncoder không coi dấu ngã là safe |
| Dấu phần trăm `%` | `%25` | `%` là ký tự mở đầu percent escape |
| Dấu và `&` | `%26` | Nếu để thô sẽ bị hiểu là ngăn cặp |
| Dấu bằng `=` | `%3D` | Nếu để thô có thể bị hiểu là phân cách key/value |
| Dấu gạch chéo `/` | `%2F` | Không coi là dấu phân đoạn path ở đây |
| Dấu hỏi `?` | `%3F` | Không để thành ký hiệu query delimiter |
| Dấu thăng `#` | `%23` | Không để thành fragment delimiter |
| Chữ `đ` | `%C4%91` | Hai byte UTF-8: C4 91 |
| Emoji `😀` | `%F0%9F%98%80` | Bốn byte UTF-8, không phải một byte hay một `char` |

**Cơ chế percent encoding:** Với ký tự không thuộc tập safe, Java trước hết mã hóa ký tự thành một hoặc nhiều **byte theo charset đã chọn**, sau đó viết **mỗi byte** thành ba ký tự `%HH` (hai chữ số hex). Sử dụng `StandardCharsets.UTF_8` để tránh phụ thuộc môi trường.

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

var utf8 = StandardCharsets.UTF_8;
System.out.println(URLEncoder.encode("a b", utf8));        // a+b
System.out.println(URLEncoder.encode("a+b", utf8));        // a%2Bb
System.out.println(URLEncoder.encode("a&b=c%", utf8));    // a%26b%3Dc%25
System.out.println(URLEncoder.encode("AZaz09-._*~", utf8));
// AZaz09-._*%7E
~~~

Đây là **đoạn minh họa bên trong một phương thức**, không phải chương trình `main` độc lập. Ví dụ hoàn chỉnh ở phần 13 có cùng phép tính đã được biên dịch/chạy.

### 3.1. Vì sao `+` là chỗ dễ sai nhất?

Trong chuỗi form:

~~~text
q=Java+10
~~~

`q` có giá trị `Java 10`, **không phải** `Java+10`.

Nếu giá trị thực là `Java+10` thì dạng form đúng phải là:

~~~text
q=Java%2B10
~~~

Vì `URLDecoder` chuyển ký tự `+` chưa escape thành dấu cách:

~~~java
System.out.println(
        java.net.URLDecoder.decode("Java+10", StandardCharsets.UTF_8));
// Java 10

System.out.println(
        java.net.URLDecoder.decode("Java%2B10", StandardCharsets.UTF_8));
// Java+10
~~~

Đừng dùng `String.replace("+", " ")` rồi tự giải mã percent phần còn lại bằng các thao tác không nhất quán; nên dùng API form decoder có Charset rõ ràng và parse đúng ranh giới thành phần.

### 3.2. Tập safe khác với unreserved của RFC 3986

Một số thư viện URI coi `~` là unreserved và sẽ để nguyên, nhưng `URLEncoder` của Java encode `~` thành `%7E`. Ngược lại, `*` được URLEncoder để nguyên. Đây là hành vi có chủ đích của **form encoding**, không phải lỗi trong Java.

Không so sánh output của form encoder với một URI path encoder rồi kết luận bên nào sai chỉ vì khác cách biểu diễn tương đương trong ngữ cảnh nào đó. Hãy luôn dùng đúng encoder theo **vị trí trong giao thức** và yêu cầu chữ ký/canonicalization nếu API đặc thù.

## 4. Java 10: overload `Charset` là lựa chọn nên dùng

### 4.1. Mã hóa

~~~java
String encoded = java.net.URLEncoder.encode(
        "C++ & Java",
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(encoded); // C%2B%2B+%26+Java
~~~

`URLEncoder.encode(String, Charset)` được bổ sung từ **Java 10**:

- Trả một `String` dạng form-urlencoded.
- Sử dụng `Charset` được truyền để chuyển ký tự không safe thành byte.
- Ném `NullPointerException` nếu source String hoặc Charset là `null`.
- Không cần khai báo checked `UnsupportedEncodingException` khi dùng overload nhận `Charset` đã có sẵn.

### 4.2. Giải mã

~~~java
String decoded = java.net.URLDecoder.decode(
        "C%2B%2B+%26+Java",
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(decoded); // C++ & Java
~~~

`URLDecoder.decode(String, Charset)` cũng có từ **Java 10**. Nó xử lý `+` thành space và giải mã các chuỗi `%HH` liên tiếp thành byte theo Charset được chọn.

**Quan trọng:** Mã hóa và giải mã phải **thống nhất Charset**. Nếu source chứa tiếng Việt và bên nhận diễn giải byte UTF-8 theo một charset khác, kết quả có thể bị lỗi ký tự (mojibake), hoặc xử lý thông tin không như dự kiến.

### 4.3. Không dùng overload mặc định phụ thuộc platform

Tránh trong code hiện đại:

~~~java
// Không nên dùng: overload một tham số bị deprecated.
String result = java.net.URLEncoder.encode("Tiếng Việt");
~~~

Overload một tham số dựa vào charset mặc định của môi trường và đã bị deprecated. Đừng dùng nó cho code cần output HTTP ổn định giữa máy phát triển, CI và production.

Overload `encode(String, String)`/`decode(String, String)` nhận tên charset là String vẫn còn hoạt động, nhưng phải xử lý checked exception liên quan tên encoding không hợp lệ/không được hỗ trợ. Với `StandardCharsets.UTF_8`, overload `Charset` Java 10+ đơn giản và an toàn kiểu hơn.

## 5. Mã hóa từng **tên trường** và **giá trị** trước khi ghép

Đây là quy tắc kỹ thuật quan trọng nhất sau quy tắc dấu cộng.

**Sai:**

~~~java
var raw = "name=An Nguyễn&note=a+b=c&100%";
var wrong = java.net.URLEncoder.encode(
        raw, java.nio.charset.StandardCharsets.UTF_8);
~~~

Nếu encode **toàn bộ** chuỗi đã chứa các dấu phân cách `=` và `&`, những dấu phân cách sẽ bị biến thành `%3D` và `%26`; server không thấy nhiều cặp name=value như ý định. Ngược lại, nếu không encode gì, giá trị chứa `&` và `=` sẽ vô tình bị tách.

**Đúng:**

~~~java
static String formPair(String name, String value) {
    var utf8 = java.nio.charset.StandardCharsets.UTF_8;
    return java.net.URLEncoder.encode(name, utf8)
            + "="
            + java.net.URLEncoder.encode(value, utf8);
}
~~~

Đây là method minh họa; caller phải bảo đảm name/value khác null hoặc xử lý null theo chính sách nghiệp vụ.

Từ nhiều cặp:

~~~java
String body = formPair("full name", "An Nguyễn")
        + "&" + formPair("note", "a+b=c&100%");
~~~

Ta được:

~~~text
full+name=An+Nguy%E1%BB%85n&note=a%2Bb%3Dc%26100%25
~~~

Phân tích:

1. Tên trường `full name` được mã hóa thành `full+name`.
2. Dấu cách trong giá trị `An Nguyễn` được mã hóa thành `+`.
3. Chữ `ễ` trong `Nguyễn` được mã hóa thành ba byte UTF-8 `E1 BB 85`, tương ứng `%E1%BB%85`.
4. Dấu `+` thật trong note thành `%2B`, `=` thành `%3D`, `&` thành `%26`, `%` thành `%25`.
5. Chỉ **sau khi encode từng thành phần**, code mới chèn dấu `=` và `&` **thô** để biểu thị cấu trúc.

### 5.1. Không encode lần hai những phần đã encode

~~~java
var once = java.net.URLEncoder.encode(
        "a b", StandardCharsets.UTF_8);     // a+b

var twice = java.net.URLEncoder.encode(
        once, StandardCharsets.UTF_8);      // a%2Bb
~~~

Ở lần thứ hai, ký tự `+` (đang có nghĩa space trong output lần đầu) lại bị xem là dấu cộng **thật của một input String** nên biến thành `%2B`. Bên server decode một lần sẽ nhận `a+b`, **không phải** `a b` như input ban đầu.

Không encode toàn bộ chuỗi sau khi đã ghép delimiters và encode từng field. Mỗi thành phần raw chỉ nên đi qua một bước mã hóa đúng ngữ cảnh.

## 6. Unicode và UTF-8: từ ký tự đến percent escapes

Một chuỗi Java là UTF-16. Khi đưa vào `URLEncoder.encode(s, UTF_8)`, các ký tự không thuộc tập safe được chuyển thành **byte UTF-8**, rồi mỗi byte thành `%HH`.

Ví dụ:

~~~java
String text = "đẹp 😀";
String encoded = java.net.URLEncoder.encode(
        text, java.nio.charset.StandardCharsets.UTF_8);

System.out.println(encoded);
// %C4%91%E1%BA%B9p+%F0%9F%98%80
~~~

Trong đó:

- `đ` → UTF-8 `C4 91` → `%C4%91`.
- `ẹ` → UTF-8 `E1 BA B9` → `%E1%BA%B9`.
- `p` là ký tự ASCII safe → giữ nguyên.
- Dấu cách → `+`.
- `😀` → UTF-8 `F0 9F 98 80` → `%F0%9F%98%80`.

**Phân biệt ba đơn vị đếm:**

| Đơn vị | Ý nghĩa | Ví dụ emoji |
| --- | --- | --- |
| `char` Java | Một đơn vị mã UTF-16 | Emoji ngoài BMP chiếm hai `char` |
| Unicode code point | Một giá trị mã Unicode | Emoji có một code point |
| Byte UTF-8 | Dữ liệu dùng trên mạng | Emoji này chiếm bốn byte |
| Ký tự `%HH` trong form text | Biểu diễn ASCII của byte | Bốn byte thành 12 ký tự `%HH` |

Không lấy `String.length()` trước khi encode rồi dùng làm Content-Length HTTP. Nó không phải chiều dài body đã mã hóa. Nếu cần số byte body, tính trên chuỗi **sau khi đã mã hóa** theo Charset thực sự dùng để gửi.

### 6.1. Unicode normalization là bước nghiệp vụ riêng

Hai chuỗi nhìn giống nhau có thể có biểu diễn Unicode khác (dạng composed/decomposed). `URLEncoder` **không tự áp đặt canonical normalization** cho giá trị nghiệp vụ. Nếu API tìm kiếm hoặc định danh người dùng cần chuẩn hóa Unicode, hãy quy định chính sách (ví dụ NFC khi phù hợp) **trước khi encode** và áp dụng giống nhau ở server.

Không coi percent encoding là một thuật toán chuẩn hóa tên, chống spoofing hoặc bảo đảm uniqueness. Nó chỉ biểu diễn dữ liệu để truyền qua cú pháp form.

## 7. Cách ghép form nhiều trường và giữ trùng tên

Đây là ví dụ cấu trúc data tốt:

~~~java
record Field(String name, String value) {}

var fields = java.util.List.of(
        new Field("tag", "Java 10"),
        new Field("tag", "HTTP"),
        new Field("empty", ""));
~~~

Chuyển thành body:

~~~text
tag=Java+10&tag=HTTP&empty=
~~~

Ở đây `tag` xuất hiện **hai lần**. Nếu gom ngay vào `Map<String,String>` bằng `put("tag",...)`, giá trị trước có thể bị ghi đè. Không được ngầm coi nhiều tên trùng là lỗi hoặc là “giữ bản cuối” nếu server chưa định nghĩa policy.

### 7.1. Vì sao dùng `List<Field>` thay vì Map?

| Kiểu dữ liệu | Thích hợp khi | Rủi ro |
| --- | --- | --- |
| `List<Field>` | Muốn giữ **mọi cặp** và thứ tự input | Phải tự validate trùng/giới hạn |
| `Map<String,String>` | API cam kết mỗi key chỉ có một value | Có thể làm mất các giá trị lặp |
| `Map<String,List<String>>` | API cần nhiều value mỗi key | Cần chọn thứ tự/list policy rõ |
| Thư viện form parser đã qua kiểm chứng | Cần xử lý URL-encoded theo framework/server | Phải xem chính sách null, bare key, duplicate và giới hạn |

Nếu ứng dụng cần parse query/body với field lặp, hãy xem tên key và value là **một sequence of pairs** hoặc một multimap, không phải mặc định map đơn trị.

### 7.2. Rỗng khác vắng mặt

So sánh:

~~~text
x=
~~~

với không có cặp `x` nào. Trường đầu có **value rỗng**, trường sau là **không được gửi**. Chuỗi bare key:

~~~text
x
~~~

cũng được một số parser hiểu là key có value rỗng; việc phân biệt `x` và `x=` phụ thuộc hợp đồng parser/server. Nếu ứng dụng cần phân biệt các trường hợp này, phải giữ thêm trạng thái “có dấu bằng hay không”.

Hàm `decode` ở chương trình cuối bài **chủ động** ánh xạ bare key `x` thành `Field("x","")` và trả `List.of()` cho body rỗng. Đây là một **chính sách demo**, không phải yêu cầu mọi server phải diễn giải như vậy.

### 7.3. Các delimiter phải được xử lý đúng thứ tự

Khi nhận:

~~~text
note=a%26b%3Dc&tag=Java+10
~~~

**Đúng:** tách chuỗi raw tại dấu `&` **chưa được percent decode**, sau đó tách từng cặp ở dấu `=` đầu tiên, cuối cùng decode **tên và value riêng**.

**Sai:** gọi `URLDecoder.decode` lên **toàn bộ** raw body rồi mới split tại `&`. Khi đó `%26` trở lại thành `&` bên trong một value và sẽ bị hiểu nhầm là separator. Đây là bug parse thường gặp khi xử lý form bằng code thủ công.

## 8. Giải mã form: `+`, `%HH` và thứ tự parse

Với một chuỗi form:

~~~text
note=a%2Bb%3Dc%26100%25
~~~

Sau khi tách cặp `note=<encoded value>`, sử dụng:

~~~java
String decoded = java.net.URLDecoder.decode(
        "a%2Bb%3Dc%26100%25",
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(decoded); // a+b=c&100%
~~~

Giải mã có thứ tự:

1. Xác định ranh giới pair `&` và dấu `=` trên **raw form string**, không tự decode các delimiter được escape.
2. Áp dụng form decode với **Charset UTF-8** cho mỗi tên và mỗi value.
3. Kiểm tra số lượng field, duplicate policy, độ dài, loại giá trị và quyền nghiệp vụ.
4. Nếu nội dung phải được escape khi đưa vào HTML/SQL/path/log, thực hiện **escaping/parameterization theo đích** riêng biệt, không coi form decoding là lớp bảo mật cuối.

### 8.1. Tại sao `URLDecoder` không phải generic URL decoder?

`URLDecoder` có behavior **form**: `+` trở thành dấu cách. Nhưng trong một path URI, ký tự cộng có thể là dấu cộng thật và không nên bị chuyển thành khoảng trắng chỉ vì bạn gọi decoder không đúng ngữ cảnh.

Ví dụ:

~~~java
System.out.println(java.net.URLDecoder.decode(
        "a+b", java.nio.charset.StandardCharsets.UTF_8)); // a b
~~~

Đúng trong form value; có thể **sai** nếu `a+b` là segment của URI path mà API cho phép dấu cộng literal.

Đừng lấy `uri.getPath()` hoặc một path segment rồi áp `URLDecoder` một cách tùy tiện. Trong URL, các thành phần **path, fragment, query và form body** có quy tắc biểu diễn/giải mã và API riêng. Chọn parser của đúng thành phần và framework, tránh giải mã nhiều lần.

### 8.2. Khi nhận query string kiểu form

Nếu endpoint/API quy định query tuân theo form-url-encoded convention:

~~~java
var uri = java.net.URI.create(
        "https://example.test/search?q=Java+10&tag=C%2B%2B");

String rawQuery = uri.getRawQuery();
// q=Java+10&tag=C%2B%2B
~~~

Sau đó parse **raw query** theo các cặp và form-decode từng key/value như với body. Không percent-decode trước khi split; cũng không dùng những constructor URI **tự escape thành phần** để truyền vào một chuỗi đã được percent encode rồi, vì có thể double-encode `%`. Với các API query đặc biệt (ký tự cộng literal, ký hiệu phân tách khác...), tuân theo hợp đồng cụ thể thay vì ép mọi query theo form rules.

## 9. HTTP POST với `java.net.http.HttpRequest`

Từ Java 11, package `java.net.http` có HTTP client chính thức, dùng được trên Java 17+. Để gửi body đã form-encode:

~~~java
var body = "name=" + java.net.URLEncoder.encode(
        "An Nguyễn", java.nio.charset.StandardCharsets.UTF_8);

var request = java.net.http.HttpRequest
        .newBuilder(java.net.URI.create("https://example.test/submit"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(
                body, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

Đây là **đoạn minh họa chỉ xây request**. `example.test` là địa chỉ minh họa và không có lời gọi `HttpClient.send` nên **không phát sinh network request**.

### 9.1. Những thành phần phải khớp nhau

- `Content-Type` chỉ rõ đây là form data. Bên nhận phải dùng quy tắc decode tương ứng.
- `charset=UTF-8` nêu charset client sử dụng; server/framework cần có cấu hình tương thích, không nên dựa vào phỏng đoán charset.
- `BodyPublishers.ofString(body, UTF_8)` tạo byte body bằng UTF-8.
- Chuỗi body đã được form-encode các thành phần; **không encode lại toàn bộ body** khi tạo publisher.
- `Content-Length` khi được gửi liên quan đến **số byte thực**, không phải `String.length()` của dữ liệu Unicode raw. HTTP client tự xử lý framing thích hợp theo giao thức.
- Luôn dùng HTTPS cho form nhạy cảm; POST body không phải một phương tiện mã hóa bảo mật độc lập.

### 9.2. Không nhầm với upload file

`application/x-www-form-urlencoded` phù hợp với text key/value nhỏ/vừa. Nó không thể hiện file upload hiệu quả hoặc metadata file theo từng phần như `multipart/form-data`. Khi cần file binary, dùng multipart hoặc API upload bytes thích hợp và thư viện xử lý tương ứng; không nhét file vào `URLEncoder.encode` một cách tùy tiện.

### 9.3. GET query và POST body có thể dùng cùng kiểu mã hóa, nhưng hành vi HTTP khác

Một HTML form GET thường đưa dữ liệu vào query string; form POST có thể đặt dữ liệu vào request body. Dù các pair có thể được encode theo cùng dạng, **vị trí truyền** khác nhau:

- URL query có thể xuất hiện trong history, logs, referer và các hệ thống giám sát; tránh đưa password/token nhạy cảm vào đó.
- POST body cũng cần bảo vệ trong logs/proxy/backend; nó **không tự được mã hóa** chỉ vì là POST.
- HTTPS bảo vệ truyền tải trên mạng, nhưng ứng dụng vẫn cần xác thực/ủy quyền, chống CSRF khi phù hợp, giới hạn input và xử lý dữ liệu nhạy cảm.

## 10. Ví dụ thực tế: tên lặp, giá trị chứa delimiter và Unicode

Giả sử có sáu cặp dữ liệu:

| Tên trường | Giá trị raw |
| --- | --- |
| `full name` | `An Nguyễn` |
| `tag` | `Java 10` |
| `tag` | `C++ & Java` |
| `note` | `a+b=c&100%` |
| `empty` | Chuỗi rỗng |
| `emoji` | `😀` |

Kết quả đúng khi encode từng cặp với UTF-8 và join bằng `&`:

~~~text
full+name=An+Nguy%E1%BB%85n&tag=Java+10&tag=C%2B%2B+%26+Java&note=a%2Bb%3Dc%26100%25&empty=&emoji=%F0%9F%98%80
~~~

Những điểm cần quan sát:

1. Tên `full name` chứa dấu cách cũng phải encode thành `full+name`.
2. Hai cặp `tag` được giữ cả hai, vì input là `List<Field>` chứ không bị Map ghi đè.
3. Giá trị `C++ & Java` trở thành `C%2B%2B+%26+Java`, không tách thành ba field.
4. `empty=` là một field tồn tại với giá trị rỗng, không bị bỏ.
5. Emoji không đi thẳng vào body form như raw UTF-16; nó được biểu diễn thành các percent escapes cho UTF-8 bytes.
6. Body đã encode chỉ gồm ký tự ASCII, nên khi chuyển chuỗi này sang UTF-8, số byte bằng số ký tự ASCII của **chuỗi encoded**, chứ không bằng độ dài của raw input.
7. Trong ví dụ code đầy đủ, độ dài encoded body theo UTF-8 là **110 byte**. Con số này áp dụng cho chính sáu cặp input đã cho, không phải một hằng số chung của form-urlencoded.

## 11. An toàn, tính đúng đắn và dữ liệu không tin cậy

### 11.1. Decode **đúng một lần** ở đúng ranh giới

Xét:

~~~text
%2520
~~~

Decode lần đầu: `%20` (literal percent + 2 + 0). Decode lần hai: dấu cách. Nếu một layer đã decode nhưng layer khác lại decode tiếp, nội dung có thể bị **biến đổi ý nghĩa ngoài dự kiến**.

~~~java
var utf8 = java.nio.charset.StandardCharsets.UTF_8;
boolean firstIsPercent20 = java.net.URLDecoder
        .decode("%2520", utf8).equals("%20"); // true
boolean secondIsSpace = java.net.URLDecoder
        .decode(java.net.URLDecoder.decode("%2520", utf8), utf8)
        .equals(" "); // true
~~~

Không yêu cầu “decode nhiều lần cho đến khi không còn dấu %”. Đây là mẫu có thể dẫn đến **double-decoding vulnerabilities**, bỏ qua validation hoặc khác biệt cách diễn giải giữa proxy, framework và ứng dụng.

### 11.2. Escape malformed và UTF-8 không hợp lệ

Một chuỗi chứa escape không hợp lệ như `%GG` không phải một form field chuẩn. Trên triển khai Java của chương trình demo, `URLDecoder.decode("%GG", UTF_8)` ném `IllegalArgumentException`; JavaDoc nói rõ implementation hiện tại dùng exception này.

Với input từ client không tin cậy:

- Có giới hạn kích thước body và số lượng field trước khi xử lý.
- Kiểm tra percent escapes và charset được chấp nhận theo hợp đồng API.
- Xử lý lỗi decode thành HTTP 400 hoặc lỗi domain phù hợp, không để request không hợp lệ tiếp tục chạy.
- Nếu cần phát hiện **strict malformed UTF-8**, không tự kết luận `URLDecoder` là một validator Unicode nghiêm ngặt cho mọi trường hợp; một số chuyển đổi byte/charset có thể dùng replacement. Dùng decoder/config validation chuyên biệt theo yêu cầu.
- Xác định chính sách đối với bare key, field rỗng, duplicate key, dấu phân cách lặp và giá trị quá dài.

### 11.3. Form encoding không phải escaping cho HTML, SQL hay shell

Ví dụ chuỗi đầu vào chứa `<script>` được percent encode khi truyền HTTP, nhưng sau khi server decode nó trở lại một String có dấu ngoặc. Nếu ứng dụng xuất String đó ra HTML **không escape theo HTML context**, nguy cơ XSS vẫn tồn tại. Tương tự:

- Dùng parameterized queries khi thao tác SQL, không nối String tùy tiện.
- Escape theo HTML context khi render template.
- Validate đường dẫn/ID khi tạo file path hoặc URI.
- Không log password, authorization codes, tokens hoặc nội dung nhạy cảm dưới dạng raw form hay decoded form.
- Bảo vệ khỏi CSRF theo kiểu ứng dụng và cookie/session; encoding không tự chống CSRF.
- Dùng HTTPS cho transport, nhưng vẫn kiểm soát dữ liệu ở server, logs, analytics và monitoring.

### 11.4. Duplicate keys có thể là vấn đề an ninh

~~~text
role=user&role=admin
~~~

Đây là một form hợp lệ về **cú pháp** có tên trường lặp. Nhưng backend sẽ chọn gì nếu API mong chỉ một `role`? Nếu proxy/WAF coi “giữ bản đầu” trong khi ứng dụng lại “giữ bản cuối”, hai tầng có thể hiểu khác nhau. Với các trường nhạy cảm, định nghĩa **reject duplicate** khi schema yêu cầu đơn trị, hoặc chuẩn hóa cách nhận multivalue ở mọi tầng.

Không cho phép caller lén thay chính sách bằng thứ tự tham số hoặc bằng cách encode cùng tên khác biểu diễn mà framework decode thành một tên chung.

### 11.5. Đặt giới hạn tài nguyên

Form-urlencoded có thể tăng kích thước do mỗi byte không safe thành ba ký tự `%HH`. Với input lớn, memory và thời gian encode/decode có thể tăng; hãy giới hạn body/field count/field length. Với nhiều file hoặc dữ liệu nhị phân lớn, chọn multipart/streaming upload thay vì encode toàn bộ vào một String.

## 12. Những trường hợp đầu vào cần hiểu rõ

| Input | Điều cần xác định |
| --- | --- |
| `name=` | Field có value rỗng |
| Không có cặp `name` | Field vắng mặt |
| `name` không có `=` | Parser có thể xem là value rỗng; chính sách cụ thể của demo |
| `name=A&name=B` | Nhiều giá trị cho cùng key; cần multivalue policy |
| `=value` | Có thể là tên rỗng; validation domain quyết định có chấp nhận |
| `a&&b` | Có phần tử trống giữa dấu `&`; quyết định có bỏ hay coi là empty pair |
| `text=a%26b` | Sau decode value là `a&b`; không được tách tiếp thành pair |
| `text=a+b` | Form decode ra `a b` |
| `text=a%2Bb` | Form decode ra `a+b` |
| `text=%2520` | Decode một lần cho `%20`; không tự decode lần hai |
| `text=%GG` | Escape không hợp lệ; xử lý như input lỗi |
| `text=%0D%0A` | Value chứa CRLF sau decode; có thể ảnh hưởng log/header nếu dùng sai context |
| Raw non-ASCII trong body | Không nên giả định decoder/framework nào cũng xử lý giống nhau; encode UTF-8 tường minh |
| `null` trong Java field model | Không tự là chuỗi rỗng hoặc chữ `"null"`; cần policy trước khi encode |

### 12.1. Đừng nhầm thuật toán Java URLEncoder với mọi bước HTML form submission

Khi trình duyệt submit HTML form, browser còn có các quy tắc **thu thập successful controls, thứ tự cặp, charset, giá trị default, normalization của line breaks và loại điều khiển**. Java `URLEncoder.encode(String, UTF_8)` chỉ encode **chuỗi được cung cấp**.

Ví dụ nếu bạn truyền `"a\nb"` vào Java URLEncoder, output phản ánh ký tự LF đã nhận (thường là `a%0Ab`); quy trình form submission của HTML có thể chuẩn hóa xuống CRLF trước bước encode trong những tình huống quy định. Đừng tự coi `URLEncoder` là công cụ dựng toàn bộ payload của mọi HTML form trong mọi trạng thái browser. Với nhu cầu tương thích chính xác browser hoặc chữ ký canonical body, kiểm thử theo quy tắc của bên gửi/bên nhận và chuẩn sống (WHATWG URL/HTML).

## 13. Ví dụ Java 17+ độc lập đã biên dịch và chạy

Chương trình sau bao gồm:

- Mã hóa chữ, dấu cách, dấu cộng, ký tự đặc biệt và Unicode.
- Dùng `List<Field>` để giữ **tên lặp**.
- Mã hóa **từng field**, ghép bằng `&`, parse bằng cách split raw `&` trước rồi mới decode từng thành phần.
- Tạo `HttpRequest` POST với `Content-Type: application/x-www-form-urlencoded; charset=UTF-8` nhưng **không gửi request**.
- Kiểm tra bộ đếm **110 byte** của body đã mã hóa.
- Kiểm tra decode một lần/hai lần và input `%GG` không hợp lệ.

Lưu file **`FormUrlEncodingDemo.java`**:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class FormUrlEncodingDemo {
    record Field(String name, String value) {
        Field {
            Objects.requireNonNull(name);
            Objects.requireNonNull(value);
        }
    }

    static String encode(List<Field> fields) {
        return fields.stream()
                .map(f -> URLEncoder.encode(f.name(), StandardCharsets.UTF_8)
                        + "="
                        + URLEncoder.encode(f.value(), StandardCharsets.UTF_8))
                .collect(Collectors.joining("&"));
    }

    static List<Field> decode(String body) {
        if (body.isEmpty()) {
            return List.of();
        }
        var fields = new ArrayList<Field>();
        for (String part : body.split("&", -1)) {
            int separator = part.indexOf('=');
            String name = separator < 0 ? part : part.substring(0, separator);
            String value = separator < 0 ? "" : part.substring(separator + 1);
            fields.add(new Field(
                    URLDecoder.decode(name, StandardCharsets.UTF_8),
                    URLDecoder.decode(value, StandardCharsets.UTF_8)));
        }
        return List.copyOf(fields);
    }

    public static void main(String[] args) {
        var utf8 = StandardCharsets.UTF_8;
        System.out.println("space=" + URLEncoder.encode("a b", utf8));
        System.out.println("literal-plus=" + URLEncoder.encode("a+b", utf8));
        System.out.println("safe-set=" + URLEncoder.encode("AZaz09-._*~", utf8));
        System.out.println("separators=" + URLEncoder.encode("a&b=c%", utf8));
        System.out.println("path-characters=" + URLEncoder.encode("a/b?c#d", utf8));
        System.out.println("unicode=" + URLEncoder.encode("\u0111\u1EB9p \uD83D\uDE00", utf8));

        var fields = List.of(
                new Field("full name", "An Nguy\u1EC5n"),
                new Field("tag", "Java 10"),
                new Field("tag", "C++ & Java"),
                new Field("note", "a+b=c&100%"),
                new Field("empty", ""),
                new Field("emoji", "\uD83D\uDE00"));
        var body = encode(fields);
        System.out.println("body=" + body);
        var decoded = decode(body);
        System.out.println("field-count=" + decoded.size());
        System.out.println("repeat-tag-count=" + decoded.stream()
                .filter(f -> f.name().equals("tag")).count());
        System.out.println("empty-present=" + decoded.contains(new Field("empty", "")));
        System.out.println("round-trip=" + decoded.equals(fields));
        System.out.println("body-bytes=" + body.getBytes(utf8).length);

        var request = HttpRequest.newBuilder(
                        URI.create("https://example.invalid/submit"))
                .header("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(body, utf8))
                .build();
        System.out.println("request-method=" + request.method());
        System.out.println("request-type=" +
                request.headers().firstValue("Content-Type").orElse(""));
        System.out.println("request-length=" +
                request.bodyPublisher().orElseThrow().contentLength());

        System.out.println("decode-plus=" + URLDecoder.decode("a+b", utf8));
        System.out.println("decode-percent-plus=" + URLDecoder.decode("a%2Bb", utf8));
        System.out.println("decode-once-keeps-percent=" +
                URLDecoder.decode("%2520", utf8).equals("%20"));
        System.out.println("decode-twice-becomes-space=" +
                URLDecoder.decode(URLDecoder.decode("%2520", utf8), utf8)
                        .equals(" "));

        try {
            URLDecoder.decode("%GG", utf8);
        } catch (IllegalArgumentException expected) {
            System.out.println("bad-escape=rejected");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 FormUrlEncodingDemo.java
java FormUrlEncodingDemo
~~~

**Stdout chính xác** đã được kiểm tra trên JDK hiện có:

~~~text
space=a+b
literal-plus=a%2Bb
safe-set=AZaz09-._*%7E
separators=a%26b%3Dc%25
path-characters=a%2Fb%3Fc%23d
unicode=%C4%91%E1%BA%B9p+%F0%9F%98%80
body=full+name=An+Nguy%E1%BB%85n&tag=Java+10&tag=C%2B%2B+%26+Java&note=a%2Bb%3Dc%26100%25&empty=&emoji=%F0%9F%98%80
field-count=6
repeat-tag-count=2
empty-present=true
round-trip=true
body-bytes=110
request-method=POST
request-type=application/x-www-form-urlencoded; charset=UTF-8
request-length=110
decode-plus=a b
decode-percent-plus=a+b
decode-once-keeps-percent=true
decode-twice-becomes-space=true
bad-escape=rejected
~~~

### 13.1. Giải thích các kết quả quan trọng

1. `space=a+b` và `literal-plus=a%2Bb` thể hiện khác biệt cốt lõi giữa dấu cách và dấu cộng thật.
2. `safe-set=AZaz09-._*%7E` xác nhận chính xác tập ký tự giữ nguyên theo Java URLEncoder: dấu `~` vẫn bị escape.
3. `separators=a%26b%3Dc%25` cho thấy dữ liệu chứa `&= %` không phá cấu trúc form.
4. `path-characters=a%2Fb%3Fc%23d` nhắc rằng đây là **form encoding**, không phải diễn giải dấu `/`, `?`, `#` như URI structure.
5. `unicode=%C4%91%E1%BA%B9p+%F0%9F%98%80` xác nhận UTF-8 percent encoding cho tiếng Việt và emoji.
6. `body=...` minh họa việc giữ cặp `tag` lặp, encode riêng mọi tên/value và join dấu phân cách đúng vị trí.
7. `field-count=6`, `repeat-tag-count=2`, `empty-present=true`: danh sách Field phân biệt đầy đủ dữ liệu ngay cả khi tên lặp hoặc value rỗng.
8. `round-trip=true` chỉ đúng cho dữ liệu/hợp đồng parser của ví dụ; không chứng minh tất cả parser HTTP có cùng chính sách với bare key và duplicate keys.
9. `body-bytes=110` và `request-length=110` là số byte của encoded body UTF-8, không tính từ String raw đầu vào.
10. `request-method=POST` và Content-Type khớp cho biết HttpRequest được xây đúng; **không có network call**.
11. `decode-plus=a b` và `decode-percent-plus=a+b`: form decoder phân biệt `+` với `%2B`.
12. `decode-once-keeps-percent=true`/`decode-twice-becomes-space=true` cho thấy double decoding làm thay nghĩa.
13. `bad-escape=rejected` là behavior của Java implementation khi gặp `%GG`, không phải lý do để bỏ qua validation ở tầng server.

### 13.2. Giới hạn cố ý của hàm `decode` mẫu

Hàm `decode` minh họa đúng **thứ tự tách-đôi rồi giải mã**, nhưng là parser tối giản dành cho dữ liệu do chương trình trên tạo ra:

- `body.isEmpty()` được coi là **không có field**.
- Bare key không có dấu `=` được ánh xạ thành value rỗng, nên **không bảo toàn thông tin có/không có dấu bằng**.
- `split("&",-1)` giữ cả thành phần rỗng; không có chính sách tự bỏ `&&` hay reject tên rỗng.
- Không đặt giới hạn field count/byte length/decoded length.
- Không hỗ trợ chính sách an ninh/schema/duplicate chuyên dụng.
- Không kiểm tra strict Unicode validity của mọi chuỗi percent-encoded.
- Nếu cần parser HTTP production, nên dùng framework có cơ chế giới hạn/validation đã kiểm chứng hoặc bổ sung tất cả điều kiện trên.

**Điểm cần học** là giải mã đúng **theo thành phần**, không phải copy nguyên hàm này vào một endpoint public mà không bổ sung bảo vệ.

## 14. Sai lầm phổ biến

| Sai lầm | Kết quả/Nguy cơ | Cách xử lý |
| --- | --- | --- |
| Dùng `URLEncoder` cho path URL chung | `/` bị thành `%2F` và có thể làm sai cấu trúc path | Dùng URI/path API đúng ngữ cảnh |
| Quên encode tên field | Tên có space, `&`, `=` gây sai cấu trúc | Encode cả tên và value |
| Encode cả body sau khi ghép `&` và `=` | Delimiters bị escape, form không còn đúng số cặp | Encode **từng** thành phần rồi join |
| Không escape dấu cộng literal | Server nhận space thay vì `+` | `+` → `%2B` |
| Dùng dấu `%20` và nói nó giống `+` trong mọi context | Chỉ tương đương ý nghĩa space trong một số form parsing, không phải mọi URL context | Tuân theo định dạng bên nhận |
| Gọi `URLDecoder` lên toàn body trước split | `%26` trở lại `&` trong value, tạo field giả | Split raw trước, decode components sau |
| Mã hóa hai lần | `+` thành `%2B`, `%` thành `%25` | Encode raw component đúng một lần |
| Giải mã hai lần | `%2520` có thể thành space ở lần 2 | Decode đúng một lần tại boundary |
| Dùng overload không Charset | Encoding phụ thuộc platform, đã deprecated | Dùng `StandardCharsets.UTF_8` |
| Coi `Map<String,String>` giữ được nhiều value cho một key | Duplicate bị ghi đè hoặc mất dữ liệu | `List<Field>` hoặc multimap |
| Giả định `x` và `x=` luôn phân biệt | Tùy parser; demo coi cùng value rỗng | Định rõ policy nếu cần phân biệt |
| Tưởng `URLEncoder` xử lý toàn HTML form | Còn bước chọn controls, newline, files, charset, ordering | Dùng form submission framework/browser phù hợp |
| Dùng form encoding để upload file lớn | Phình dữ liệu, mất metadata/binary semantics | `multipart/form-data` hoặc byte upload |
| Dùng String.length() làm Content-Length raw form | Không tương đương số byte gửi | Đếm byte trên encoded body/để HTTP client xử lý |
| Coi form encoding là chống injection | Sau decode có thể chứa mọi ký tự nguy hiểm | Validation + context-specific escaping/parameterization |
| Đặt secret trong GET query | Lộ qua URL logs/history/telemetry | POST over HTTPS + policy logging |
| Không giới hạn body hoặc số cặp | Dễ lạm dụng CPU/RAM/parser | Quota, size validation, từ chối input quá lớn |
| Coi mọi chuỗi `%HH` là UTF-8 hợp lệ | Invalid byte sequences có thể cần xử lý strict | Strict decoder/validation theo API |
| Dùng `URLDecoder` cho URI path | Dấu cộng literal bị đổi space | Decode theo path/query component đúng |
| Kỳ vọng charset parameter tự ép mọi server decode giống nhau | Tùy server/framework và cấu hình | Kiểm thử hợp đồng giữa client/server |

## 15. Bài tập tự kiểm tra có đáp án

**Bài 1.** Mã hóa `"Java 10"` bằng Java `URLEncoder.encode(s, UTF_8)` ra gì?

**Đáp án:** `Java+10`; U+0020 chuyển thành dấu cộng.

**Bài 2.** Mã hóa `"C++"`?

**Đáp án:** `C%2B%2B`; dấu cộng thật phải được escape thành `%2B`.

**Bài 3.** Giải mã form `q=Java+10` thì q có nội dung gì?

**Đáp án:** `Java 10`, không phải `Java+10`.

**Bài 4.** Giải mã `q=Java%2B10` thì q có nội dung gì?

**Đáp án:** `Java+10`. Percent-encoded plus đại diện dấu cộng literal.

**Bài 5.** Vì sao `URLEncoder.encode("name=a&note=b", UTF_8)` không thích hợp để tạo một form hai field?

**Đáp án:** Vì mã hóa cả dấu `=` và `&` thành `%3D`/`%26`, làm mất cấu trúc cặp. Phải encode mỗi tên/value riêng rồi ghép.

**Bài 6.** Mã hóa `"a&b=c%"` ra gì?

**Đáp án:** `a%26b%3Dc%25`.

**Bài 7.** `URLEncoder.encode("AZaz09-._*~", UTF_8)` ra gì?

**Đáp án:** `AZaz09-._*%7E`. Dấu `*` giữ nguyên, `~` bị percent escape.

**Bài 8.** Vì sao `"đ"` biến thành `%C4%91`?

**Đáp án:** Vì UTF-8 của code point U+0111 gồm hai byte `C4` và `91`; mỗi byte được viết bằng `%HH`.

**Bài 9.** Với emoji `😀`, form-encoded UTF-8 của emoji là gì?

**Đáp án:** `%F0%9F%98%80`, bốn byte UTF-8.

**Bài 10.** `tag=a&tag=b` có tương đương một Map đơn trị `{"tag":"b"}` không?

**Đáp án:** Không về mặt dữ liệu gốc: form có **hai cặp**. Một Map đơn trị có thể làm mất giá trị `a`; chính sách server phải rõ.

**Bài 11.** Có thể phân biệt field không gửi với field `name=` không?

**Đáp án:** Có ở mức cặp dữ liệu: field `name=` được gửi với value rỗng, còn absent field không xuất hiện. Một số framework có thể có chính sách binding riêng.

**Bài 12.** Parser cần split `&` trước hay decode toàn bộ chuỗi trước?

**Đáp án:** Split trên chuỗi **raw** trước, tách tên/value theo dấu `=` đầu tiên, rồi mới decode từng thành phần. Nếu decode trước, `%26` trong value thành `&` và bị tách sai.

**Bài 13.** Tại sao overload `encode(String)` không nên dùng trong Java hiện đại?

**Đáp án:** Nó phụ thuộc charset mặc định và đã deprecated. Dùng `encode(String, StandardCharsets.UTF_8)` từ Java 10.

**Bài 14.** Có nên dùng `URLDecoder.decode` cho path segment `a+b` trong URL không?

**Đáp án:** Không tùy tiện. URLDecoder là **form** decoder, sẽ chuyển `+` thành space, trong khi path có thể coi `+` là literal.

**Bài 15.** Vì sao body form với input Unicode cần tính Content-Length sau khi encode?

**Đáp án:** Content-Length là số **byte truyền tải**. Raw String.length() đo UTF-16 units, còn `URLEncoder` tạo ASCII percent escapes dựa trên UTF-8 byte sequence.

**Bài 16.** `URLDecoder.decode("%2520", UTF_8)` cho gì và vì sao không decode lại?

**Đáp án:** Một lần ra `%20`; lần hai thành space, có thể thay ngữ nghĩa và tạo lỗ hổng double decoding.

**Bài 17.** `URLDecoder.decode("%GG", UTF_8)` trên Java implementation đã kiểm thử có kết quả gì?

**Đáp án:** Ném `IllegalArgumentException`. Hãy coi chuỗi escape sai định dạng là input không hợp lệ và xử lý lỗi.

**Bài 18.** Khi nào nên chọn `multipart/form-data`?

**Đáp án:** Khi upload file hoặc cần truyền các phần dữ liệu riêng có metadata, đặc biệt binary. Không dùng form-urlencoded như byte-copy thay cho upload file.

**Bài 19.** Mã hóa form có chống SQL injection/XSS không?

**Đáp án:** Không. Nó chỉ là transport encoding. Dữ liệu sau decode vẫn cần validation, parameterized SQL và escaping theo context đầu ra.

**Bài 20.** Nếu browser chuẩn hóa line endings trước khi submit HTML form, `URLEncoder.encode` có làm bước đó thay không?

**Đáp án:** Không. `URLEncoder` chỉ encode String đã nhận. Nếu cần tương thích chính xác quá trình browser form submission, áp dụng đầy đủ quy tắc HTML/WHATWG liên quan tới controls, charset và newline.

## 16. Checklist áp dụng trong code production

Trước khi mã hóa hoặc giải mã form-urlencoded, hãy kiểm tra:

1. **Đúng media type chưa?** Đối tác mong `application/x-www-form-urlencoded` hay JSON/multipart?
2. **Charset đã thống nhất chưa?** Dùng UTF-8 tường minh ở encode, HTTP body, Content-Type và decode.
3. **Đang mã hóa đúng vị trí chưa?** Form value hay URI path/fragment có quy tắc khác nhau.
4. **Mỗi raw component chỉ encode một lần?** Tên và value trước khi join dấu `&`/`=`.
5. **Đã giữ field lặp?** Nếu schema chỉ cho một value, reject duplicate theo chính sách rõ.
6. **Đã xử lý field vắng/rỗng/bare key?** Không đánh đồng ngầm.
7. **Có Unicode và emoji không?** Có unit tests cho UTF-8 percent encoding và round-trip?
8. **Có case dấu cộng thật, `&`, `=`, `%`, slash, question, hash không?**
9. **Server parse raw trước rồi decode từng field sau?** Không decode cả body trước khi split.
10. **Có giới hạn body size, number of fields, decoded length và timeout không?**
11. **Có xử lý malformed `%HH` và invalid UTF-8 phù hợp không?**
12. **Có tránh double decoding ở proxy, router, framework, controller không?**
13. **Có dữ liệu nhạy cảm không?** HTTPS, không đưa secrets vào query hoặc logs không cần thiết.
14. **Có dùng parameterized queries và output escaping sau khi decode không?**
15. **Nếu upload file, có chuyển sang multipart/raw body đúng không?**
16. **Nếu muốn giống HTML browser tuyệt đối, có kiểm tra HTML successful controls/newline normalization không?**
17. **HTTP request body có số byte đúng?** Để HttpClient tính hoặc đo trên encoded bytes.
18. **Các test có phân biệt quy tắc Java URLEncoder và generic URI encoding không?**

## 17. Tài liệu tham khảo hiện hành

1. [Java SE 17 – URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html): tập ký tự safe, dấu cách thành `+`, percent encoding UTF-8, overload `encode(String, Charset)` có từ Java 10.
2. [Java SE 17 – URLDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html): dấu `+` thành space, chuỗi `%HH` thành bytes, overload `decode(String, Charset)` có từ Java 10 và xử lý input không hợp lệ.
3. [WHATWG URL Living Standard – application/x-www-form-urlencoded](https://url.spec.whatwg.org/#application/x-www-form-urlencoded): thuật toán percent encode/decode, bộ ký tự và biểu diễn name-value pairs đang được chuẩn hóa trong web platform.
4. [WHATWG HTML Living Standard – Form submission](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#form-submission-algorithm): quá trình HTML form submission vượt ra ngoài việc encode riêng một String.
5. [MDN – HTTP POST](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/POST): form-urlencoded body, multipart/form-data và vai trò của Content-Type.
6. [Java SE 17 – HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, body publishers và Content-Type.
7. [Java SE 17 – StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset UTF-8 chuẩn, tránh phụ thuộc platform.
8. [Java SE 17 – URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): phân biệt raw query, path, fragment và cách dựng URI.
9. [Java SE 17 – Collectors.joining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#joining(java.lang.CharSequence)): ghép các cặp đã mã hóa bằng dấu phân cách.
10. [OpenJDK – JEP 286](https://openjdk.org/jeps/286): `var` từ Java 10, được dùng cho biến cục bộ trong ví dụ Java 17+.

**Kết luận:** `application/x-www-form-urlencoded` có quy tắc biểu diễn riêng: **space thành `+`; plus thật thành `%2B`; ký tự không safe được UTF-8 percent encode theo byte**. `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` là các overload phù hợp có từ Java 10. Hãy encode **từng key/value trước khi ghép**, decode **từng key/value sau khi tách**, giữ các tên lặp theo hợp đồng, thống nhất UTF-8 và tránh double encoding/decoding. Khi cần xử lý dữ liệu lớn, upload file, URI path hoặc bảo mật, dùng **cơ chế chuyên dụng đúng ngữ cảnh** thay vì xem form encoding là giải pháp cho mọi vấn đề.
