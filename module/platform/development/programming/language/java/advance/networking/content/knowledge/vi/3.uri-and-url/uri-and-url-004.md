# Phân tích, tạo URI theo thành phần và xử lý `URISyntaxException` trong Java

Trong Java, `java.net.URI` giúp biểu diễn, phân tích (parse), kết hợp và chuẩn hóa **định danh tài nguyên** theo cú pháp URI. Một URI có thể là URL HTTP(S), đường dẫn tương đối, `mailto:`, `urn:` hoặc một định danh khác. **Tạo `URI` không mở kết nối mạng và không kiểm tra tài nguyên có tồn tại hay không.** Trọng tâm của bài học là đọc chính xác từng thành phần, xây URI mà không lẫn ranh giới dữ liệu, và xử lý `URISyntaxException` có chủ đích.

Ví dụ cùng một nhu cầu có hai cách dễ nhầm:

~~~text
"Đã có chuỗi URI hoàn chỉnh, cần kiểm tra cú pháp"
   -> new URI(fullText)                   // có thể ném URISyntaxException

"Đã có scheme, host, path, query, fragment riêng"
   -> new URI(scheme, userInfo, host, port, path, query, fragment)
                                              // tự quote một số ký tự không hợp lệ
~~~

Hai cách **không tương đương về cách xử lý dấu cách, ký tự phần trăm và ký tự phân cách**. Hiểu khác biệt này giúp tránh URI bị mã hóa hai lần hoặc query mang nghĩa ngoài dự định.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Đọc cấu trúc URI gồm `scheme`, `authority` (`userInfo`, `host`, `port`), `path`, `query`, `fragment`; nhận ra URI tuyệt đối, tương đối, hierarchical và opaque.
- Chọn `getRawPath()/getPath()`, `getRawQuery()/getQuery()` và các accessor đúng ngữ cảnh.
- Tạo URI bằng constructor một chuỗi hoặc constructor nhiều thành phần, giải thích `null`, port `-1`, phần trăm `%XX`, khoảng trắng và ký tự dành riêng.
- Phân biệt `new URI(...)` ném checked `URISyntaxException` với `URI.create(...)` ném unchecked `IllegalArgumentException`.
- Dùng `normalize()`, `resolve()`, `relativize()`, `parseServerAuthority()` đúng công dụng.
- Biết lúc nào cần `URLEncoder`/`URLDecoder` và vì sao chúng **không** phải công cụ mã hóa URI nói chung.
- Viết chương trình Java 17+ chạy độc lập để tạo, phân tích URI và hiển thị nguyên nhân/vị trí lỗi.

## 2. Mô hình URI và cách đọc từng thành phần

### 2.1. Cú pháp của URI phân cấp

Với một HTTP(S) URI điển hình:

~~~text
scheme://[userInfo@]host[:port]/path?query#fragment
https://guest@example.org:8443/docs/java?lang=vi&page=2#install
^^^^^   ^^^^^ ^^^^^^^^^^^ ^^^^ ^^^^^^^^^^ ^^^^^^^^^^^^^^ ^^^^^^^
scheme  user   host        port path       query           fragment
~~~

Dấu `:`, `//`, `/`, `?`, `#` xác định ranh giới cú pháp. **Dấu phân cách khác với dữ liệu**: dấu `#` là ký tự mở đầu fragment, còn `%23` trong path là dữ liệu biểu diễn dấu `#`. Tương tự, dấu `?` bắt đầu query trong một URI phân cấp, còn `%3F` nằm trong path là dấu hỏi thuộc tên path.

`authority` là phần giữa `//` và dấu `/`, `?`, `#` kế tiếp; một server-based authority có thể tách thành `userInfo`, `host`, `port`. **Không phải mọi URI đều có host.** Một vài URI có authority ở dạng không phân tích được thành host, nên `getRawAuthority()` có giá trị nhưng `getHost()` có thể trả `null`.

Đối với ví dụ trên:

| Gọi phương thức | Giá trị kỳ vọng |
| --- | --- |
| `getScheme()` | `"https"` |
| `getRawAuthority()` | `"guest@example.org:8443"` |
| `getUserInfo()` | `"guest"` |
| `getHost()` | `"example.org"` |
| `getPort()` | `8443` |
| `getPath()` | `"/docs/java"` |
| `getQuery()` | `"lang=vi&page=2"` |
| `getFragment()` | `"install"` |

> Không nên đưa password, access token hay bí mật vào `userInfo`, query hoặc fragment rồi ghi nguyên URI vào log. Các phần đó có thể bị lưu trong history, telemetry hoặc log ngoài ý muốn.

### 2.2. Absolute, relative, hierarchical và opaque

Có **hai trục phân loại khác nhau**:

- `isAbsolute()` là `true` nếu URI có **scheme** (ví dụ `https:`, `mailto:`). Không có nghĩa URI đó có host hay là một URL có thể kết nối.
- `isOpaque()` là `true` nếu URI **tuyệt đối** và scheme-specific part không bắt đầu bằng `/`. `mailto:team@example.org`, `urn:isbn:...` là các ví dụ opaque; chúng không có path/query theo mô hình hierarchical giống HTTP.
- URI **relative** không có scheme, ví dụ `../images/icon.svg`, `/docs`, `?lang=vi`, `#toc`.
- URI hierarchical có thể là tuyệt đối (`https://example.org/a`) hoặc tương đối (`../a`).

Một đoạn mã minh họa, chạy trong phương thức:

~~~java
URI http = URI.create("https://example.org/docs");
URI mail = URI.create("mailto:team@example.org");
URI relative = URI.create("../images/logo.svg");

System.out.println(http.isAbsolute());     // true
System.out.println(http.isOpaque());       // false
System.out.println(mail.isAbsolute());     // true
System.out.println(mail.isOpaque());       // true
System.out.println(relative.isAbsolute()); // false
~~~

Đoạn này cần `import java.net.URI;`. Các comment ghi kết quả từng phép gọi. Với `mailto:`, có thể đọc `getSchemeSpecificPart()`; không nên kỳ vọng `getHost()` hoặc `getPath()` như HTTP URI.

### 2.3. `null`, chuỗi rỗng và `-1` rất khác nhau

- `getScheme()`, `getQuery()`, `getFragment()`, `getHost()` có thể trả `null` nếu thành phần **không được định nghĩa**.
- `getPort()` trả `-1` khi không có port được chỉ định. Không có port trong URI **không tự điền số 80 hay 443**; ứng dụng có thể suy ra default dựa vào scheme.
- `https://example.org/a` có query **không tồn tại** (`getQuery() == null`); `https://example.org/a?` có query **được khai báo nhưng rỗng** (`getQuery().equals("")`).
- `#` có thể mở đầu fragment rỗng; `getFragment() == null` và `getFragment().isEmpty()` không luôn tương đương.
- Không dùng `uri.getQuery().split("&")` nếu chưa kiểm tra `null` và đặc biệt chưa xét ngữ nghĩa percent-encoding.

## 3. Parse URI từ một chuỗi đầy đủ

### 3.1. `new URI(String)`: parse và ném checked exception

~~~java
import java.net.URI;
import java.net.URISyntaxException;

public class UriParseFragment {
    static URI parse(String input) throws URISyntaxException {
        return new URI(input);
    }
}
~~~

Constructor `URI(String)` phân tích **nguyên chuỗi đã cung cấp**. Nếu chuỗi sai cú pháp, nó ném `URISyntaxException`, là **checked exception**: phải `catch` hoặc khai báo `throws`.

~~~java
URI good = new URI("https://example.org/a%20b?x=1#top"); // hợp lệ
URI bad  = new URI("https://example.org/a b");           // URISyntaxException
~~~

Hai dòng trên là **minh họa kết quả**: nếu đặt liên tiếp vào một chương trình không xử lý exception thì chương trình dừng ở dòng thứ hai. Với `URI(String)`, khoảng trắng thô trong path là bất hợp lệ; `%20` là escape hợp lệ biểu diễn khoảng trắng.

Parser **không** kiểm tra DNS, kết nối, HTTP status, tính an toàn của đích, hoặc khả năng truy cập tài nguyên. Nó chỉ xử lý tính hợp lệ theo cú pháp mà `java.net.URI` hỗ trợ.

### 3.2. `URI.create(String)`: phù hợp với hằng số đã biết hợp lệ

~~~java
URI base = URI.create("https://example.org/api/");
~~~

`URI.create(input)` hoạt động như `new URI(input)`, nhưng nếu parse thất bại nó bọc `URISyntaxException` trong `IllegalArgumentException` (**unchecked exception**). JDK định hướng cách này cho chuỗi đã biết chắc là hợp lệ, chẳng hạn cấu hình/hằng số do lập trình viên kiểm soát.

| Nguồn dữ liệu | Cách dùng thường hợp lý | Lý do |
| --- | --- | --- |
| Hằng URI literal đã kiểm tra | `URI.create("https://...")` | Cú pháp sai là lỗi lập trình/cấu hình |
| Chuỗi URI do người dùng nhập | `new URI(input)` + `catch URISyntaxException` | Có thể báo lỗi có cấu trúc cho người dùng |
| Các thành phần `scheme/host/path/query` tách riêng | Constructor nhiều tham số | Giữ ranh giới cấu trúc khi tạo |
| Chuỗi do dịch vụ bên ngoài cung cấp | `new URI(input)` và kiểm tra ngữ nghĩa | Đầu vào không hoàn toàn tin cậy |
| Đường dẫn/query có dữ liệu động | Encode theo **từng thành phần/giá trị** trước khi ghép đúng ngữ cảnh | Tránh injection và double-encoding |

Không đổi mọi `new URI(input)` thành `URI.create(input)` chỉ để khỏi khai báo `throws`; như vậy làm mất khả năng xử lý checked error ở ranh giới nhập liệu.

### 3.3. Đọc chi tiết `URISyntaxException`

Một `URISyntaxException` cung cấp:

- `getReason()`: mô tả lý do, chẳng hạn `Illegal character in path`. Đây là thông tin chẩn đoán; **không** dùng so khớp chính xác chuỗi lý do làm logic nghiệp vụ, vì wording có thể khác theo triển khai/phiên bản.
- `getIndex()`: vị trí lỗi tính từ **0** trong input, hoặc `-1` nếu không xác định.
- `getInput()`: toàn bộ input bị từ chối.
- `getMessage()`: thông báo tổng hợp lý do, vị trí (nếu có) và input.

Ví dụ xử lý ở biên nhập liệu:

~~~java
try {
    URI uri = new URI(userInput);
    // Tiếp tục kiểm tra scheme/host/port theo quy tắc ứng dụng.
} catch (URISyntaxException e) {
    int index = e.getIndex();
    String explanation = e.getReason();
    System.err.println("URI không hợp lệ, vị trí: " + index);
    System.err.println("Nguyên nhân: " + explanation);
}
~~~

Đây là **mảnh mã trong phương thức**: `userInput` phải là biến `String` có trước, và cần `import java.net.URI;`, `import java.net.URISyntaxException;`. Không log `getInput()` một cách vô điều kiện vì URI có thể chứa thông tin nhạy cảm. Cũng không tự ý “sửa” toàn bộ input bằng cách thay mọi dấu cách thành `%20`: path, query và userInfo có quy tắc khác nhau; đầu vào sai có thể cần được từ chối.

## 4. Tạo URI bằng các thành phần

### 4.1. Constructor bảy tham số

~~~java
URI uri = new URI(
    "https",             // scheme
    null,                // userInfo
    "example.org",       // host
    8443,                // port (-1 nghĩa là không khai báo port)
    "/ho so/cv",         // path
    "q=java uri&sort=asc", // query
    "muc 1"              // fragment
);
~~~

Đây là đoạn mã minh họa trong phương thức có `throws URISyntaxException` hoặc `catch`; cần `import java.net.URI;`. Kết quả:

~~~text
https://example.org:8443/ho%20so/cv?q=java%20uri&sort=asc#muc%201
~~~

Constructor bảy tham số `URI(String scheme, String userInfo, String host, int port, String path, String query, String fragment)` tạo **URI hierarchical**, đặt dấu phân cách đúng vị trí và **quote ký tự không hợp lệ cho từng thành phần**. Chẳng hạn dấu cách trong path/query/fragment được biến thành `%20`. Sau khi dựng chuỗi, constructor vẫn kiểm tra cú pháp và có thể ném `URISyntaxException`.

Một số quy tắc phải nhớ:

1. Truyền `null` khi một thành phần **không có**, hoặc `-1` khi **không chỉ định port**.
2. Nếu có scheme và path, path phải rỗng hoặc **bắt đầu bằng `/`**; truyền path tương đối như `"docs/a"` cùng scheme có thể ném `URISyntaxException`.
3. Không thêm thủ công dấu `?`, `#` vào `query`, `fragment`: constructor tự chèn delimiter.
4. Path nhận **đường dẫn**, query nhận **phần sau `?`**; dấu `/` trong path được giữ để phân tách segment.
5. Truyền `userInfo` thường không cần thiết với HTTP hiện đại; đừng đặt credential trong URI.
6. Constructor không kiểm tra dịch vụ tồn tại và không chắc chắn tự hiểu ranh giới **tham số query** (`&`, `=` vẫn có thể là ký tự cấu trúc hợp lệ trong query).

### 4.2. Các constructor liên quan và cách chọn

| Constructor | Khi nào có ích |
| --- | --- |
| `new URI(String full)` | Parse chuỗi URI đầy đủ, không tự quote ký tự sai |
| `new URI(scheme, userInfo, host, port, path, query, fragment)` | Tạo server-based hierarchical URI với host/port rõ ràng |
| `new URI(scheme, authority, path, query, fragment)` | Khi authority được cung cấp ở dạng riêng |
| `new URI(scheme, host, path, fragment)` | Biến thể ngắn không có query/port/userInfo |
| `new URI(scheme, schemeSpecificPart, fragment)` | Khi cần định danh dựa trên scheme-specific part, kể cả opaque URI |

Đừng nhầm constructor ba tham số thứ năm (`scheme, schemeSpecificPart, fragment`) với `scheme, host, path`. Nó **không** có nghĩa là ba thành phần HTTP thông thường.

### 4.3. Tên host, IPv6 và IDN

- Dùng `getHost()` hoặc constructor có `host`, **không tách hostname bằng `split(":")`**. IPv6 literal chứa dấu `:`; dạng HTTP URI thường là `https://[2001:db8::1]:8443/`.
- Với hostname quốc tế hóa, `java.net.IDN.toASCII(name)` giúp chuyển nhãn domain theo quy tắc IDN mà Java hỗ trợ trước khi dùng ở trường `host`. Vẫn phải áp dụng quy tắc cho phép host của ứng dụng; conversion không thay thế chính sách bảo mật hay kiểm tra DNS.
- Port `-1` trong `URI` là “không khai báo”, không có nghĩa kết nối đến cổng âm.

Ví dụ tạo URI có IPv6 host được API chấp nhận:

~~~java
URI local = new URI("http", null, "::1", 8080, "/health", null, null);
// URI ở dạng văn bản sẽ đặt dấu ngoặc vuông quanh IPv6 literal nếu cần.
~~~

Đoạn mã có thể dùng trong phương thức khai báo/handle `URISyntaxException`. Không phải mọi URI có `getRawAuthority()` đều có `getHost()` khác `null`. Khi một protocol cụ thể đòi server-based authority, dùng `parseServerAuthority()` để báo lỗi nếu authority không phân tích được.

## 5. `getRawXxx()` và `getXxx()`: đọc đúng percent-encoding

URI có thể biểu diễn một ký tự bằng các byte UTF-8 theo dạng `%HH` (escape/percent-encoding). Ví dụ `%20` là dấu cách ASCII. `URI` cung cấp accessor **raw** và accessor **decoded**:

| Thành phần | Raw (giữ `%HH`) | Decoded (giải mã escape) |
| --- | --- | --- |
| Path | `getRawPath()` | `getPath()` |
| Query | `getRawQuery()` | `getQuery()` |
| Fragment | `getRawFragment()` | `getFragment()` |
| User info | `getRawUserInfo()` | `getUserInfo()` |
| Authority | `getRawAuthority()` | `getAuthority()` |
| Scheme-specific part | `getRawSchemeSpecificPart()` | `getSchemeSpecificPart()` |

Với `https://example.org/ho%20so?q=a%26b#phan%201`:

~~~text
getRawPath()     -> "/ho%20so"
getPath()        -> "/ho so"
getRawQuery()    -> "q=a%26b"
getQuery()       -> "q=a&b"
getRawFragment() -> "phan%201"
getFragment()    -> "phan 1"
~~~

**Cạm bẫy quan trọng:** nếu gọi `getQuery()` trước rồi `split("&")`, giá trị của `q` ở ví dụ trên bị nhầm thành hai phần vì `%26` đã giải mã thành `&`. Khi thực sự cần phân tích cặp tham số query, hãy tách cấu trúc trên `getRawQuery()` **trước**, rồi decode tên/giá trị theo quy ước encoding của endpoint.

Tương tự, `getPath()` có thể giải mã `%2F` thành `/`. Đó là thay đổi có ý nghĩa với router và phân tách segment: **đừng tách path sau khi decode** nếu giao thức phân biệt dấu `/` làm delimiter với dấu slash được encode bên trong một segment.

`toString()` giữ biểu diễn URI có thể chứa Unicode; `toASCIIString()` xuất dạng ASCII dùng percent-encoding UTF-8 khi cần. Không nên xem `URI.toString()` hoặc `toASCIIString()` là cơ chế làm sạch input chống tấn công.

## 6. Tránh double-encoding và lỗi query

### 6.1. Chuỗi đã encode khác với thành phần chưa encode

Hai ví dụ dưới đây **khác nhau**:

~~~java
URI parsed = new URI("https://example.org/a%20b");
URI rebuilt = new URI(
        "https", null, "example.org", -1, "/a%20b", null, null);

System.out.println(parsed.getRawPath());   // /a%20b
System.out.println(rebuilt.getRawPath());  // /a%2520b
~~~

Đây là đoạn mã minh họa trong phương thức khai báo `throws URISyntaxException`, không phải chương trình độc lập. Khi dùng constructor nhiều thành phần, dấu `%` được quote thành `%25` để bảo toàn nó như **dữ liệu**. Vì vậy truyền `"/a%20b"` vào trường `path` sẽ nhận `"/a%2520b"`. Đừng trộn đoạn đã percent-encode với constructor dành cho component đầu vào.

Nguyên tắc thực hành:

- Nếu đầu vào là **chuỗi URI hoàn chỉnh đã mã hóa đúng**, parse bằng `new URI(full)`.
- Nếu đầu vào là **thành phần thô** chưa encode, dựng URI bằng constructor phù hợp rồi kiểm tra cấu trúc kết quả.
- Không encode cả chuỗi URI như một dữ liệu duy nhất; dấu `:`, `/`, `?`, `&`, `#` có ý nghĩa theo ngữ cảnh.
- Không decode rồi re-encode tùy ý, nhất là với path/query đã chứa escape.

### 6.2. Query có hai mức cấu trúc

Trong cú pháp URI tổng quát, query chỉ là **một chuỗi** sau `?`. Quy ước `key=value&key2=value2` là cách nhiều ứng dụng HTTP biểu diễn các tham số, **không phải chức năng tự động của `URI`**.

Giả sử giá trị tìm kiếm là `"a+b & c"`, chứa các ký tự `+`, khoảng trắng và `&`. Nếu ghép thẳng vào `q=...`, `&` có thể bị server hiểu là bắt đầu một tham số mới.

Đối với endpoint **dùng quy ước form query** (`application/x-www-form-urlencoded`), có thể mã hóa **từng giá trị**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class QueryValueFragment {
    static URI searchUri(String userText) {
        String encoded = URLEncoder.encode(userText, StandardCharsets.UTF_8);
        return URI.create("https://example.org/search?q=" + encoded);
    }
}
~~~

Với `userText = "a+b & c"`, chuỗi `encoded` là `a%2Bb+%26+c`; URI kết quả có query raw `q=a%2Bb+%26+c`. **Dấu `+` của form encoding đại diện cho khoảng trắng**; dấu cộng thật được encode thành `%2B`. Ở phía nhận, `URLDecoder` áp dụng ngữ nghĩa tương ứng khi endpoint dùng form encoding.

Điều cần tránh:

- `URLEncoder`/`URLDecoder` là cho **HTML form encoding**, không phải encoder/decoder cho mọi phần của URI. Không dùng `URLEncoder` để mã hóa toàn bộ URI hoặc cả path; nó có thể biến dấu `/` thành `%2F` và dấu cách thành `+` (không phải cú pháp mong muốn cho path).
- Với endpoint quy định percent-encoding RFC 3986 khác form encoding, cần dùng cơ chế encode đúng theo **quy định của endpoint**, đặc biệt xử lý `+`.
- Nếu đã dùng `URLEncoder` để có `q=a%2Bb+%26+c`, đừng đưa nguyên chuỗi đã encode vào trường `query` của constructor nhiều tham số, vì dấu `%` sẽ bị encode lần nữa.
- Không tùy tiện nối fragment `#...` vào query; constructor thành phần có argument `fragment` riêng.

### 6.3. Phân tích query raw mà không phá ranh giới

Với quy ước form query, quy trình cơ bản:

1. Lấy `uri.getRawQuery()`; nếu `null`, không có query.
2. Chia theo dấu `&` **chưa decode**; có thể xuất hiện tham số không có `=`, giá trị rỗng hoặc nhiều tham số cùng tên.
3. Với mỗi cặp, tìm dấu `=` **đầu tiên** để tách tên/giá trị, thay vì split mọi dấu `=`.
4. Decode từng phần theo quy tắc ứng dụng (`URLDecoder` chỉ khi thực sự là form encoding); kiểm soát charset, malformed escape, duplicate keys và giới hạn độ dài.

Đó là một **quy trình giao thức ứng dụng**, không phải lời hứa rằng tất cả HTTP endpoint đều dùng cùng ngữ nghĩa cho query. Nếu dùng thư viện HTTP/web framework có bộ xây dựng/parsing query parameter phù hợp, thường nên dùng API đó thay vì tự viết parser phức tạp.

## 7. `normalize`, `resolve`, `relativize` không thay thế nhau

### 7.1. `normalize()`: rút gọn dot segments trong path

~~~java
URI uri = URI.create("https://example.org/a/./b/../c");
System.out.println(uri.normalize()); // https://example.org/a/c
~~~

`normalize()` xử lý một số thành phần `.`, `..` trong **path** và những quy tắc path normalization của `URI`; nó không truy cập mạng, không tự xác thực tài nguyên, không giải mã mọi escape và không bảo đảm hai URL trỏ đến cùng một nội dung ứng dụng. Ví dụ `%2e%2e` không nhất thiết được xử lý như literal `..` trong quá trình normalize. Đừng dùng mỗi `normalize()` để ngăn path traversal.

### 7.2. `resolve(reference)`: giải tham chiếu tương đối theo base

~~~java
URI base = URI.create("https://example.org/docs/java/page.html");
URI other = URI.create("../images/logo.svg");
URI absolute = base.resolve(other);
System.out.println(absolute); // https://example.org/docs/images/logo.svg
~~~

Path của base kết thúc bằng `page.html`, nên một tham chiếu tương đối không bắt đầu `/` được giải theo **thư mục chứa tài liệu**, rồi xử lý `..`. Nếu muốn `base` đóng vai trò **thư mục**, hãy đảm bảo dấu `/` ở cuối theo yêu cầu. Một reference có URI absolute hoặc authority riêng có thể thay đổi origin đích; `resolve` **không giới hạn reference trong một thư mục**.

### 7.3. `relativize(target)`: tìm phần tương đối khi phù hợp

~~~java
URI root = URI.create("https://example.org/docs/");
URI page = URI.create("https://example.org/docs/java/uri.html");
System.out.println(root.relativize(page)); // java/uri.html
~~~

Nếu scheme/authority/path không đáp ứng điều kiện relativize, kết quả có thể giữ nguyên target thay vì trở thành URI tương đối. Không xem `relativize` là phép đảo hoàn hảo cho mọi `resolve`.

Các API đều trả **URI mới** (hoặc giữ cùng đối tượng khi không cần đổi); `URI` là immutable.

## 8. Xác minh server-based authority và ngữ nghĩa ứng dụng

Một URI có thể hợp lệ về **cú pháp tổng quát** nhưng không phù hợp cho HTTP request hoặc chính sách của ứng dụng.

~~~java
URI candidate = new URI(userInput).parseServerAuthority();

if (!"https".equalsIgnoreCase(candidate.getScheme())
        || candidate.isOpaque()
        || candidate.getHost() == null
        || candidate.getUserInfo() != null) {
    throw new IllegalArgumentException("Chỉ chấp nhận HTTPS URI có host");
}
~~~

Đây là **đoạn mã minh họa trong phương thức** với biến `userInput` có sẵn và khai báo/handle `URISyntaxException`. `parseServerAuthority()` yêu cầu authority (nếu có) phải phân tích được thành server-based authority, còn kiểm tra `getHost()` giúp xác nhận HTTP(S) URI có host. Các quy tắc bổ sung theo ứng dụng thường gồm host/port được phép, path prefix, redirect và hạn chế mạng.

**Không nhầm syntax validation với bảo mật:** kiểm tra scheme/host trên chuỗi trước khi gửi request vẫn chưa đủ để chống SSRF. Tùy threat model cần chống redirect đến host ngoài danh sách, DNS rebinding, IP nội bộ/metadata service, proxy bất ngờ và các thay đổi phân giải hostname; enforce ở tầng HTTP client, DNS, network egress và chính sách hệ thống.

### Các lỗi phân tích thường gặp

| Hiện tượng | Lý do | Cách xử lý |
| --- | --- | --- |
| `new URI("https://example.org/a b")` ném lỗi | Có dấu cách raw trong path | Tạo từ component thô hoặc encode đúng path |
| `URI.create(userInput)` ném `IllegalArgumentException` | Nó bọc `URISyntaxException` | Dùng checked constructor cho input không tin cậy |
| `getHost() == null` dù có authority | Authority không được parse thành server-based host, hoặc URI không có host | Kiểm tra cú pháp/context, dùng `parseServerAuthority()` khi cần |
| URI tạo ra `%2520` | Đã encode `%20`, rồi lại dùng component constructor | Không mã hóa hai lần; phân biệt raw input và encoded URI |
| Query bị tách sai khi có `%26` | Decode trước khi tách `&` | Tách raw query trước khi decode |
| `URLEncoder` biến dấu cách thành `+` | Đây là form encoding | Chỉ dùng khi endpoint quy định form query |
| URI resolve ra host/path khác base | Reference có thể là absolute, có `//host` hoặc `../` | Validate URI cuối, không dùng resolve làm sandbox |
| `normalize()` không loại được escape `%2e` | Normalize không phải bộ lọc bảo mật | Xác thực path theo quy tắc server/filesystem |
| `uri.equals(other)` nhưng server trả khác kết quả, hoặc ngược lại | URI equality theo cú pháp, không phải đồng nhất tài nguyên HTTP | Không dùng equality thay cho logic canonicalization nghiệp vụ |
| Mất ngữ cảnh dấu `#` | Fragment không được gửi như phần HTTP request target thông thường | Tách fragment bằng API; không nhúng vào query/path |

## 9. Chương trình Java 17+ chạy hoàn chỉnh

Ví dụ dưới đây chỉ làm việc với URI trên bộ nhớ; **không cần mạng, DNS, thư viện bên ngoài hoặc server**. Nó chứng minh cách tạo bằng thành phần, truy xuất raw/decoded, resolve, normalize và bắt lỗi cú pháp.

Tạo file **`UriStudy.java`**:

~~~java
import java.net.URI;
import java.net.URISyntaxException;

public class UriStudy {
    public static void main(String[] args) throws URISyntaxException {
        URI built = new URI("https", null, "example.org", 8443,
                "/ho so/cv", "q=java uri&sort=asc", "muc 1");

        System.out.println("uri=" + built);
        System.out.println("host=" + built.getHost());
        System.out.println("port=" + built.getPort());
        System.out.println("rawPath=" + built.getRawPath());
        System.out.println("path=" + built.getPath());
        System.out.println("rawQuery=" + built.getRawQuery());

        URI base = new URI("https://example.org/docs/java/page.html");
        System.out.println("resolved=" + base.resolve("../images/logo.svg"));

        System.out.println("normalized="
                + new URI("https://example.org/a/./b/../c").normalize());

        try {
            new URI("https://example.org/a b");
        } catch (URISyntaxException error) {
            System.out.println("errorIndex=" + error.getIndex());
            System.out.println("errorReason=" + error.getReason());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 UriStudy.java
java UriStudy
~~~

Stdout thực tế khi chạy với OpenJDK 24 (các giá trị cấu trúc và chỉ số lỗi cũng phù hợp Java 17/21 cho ví dụ này):

~~~text
uri=https://example.org:8443/ho%20so/cv?q=java%20uri&sort=asc#muc%201
host=example.org
port=8443
rawPath=/ho%20so/cv
path=/ho so/cv
rawQuery=q=java%20uri&sort=asc
resolved=https://example.org/docs/images/logo.svg
normalized=https://example.org/a/c
errorIndex=21
errorReason=Illegal character in path
~~~

Đọc kết quả:

1. Dấu cách từ `"/ho so/cv"` và `"q=java uri&sort=asc"` đã được constructor component quote thành `%20`.
2. `getRawPath()` còn escape `%20`; `getPath()` đã decode thành khoảng trắng.
3. `resolve("../images/logo.svg")` đưa đường dẫn từ `/docs/java/` lên `/docs/`, thành `/docs/images/logo.svg`.
4. `normalize()` rút gọn literal dot segments `.` và `..`.
5. Dấu cách raw trong chuỗi `https://example.org/a b` ở **vị trí index 21** gây `URISyntaxException`. Index bắt đầu từ 0; lý do từ JDK là `Illegal character in path`.

Kết quả `errorReason` dùng để quan sát lỗi, không được hard-code logic production phụ thuộc vào nguyên văn thông báo. Với input khác, `getIndex()` có thể là `-1`.

## 10. Kiểm thử theo bảng tình huống

Không dừng ở kiểm tra ví dụ “đường thẳng”: một parser/URI builder sử dụng dữ liệu ngoài cần được thử thêm các trường hợp:

| Đầu vào/tình huống | Điều cần kiểm tra |
| --- | --- |
| `https://example.org/a%20b` | Parse thành công; raw path giữ `%20`; decoded path có space |
| `https://example.org/a b` | `new URI` ném checked `URISyntaxException`; `URI.create` ném `IllegalArgumentException` |
| `https://example.org/a?` | Query rỗng khác query không có |
| `https://example.org/a#` | Fragment rỗng khác fragment không có |
| `https://example.org/a?q=a%26b` | Không split query sau khi decode |
| `mailto:team@example.org` | Absolute nhưng opaque; không có HTTP host/path |
| `../pictures/cover.png` | Relative URI, chỉ thành absolute sau resolve với base phù hợp |
| `https://[2001:db8::1]:8443/` | Host IPv6, không split chuỗi bằng dấu hai chấm |
| `https://example.org/../admin` | Normalize/resolve thay đổi đường dẫn; không suy ra quyền truy cập |
| `https://example.org/a%2520b` | Hai lớp escape; decoded path có chữ `%20`, không phải dấu cách |
| Trường query chứa `&`, `=`, `+`, Unicode | Encode/decode theo đúng quy ước của endpoint, không làm mất ranh giới tham số |
| URL có credentials/secret | Không log toàn bộ chuỗi lỗi; có chính sách từ chối/ẩn dữ liệu |

Khi viết unit test, so sánh từng thành phần và cả `getRaw...` khi encoding quan trọng, thay vì chỉ kiểm tra `uri.toString()`.

## 11. Bài tập có lời giải

### Bài 1 — Parse và xác định lỗi

Input là `"https://example.org/a b"`. Phương thức nào ném checked exception? Nếu dùng `URI.create`, loại exception gì?

**Đáp án:** `new URI(input)` ném `URISyntaxException`, còn `URI.create(input)` ném `IllegalArgumentException` (bọc lỗi cú pháp). Trong chương trình ví dụ, dấu cách ở index 21.

### Bài 2 — Xây URI từ component thô

Cần tạo `https://example.org/docs/hello%20world?lang=vi#part%201` từ những thành phần `"https"`, `"example.org"`, `"/docs/hello world"`, `"lang=vi"`, `"part 1"`. Hãy chọn constructor.

**Đáp án:**

~~~java
URI uri = new URI("https", null, "example.org", -1,
                  "/docs/hello world", "lang=vi", "part 1");
~~~

Đây là đoạn mã trong phương thức có `throws URISyntaxException`/catch. Constructor tự thêm `?`, `#` và quote khoảng trắng. Không truyền chuỗi `"/docs/hello%20world"` như path thô.

### Bài 3 — Chọn raw hay decoded

Với URI `https://example.org/search?q=a%26b`, tại sao `uri.getQuery().split("&")` nguy hiểm?

**Đáp án:** `getQuery()` decode `%26` thành `&`; dữ liệu bên trong giá trị bị hiểu nhầm thành separator. Dùng `getRawQuery()` để tách cấu trúc trước, rồi decode từng value theo quy tắc query form nếu phù hợp.

### Bài 4 — URI tuyệt đối có host không?

`URI.create("mailto:team@example.org").isAbsolute()` trả true. Vậy `getHost()` có bắt buộc khác `null`?

**Đáp án:** Không. Nó có scheme `mailto` nên absolute, nhưng opaque, không phải URI hierarchical có server-based authority. `isAbsolute()` không chứng minh có host.

### Bài 5 — Lỗi logic dù URI hợp lệ

Một ứng dụng nhận URI người dùng rồi gọi HTTP client. URI đã qua `new URI(input)` mà không ném exception. Có đủ để gửi request an toàn không?

**Đáp án:** Chưa. Cần kiểm tra scheme, host, port, userInfo, redirect, chính sách network egress và những ràng buộc bảo mật khác. **Đúng cú pháp** không có nghĩa **được phép truy cập** hay **đích an toàn**.

## 12. Checklist áp dụng vào code thật

- [ ] Tôi biết đầu vào là **URI hoàn chỉnh** hay **các thành phần thô**.
- [ ] Tôi đã quyết định dùng `new URI(...)` hay `URI.create(...)` dựa trên khả năng input sai cú pháp.
- [ ] Tôi không trộn thành phần đã percent-encode vào constructor tự quote.
- [ ] Tôi dùng raw accessor khi cần giữ ranh giới path/query; decode ở đúng ngữ cảnh.
- [ ] Tôi không dùng `URLEncoder` cho path hoặc toàn URI.
- [ ] Tôi phân biệt `null`, chuỗi rỗng và port `-1`.
- [ ] Tôi xử lý `URISyntaxException` và không làm rò input chứa bí mật trong thông báo/log.
- [ ] Nếu URI đi tới network, tôi đã kiểm tra thêm các quy tắc ngữ nghĩa và bảo mật.
- [ ] Tôi có test cho space, `%HH`, encoded separator, fragment, relative, IPv6 và input sai.

## 13. Tài liệu chính thức

- [Java SE 21 — `java.net.URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): grammar, các constructor, raw/decoded accessor, normalize, resolve, relativize, parseServerAuthority.
- [Java SE 21 — `java.net.URISyntaxException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URISyntaxException.html): `getReason()`, `getIndex()`, `getInput()`, `getMessage()`.
- [Java SE 21 — `java.net.URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html): quy ước `application/x-www-form-urlencoded`.
- [Java SE 21 — `java.net.URLDecoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html): decode theo form encoding.
- [Java SE 21 — `java.net.IDN`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/IDN.html): chuyển tên miền quốc tế hóa.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): ngữ nghĩa tổng quát về syntax/percent-encoding/delimiter; khi làm Java cần đối chiếu thêm contract cụ thể của `java.net.URI`.

**Ghi nhớ:** `URI(String)` **parse**, constructor nhiều tham số **dựng từ component và quote khi cần**, `URISyntaxException` **báo lỗi cú pháp**, còn validation nghiệp vụ/bảo mật là bước riêng. Khi giữ rõ ba trách nhiệm đó, bạn sẽ tránh phần lớn lỗi URI trong Java Networking.
