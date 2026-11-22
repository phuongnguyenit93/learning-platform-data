# URI, path, query và mã hóa đúng ngữ cảnh khi tạo HTTP Request (Java 11+)

## 1. Vì sao cùng một ký tự nhưng cách mã hóa lại khác nhau?

Khi tạo HTTP request, chương trình thường ghép dữ liệu người dùng vào một địa chỉ: mã tài nguyên vào **path**, từ khóa tìm kiếm vào **query parameter**, đôi khi thêm ký tự tiếng Việt, khoảng trắng, dấu `/`, `+`, `&`, `=` hoặc `#`. Nếu nối các chuỗi trực tiếp mà không phân biệt ngữ cảnh, ký tự dữ liệu có thể bị hiểu thành **dấu phân cách cấu trúc của URI**, khiến request truy cập sai đường dẫn hoặc gửi sai tham số.

Ví dụ ý định gọi API tìm kiếm:

```text
Host:  api.example.com
Path:  /v1/search
Tên tham số: q
Giá trị q:   C++ & Java
```

Chuỗi tạo bằng cách ghép thẳng sẽ không biểu diễn đúng giá trị:

```java
// Minh họa cách ghép sai: & được hiểu như dấu phân cách tham số
URI wrong = URI.create(
        "https://api.example.com/v1/search?q=C++ & Java");
// Còn có khoảng trắng không được phép trong URI, nên URI.create ném lỗi.
```

Với quy ước query **`application/x-www-form-urlencoded`**, giá trị cần mã hóa riêng:

```text
https://api.example.com/v1/search?q=C%2B%2B+%26+Java
```

Ở đây `%2B` biểu thị dấu `+` **thuộc dữ liệu**, `%26` biểu thị dấu `&` **thuộc dữ liệu**, còn dấu `+` không mã hóa trong query form là cách biểu diễn **khoảng trắng**. Phía nhận chỉ diễn giải đúng khi hai bên đã thống nhất quy ước query form; cú pháp URI tổng quát không bắt buộc dấu `+` mang nghĩa khoảng trắng.

**Nguyên tắc trung tâm:** Xác định **đúng thành phần URI** trước, rồi mã hóa **dữ liệu thuộc thành phần đó** theo hợp đồng API. Không có một hàm "encode URL" duy nhất áp dụng chính xác cho toàn bộ URI, mọi path segment và mọi query value.

## 2. Giải phẫu HTTP URI và vai trò từng phần

Một URI phân cấp thường có dạng:

```text
scheme://authority/path?query#fragment
```

Xem địa chỉ ví dụ:

```text
https://api.example.com:8443/v1/items/a%2Fb?q=C%2B%2B+%26+Java&page=2#details
|----|  |------------------| |-------------| |--------------------------| |-----|
scheme        authority            path                  query            fragment
```

| Thành phần | Trong ví dụ | Công dụng |
| --- | --- | --- |
| `scheme` | `https` | Chọn giao thức truy cập |
| `authority` | `api.example.com:8443` | Xác định máy chủ/port; authority về mặt cú pháp còn có thể chứa user-info, nhưng không nên dùng user-info như cơ chế xác thực HTTP |
| `path` | `/v1/items/a%2Fb` | Chỉ đường tới tài nguyên và cấu trúc route |
| `query` | `q=C%2B%2B+%26+Java&page=2` | Dữ liệu truy vấn; `key=value&...` là quy ước của nhiều ứng dụng web, không phải cấu trúc cặp khóa-giá trị do `java.net.URI` tự phân tích |
| `fragment` | `details` | Chỉ định phần/neo trong biểu diễn tài nguyên phía client; không thuộc HTTP/1.1 origin-form request-target gửi tới server |

Trong HTTP/1.1 thông thường, request-target gửi trực tiếp tới origin server có dạng:

```http
GET /v1/items/a%2Fb?q=C%2B%2B+%26+Java&page=2 HTTP/1.1
Host: api.example.com:8443
```

Đây là **minh họa dòng yêu cầu HTTP**; địa chỉ không được gửi nguyên dạng từ `https://` vào origin-form. Host/authority được xử lý theo quy tắc HTTP, còn `#details` không gửi như một phần của request-target. Các dạng request-target khác như proxy và `CONNECT` có quy tắc riêng; bài này tập trung vào tình huống HTTP request thông thường.

Trong Java 11:

- `java.net.URI` biểu diễn và phân tích URI ở mức cú pháp.
- `java.net.http.HttpRequest` nhận một `URI` làm đích của request.
- `HttpClient` là thành phần thực hiện network I/O khi gọi `send`/`sendAsync`. Chỉ tạo `URI` hoặc `HttpRequest` **chưa gửi request ra mạng**.

## 3. Path: dấu gạch chéo là cấu trúc, dữ liệu phải mã hóa theo segment

Path thường gồm nhiều **segment** được phân tách bởi dấu `/`:

```text
/v1/users/42/orders/2026
 |   |    |   |      |
   các segment / dấu phân cấp của route
```

Khi route yêu cầu `/v1/users/{id}`, giá trị `id` có thể đến từ người dùng. Nếu `id = "team/42"` rồi nối thẳng:

```java
String id = "team/42";
String unsafePath = "/v1/users/" + id;
// Kết quả: /v1/users/team/42
// Router có thể hiểu đây là hai segment "team" và "42".
```

Nếu giao thức thực sự định nghĩa `id` là **một segment**, mã hóa ký tự `/` trong dữ liệu thành `%2F`:

```text
/v1/users/team%2F42
```

Tại mức cú pháp URI, `%2F` biểu thị byte của dấu slash nằm **bên trong một segment**, khác với dấu `/` thật dùng để tách các segment.

Tuy nhiên, một số server/proxy/router sẽ từ chối hoặc giải mã `%2F` trước khi định tuyến. Vì vậy, nếu contract route cấm slash trong ID, cách an toàn hơn là **xác thực và từ chối ID chứa slash**, chứ không giả định mọi tầng HTTP giữ nguyên ranh giới segment sau decode. Nếu API cần chấp nhận slash trong ID, hai phía phải thỏa thuận rõ cách định tuyến và xử lý encoded slash.

Các ký tự cũng có ý nghĩa cấu trúc đặc biệt:

- Dấu `?` bắt đầu query; khi thuộc dữ liệu trong path segment nên biểu diễn `%3F`.
- Dấu `#` bắt đầu fragment; khi thuộc dữ liệu nên biểu diễn `%23`.
- Dấu `%` mở đầu percent-encoding; muốn biểu diễn dấu phần trăm literal trong dữ liệu, dùng `%25`.
- Khoảng trắng trong URI path được percent-encode thành `%20`, **không dùng dấu `+` theo quy tắc form**.
- Ký tự Unicode như `á` được biểu diễn theo **các byte UTF-8** rồi percent-encode: `á` là `C3 A1` → `%C3%A1`.

Path **không** được xử lý đúng bằng `URLEncoder.encode(path, UTF_8)` vì hàm ấy dùng quy ước HTML form và sẽ đổi dấu slash phân tách thành `%2F`, đổi khoảng trắng thành dấu `+`, đồng thời làm mất cấu trúc path mà caller định tạo.

### Luôn phân biệt một segment với toàn bộ path

Đúng:

```text
"/v1/users/"   + encodePathSegment(userId)
  cấu trúc         dữ liệu của đúng một segment
```

Có thể sai:

```text
encodePathSegment("/v1/users/" + userId)
    mã hóa luôn dấu / cấu trúc thành %2F
```

Nếu ứng dụng nhận **toàn bộ path từ nguồn không tin cậy**, mã hóa từng segment chưa đủ để quyết định quyền truy cập. Cần kiểm soát những route được cho phép và cách server diễn giải path.

## 4. Query: tách dấu cấu trúc `&` và `=` khỏi dữ liệu tham số

Trên nhiều web API, query dùng dạng:

```text
?name=encodedValue&name2=encodedValue2
```

Ở dạng này:

- `?` bắt đầu toàn bộ query.
- `&` phân tách các cặp tham số theo quy ước của ứng dụng.
- Dấu `=` đầu tiên trong mỗi cặp phân tách tên và giá trị; dấu bằng **trong giá trị** cần được mã hóa.
- Tên/giá trị có thể trùng, rỗng, xuất hiện nhiều lần hoặc theo một thứ tự có ý nghĩa tùy API.

Giả sử ba tham số:

| Tên | Giá trị logic | Giá trị đã form-encode bằng UTF-8 |
| --- | --- | --- |
| `q` | `C++ & Java` | `C%2B%2B+%26+Java` |
| `page` | `2` | `2` |
| `filter` | `a=b&c` | `a%3Db%26c` |

Query hoàn chỉnh:

```text
q=C%2B%2B+%26+Java&page=2&filter=a%3Db%26c
```

Nối `&` và `=` **sau khi mã hóa từng tên/giá trị**, không percent-encode cả chuỗi `key=value&...` thành một khối; nếu làm vậy, dấu `&` phân cách cặp cũng bị mã hóa thành dữ liệu và phía nhận có thể chỉ thấy một tham số.

### `URLEncoder` chính xác là gì?

Trong Java 11, `java.net.URLEncoder` là encoder cho định dạng **`application/x-www-form-urlencoded`**. Dùng overload chỉ rõ charset:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encoded = URLEncoder.encode(
        "C++ & Java", StandardCharsets.UTF_8);

System.out.println(encoded);
// C%2B%2B+%26+Java
```

Dùng `StandardCharsets.UTF_8` để kết quả không phụ thuộc charset mặc định của máy. Đây là overload đã có trong JDK 11.

Quy tắc nổi bật:

| Giá trị dữ liệu | Kết quả của `URLEncoder.encode(value, UTF_8)` | Ý nghĩa |
| --- | --- | --- |
| `a b` | `a+b` | Dấu cách thành `+` trong form encoding |
| `a+b` | `a%2Bb` | Dấu cộng literal cần mã hóa để không bị hiểu thành dấu cách |
| `a&b` | `a%26b` | Dấu `&` không còn tách tham số |
| `a=b` | `a%3Db` | Dấu `=` không còn chia key/value |
| `báo cáo` | `b%C3%A1o+c%C3%A1o` | Unicode được mã hóa theo byte UTF-8 |
| `a/b` | `a%2Fb` | Slash là dữ liệu của một value |

**Quan trọng:** Query trong RFC 3986 cho phép dấu `+` literal; chỉ những hệ thống áp dụng quy ước form mới xem `+` là khoảng trắng. Với API yêu cầu percent-encoding chuẩn theo RFC 3986 mà **không** dùng quy ước form, cần dùng encoder phù hợp tạo `%20` cho khoảng trắng và bảo toàn quy tắc bên nhận. Không mặc định `URLEncoder` cho mọi query của mọi dịch vụ.

## 5. Percent-encoding: mã hóa byte UTF-8, không mã hóa ký tự Java theo số thập phân

Theo RFC 3986, một byte cần escape được biểu diễn bằng dấu `%` và hai chữ số hex. Tập ký tự *unreserved* có thể giữ nguyên gồm:

```text
A-Z a-z 0-9 - . _ ~
```

Các ký tự reserved như `: / ? # [ ] @ ! $ & ' ( ) * + , ; =` có thể là dấu phân cách hoặc dữ liệu tùy vị trí. Một ký tự reserved được percent-encode khi nó thuộc dữ liệu và có thể bị hiểu thành dấu phân cách của thành phần tương ứng.

Ví dụ với Unicode:

```text
Giá trị logic: "cà"
UTF-8:          63 C3 A0
URI octets:     c%C3%A0
```

Không encode `à` thành `%E0` dựa vào mã code point hoặc một byte của bảng mã khác; với UTF-8, `à` có hai byte `C3 A0`. Mã hóa URI chỉ đúng nếu cả client và server thống nhất charset và hợp đồng parse.

**Mã hóa một lần** ở ranh giới dữ liệu → URI. Nếu dữ liệu đã thành chuỗi encoded mà lại đưa vào API có trách nhiệm escape thêm, dấu `%` thành `%25` và có thể dẫn tới lỗi double encoding.

## 6. `java.net.URI`: khi nào dùng constructor, khi nào dùng URI.create?

Java `URI` có hai nhóm tạo đối tượng hữu ích:

### 6.1. Từ chuỗi URI đã ghép và đã escape đúng

```java
URI uri = URI.create(
        "https://api.example.com/v1/search?q=C%2B%2B+%26+Java");
```

`URI.create` phân tích cú pháp chuỗi **đã là URI**; nó không tự hiểu `q` là tham số cần escape giá trị và không tự biến khoảng trắng literal thành `%20`. Vì vậy:

```java
// Sai: URI.create không phải encoder cho ký tự bất hợp lệ
// URI.create("https://api.example.com/search?q=coffee shop");
// -> IllegalArgumentException do có khoảng trắng literal trong URI
```

Sử dụng `URI.create` khi bạn đã có **raw path/query encoded đúng ngữ cảnh**, hoặc một URI hoàn chỉnh đã được kiểm soát.

### 6.2. Từ các thành phần chưa percent-encode

```java
import java.net.URI;

URI uri = new URI(
        "https",                       // scheme
        null,                          // userInfo
        "api.example.com",             // host
        -1,                            // port mặc định
        "/v1/search/b\u00E1o c\u00E1o", // path đã xác định cấu trúc
        "q=coffee shop",               // query chưa percent-encode
        null                           // fragment
);

System.out.println(uri.toASCIIString());
// https://api.example.com/v1/search/b%C3%A1o%20c%C3%A1o?q=coffee%20shop
```

Các constructor nhiều đối số của `URI` quote ký tự không hợp lệ trong **từng thành phần**; chúng quote cả dấu `%`. Vì vậy path/query đưa vào constructor nên là **chuỗi thành phần chưa percent-encode**. Constructor nhận **cả path** và **cả query**, không nhận danh sách path segment hay cặp query parameter. Nó không tự mã hóa các dấu `/` đã có trong path thành dữ liệu, cũng không tự phân biệt `&` là dữ liệu trong giá trị query hay dấu phân cách.

Ví dụ double encoding dễ gặp:

```java
String encoded = URLEncoder.encode(
        "A+B & C", StandardCharsets.UTF_8);
// encoded = "A%2BB+%26+C"

// Sai khi truyền encoded vào URI constructor nhiều tham số:
URI wrong = new URI(
        "https", "api.example.com", "/search",
        "q=" + encoded, null);

// wrong.toASCIIString():
// https://api.example.com/search?q=A%252BB+%2526+C

// Đúng nếu đã xây dựng raw query:
URI right = URI.create(
        "https://api.example.com/search?q=" + encoded);

// right.toASCIIString():
// https://api.example.com/search?q=A%2BB+%26+C
```

Đây là **mã minh họa trong một phương thức có thể ném URISyntaxException**, không phải file Java độc lập. Sự khác biệt `%2B` → `%252B` xuất phát từ việc constructor nhiều đối số escape ký tự `%` lần nữa. Không có quy tắc "cứ encode mọi thành phần trước rồi đưa vào new URI(...)" nào đúng cho tất cả overload.

### 6.3. Hiểu `toString()` và `toASCIIString()`

`URI.toString()` có thể giữ lại một số ký tự Unicode không phải ASCII mà Java cho phép trong đối tượng URI. `toASCIIString()` trả chuỗi ASCII đã escape/encode những ký tự Unicode còn lại. Để inspect URI trên log khi cần biết byte representation, `toASCIIString()` thường dễ đối chiếu hơn; tuy nhiên phải tránh log token, mật khẩu hay dữ liệu nhạy cảm trong query.

## 7. `getRawPath`/`getPath` và `getRawQuery`/`getQuery` khác nhau ra sao?

`java.net.URI` cung cấp hai nhóm truy xuất:

| Phương thức | Trả về | Khi dùng |
| --- | --- | --- |
| `getRawPath()` | Path giữ nguyên các escape `%HH` | Xem cấu trúc segment **trước khi percent-decode**; bảo toàn `%2F` |
| `getPath()` | Path đã percent-decode (UTF-8) | Hiển thị/đọc giá trị logic; không tự ý tách segment sau khi decode |
| `getRawQuery()` | Query còn các escape `%HH` | Tách cặp theo delimiter **raw** nếu API dùng quy ước `&`/`=` |
| `getQuery()` | Query đã percent-decode `%HH` | Đọc nội dung được giải mã percent; không tương đương parser query form hoàn chỉnh |

Ví dụ:

```java
URI uri = URI.create(
        "https://example.com/r/a%2Fb?q=a%26b#section");

System.out.println(uri.getRawPath());  // /r/a%2Fb
System.out.println(uri.getPath());     // /r/a/b
System.out.println(uri.getRawQuery()); // q=a%26b
System.out.println(uri.getQuery());    // q=a&b
System.out.println(uri.getFragment()); // section
```

Nếu bạn tách `uri.getPath()` bằng dấu `/`, phần `a%2Fb` sau giải mã trở thành `a/b` và có thể bị xem thành hai segment. Tương tự, tách `uri.getQuery()` theo `&` sẽ tách nhầm giá trị `a%26b` vốn chứa dấu `&` **thuộc dữ liệu**.

**Thứ tự đúng với một query form đã biết:**

1. Lấy `getRawQuery()`.
2. Tách các cặp theo dấu `&` literal còn nguyên trên raw query.
3. Trong từng cặp, tìm dấu `=` đầu tiên theo hợp đồng của API.
4. Chỉ sau đó mới dùng `URLDecoder.decode(key, UTF_8)` và `URLDecoder.decode(value, UTF_8)` cho **từng thành phần**.

`URLDecoder` là decoder cho form encoding: ngoài `%HH` nó còn chuyển `+` thành khoảng trắng. Do đó `URI.getQuery()` **không** tương đương `URLDecoder.decode(uri.getRawQuery(), UTF_8)`: `getQuery()` không áp dụng quy ước plus-as-space. Không dùng `URLDecoder` một cách mù quáng với path, toàn URI hoặc query không theo quy ước form.

Với query có tham số trùng tên, tham số không có `=`, giá trị rỗng hoặc dấu phân cách khác `&`, parser cần tuân thủ **contract của API**; đoạn ví dụ dưới dùng quy ước đơn giản với ba cặp `key=value` đã biết.

## 8. Chương trình Java 11+ hoàn chỉnh: dựng HttpRequest với path và query đúng ngữ cảnh

Ví dụ này dùng `java.net.URI`, `URLEncoder`, `URLDecoder` và `java.net.http.HttpRequest` của Java 11. Để minh họa rõ sự khác nhau giữa path và query, nó tự viết một encoder **chỉ cho một path segment**, giữ lại các byte ASCII unreserved và percent-encode các byte khác theo UTF-8.

Lưu file **`UriPathQueryDemo.java`**:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

public final class UriPathQueryDemo {
    private static final char[] HEX =
            "0123456789ABCDEF".toCharArray();

    // Dùng cho MỘT path segment, không dùng cho cả URI.
    static String encodeSegment(String text) {
        if (text.equals(".") || text.equals("..")) {
            throw new IllegalArgumentException("Dot segment");
        }

        StringBuilder output = new StringBuilder();
        for (byte value : text.getBytes(StandardCharsets.UTF_8)) {
            int b = value & 0xFF;

            boolean unreserved =
                    (b >= 'a' && b <= 'z')
                    || (b >= 'A' && b <= 'Z')
                    || (b >= '0' && b <= '9')
                    || b == '-' || b == '.'
                    || b == '_' || b == '~';

            if (unreserved) {
                output.append((char) b);
            } else {
                output.append('%')
                        .append(HEX[b >>> 4])
                        .append(HEX[b & 15]);
            }
        }
        return output.toString();
    }

    static String formValue(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        // Host và route do ứng dụng kiểm soát.
        String rawPath =
                "/v1/files/" + encodeSegment("reports/2026 #1");

        // Chỉ encode tên/giá trị, tự đặt delimiter giữa các cặp.
        String rawQuery =
                "q=" + formValue("C++ & Java")
                + "&page=" + formValue("2")
                + "&filter=" + formValue("a=b&c");

        // URI.create nhận chuỗi đã được percent-encode phù hợp.
        URI uri = URI.create(
                "https://api.example.com" + rawPath + "?" + rawQuery);

        // Xây request; chưa gửi đi bất kỳ network request nào.
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        System.out.println("uri=" + request.uri().toASCIIString());
        System.out.println("rawPath=" + request.uri().getRawPath());
        System.out.println("path=" + request.uri().getPath());
        System.out.println("rawQuery=" + request.uri().getRawQuery());
        System.out.println("query=" + request.uri().getQuery());

        // Query demo đã được định nghĩa theo key=value&key=value.
        for (String pair : uri.getRawQuery().split("&", -1)) {
            int equals = pair.indexOf('=');
            String key =
                    equals < 0 ? pair : pair.substring(0, equals);
            String val =
                    equals < 0 ? "" : pair.substring(equals + 1);

            System.out.println("pair=" +
                    URLDecoder.decode(key, StandardCharsets.UTF_8)
                    + " -> " +
                    URLDecoder.decode(val, StandardCharsets.UTF_8));
        }

        // Constructor nhiều đối số nhận component chưa encoded.
        URI fromComponents = new URI(
                "https", null, "api.example.com", -1,
                "/v1/search/b\u00E1o c\u00E1o",
                "q=coffee shop", null);
        System.out.println("components=" +
                fromComponents.toASCIIString());

        System.out.println("formSpace=" + formValue("a b"));
        System.out.println("formPlus=" + formValue("a+b"));
        System.out.println("segmentSpace=" + encodeSegment("a b"));
        System.out.println("unicodeSegment=" +
                encodeSegment("b\u00E1o c\u00E1o"));

        System.out.println("resolve=" +
                URI.create("https://api.example.com/v1/users/")
                        .resolve("42"));
        System.out.println("normalized=" +
                URI.create("https://api.example.com/a/../b")
                        .normalize());
    }
}
```

Biên dịch/chạy trên JDK 11 trở lên:

```bash
javac --release 11 UriPathQueryDemo.java
java UriPathQueryDemo
```

Stdout đúng của chương trình:

```text
uri=https://api.example.com/v1/files/reports%2F2026%20%231?q=C%2B%2B+%26+Java&page=2&filter=a%3Db%26c
rawPath=/v1/files/reports%2F2026%20%231
path=/v1/files/reports/2026 #1
rawQuery=q=C%2B%2B+%26+Java&page=2&filter=a%3Db%26c
query=q=C+++&+Java&page=2&filter=a=b&c
pair=q -> C++ & Java
pair=page -> 2
pair=filter -> a=b&c
components=https://api.example.com/v1/search/b%C3%A1o%20c%C3%A1o?q=coffee%20shop
formSpace=a+b
formPlus=a%2Bb
segmentSpace=a%20b
unicodeSegment=b%C3%A1o%20c%C3%A1o
resolve=https://api.example.com/v1/users/42
normalized=https://api.example.com/b
```

### Vì sao output có những chi tiết này?

- `reports%2F2026%20%231` là **một path segment** xét trên URI raw, vì slash dữ liệu, khoảng trắng và dấu `#` đã được escape. Server/router phải đồng ý cách xử lý encoded slash; nếu không, cần dùng định dạng ID không chứa slash.
- `getPath()` giải mã thành `/v1/files/reports/2026 #1`. Đây là cách nhìn **decoded**, không còn đủ thông tin để biết dấu slash nào vốn được percent-encode.
- `getRawQuery()` bảo toàn `%26` và `%3D`, nên tách các cặp theo `&` chưa mã hóa là chính xác cho quy ước đã chọn.
- `getQuery()` đã percent-decode thành `q=C+++&+Java&page=2&filter=a=b&c`. Chuỗi này **không thể tách bằng `&` để lấy lại cặp giá trị đúng**, do `&` vốn là dữ liệu của `q` và `filter` đã được giải mã.
- Ba dòng `pair=...` chứng minh tách trên raw query rồi `URLDecoder` từng key/value sẽ khôi phục giá trị có dấu `+`, dấu `&` và `=`.
- `formSpace=a+b` khác `segmentSpace=a%20b`: cùng dấu cách logic nhưng quy tắc của query form và path segment khác nhau.
- `components=...` chứng minh constructor nhiều đối số có thể quote phần path/query chưa encoded.
- `resolve` và `normalized` minh họa API hỗ trợ ghép URI tương đối và loại bỏ các dot segment khi normalize, **không phải** một cơ chế kiểm soát quyền truy cập.

Chương trình chỉ gọi `HttpRequest.newBuilder(...).GET().build()` nên chạy được **không cần Internet**, không phụ thuộc API server có tồn tại.

## 9. Path traversal, URI.resolve và dấu chấm đặc biệt

Trong URI phân cấp, segment đúng bằng `.` hoặc `..` có thể được xử lý để bỏ segment hiện tại hoặc quay lên cấp cha trong quá trình resolution/normalization:

```java
URI base = URI.create(
        "https://api.example.com/v1/users/");

System.out.println(base.resolve("42"));
// https://api.example.com/v1/users/42

System.out.println(
        URI.create("https://api.example.com/a/../b").normalize());
// https://api.example.com/b
```

Lưu ý thêm:

- `URI.resolve` không phải API "ghép string an toàn" cho mọi đầu vào. Nếu tham số là URI tuyệt đối như `https://other.example/path`, nó có thể **thay toàn bộ scheme/host** của base. Không dùng dữ liệu người dùng chưa kiểm soát làm một URI reference rồi `resolve` mà không xác minh kết quả.
- Base path có dấu slash cuối khác với không có: `https://example.com/a/b/` resolve `c` thành `/a/b/c`, nhưng `https://example.com/a/b` resolve `c` thành `/a/c`.
- Dot-segment `.` và `..` có nghĩa đặc biệt. Encoder ví dụ từ chối đầu vào đúng bằng hai giá trị này nếu dùng làm một segment.
- Những tầng server/proxy khác nhau có thể normalize hoặc decode percent-encoding theo thứ tự khác nhau. Vì thế **mã hóa không thay thế kiểm tra route, allowlist, định danh và phân quyền**.
- `URI.normalize()` chỉ chuẩn hóa cú pháp đường dẫn mà nó nhìn thấy; nó không tự giải quyết mọi biến thể encoded traversal hay sai lệch canonicalization giữa client/server.

Với API có path ID nhận từ bên ngoài, nên định nghĩa contract: bộ ký tự được phép, ID có được chứa slash/dot segment không, có được dùng percent-encoded slash hay không và server/router parse ở bước nào.

## 10. HTTP Request: path và query khác body và header

Java 11 có HTTP client trong module `java.net.http`. Với request GET, ví dụ:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/v1/search?q=Java"))
        .GET()
        .build();
```

`request.uri()` chứa URI đích; `HttpClient.send(...)` hoặc `sendAsync(...)` mới thực hiện trao đổi HTTP. Có thể tạo request dạng POST mà **không đưa dữ liệu body vào query**:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String body = "name=" +
        URLEncoder.encode("C++ & Java", StandardCharsets.UTF_8);

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://api.example.com/v1/forms"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8))
        .build();
```

Đây là **đoạn code trong phương thức**, minh họa hợp đồng HTTP form body. Body đã dùng quy tắc form encoding; khác với xây dựng đường dẫn URI. Nhiều API JSON dùng `Content-Type: application/json` và payload JSON theo schema; không dùng `URLEncoder` để xử lý cả JSON body hay HTTP headers.

Tránh đặt secret, token hoặc thông tin nhạy cảm trong query nếu giao thức có lựa chọn tốt hơn, vì URL thường xuất hiện trong log, lịch sử truy cập hoặc hệ thống quan sát. Header xác thực nên theo API và cơ chế bảo mật tương ứng, không tự chèn bí mật vào user-info của URI.

## 11. Xử lý host và URI nhận từ người dùng

`URI.create(...)` chỉ kiểm tra cú pháp URI; việc tạo đối tượng không tự xác thực host có đáng tin, không tự kiểm tra DNS và không cấp phép gửi network request. Khi ứng dụng cho người dùng nhập URL để tải tài nguyên:

1. Chỉ cho phép scheme đúng nhu cầu, ví dụ `https`, và host/port thuộc danh sách được phép.
2. Kiểm tra `uri.isAbsolute()`, `uri.getHost()` và các trường hợp authority không phải dạng host thông thường; có thể dùng `parseServerAuthority()` để yêu cầu authority hợp lệ.
3. Không tin rằng `URI.normalize()`, `getPath()` hay percent-decoding đã làm URL an toàn để kết nối. Đối với hệ thống có nguy cơ SSRF, việc phân giải DNS, redirect và đích kết nối phải được kiểm soát theo chính sách mạng của ứng dụng.
4. Nếu host quốc tế hóa (IDN) cần xử lý riêng, dùng công cụ chuẩn hóa host tương ứng, ví dụ `java.net.IDN` theo yêu cầu của DNS; **không** áp dụng `URLEncoder` lên host.
5. Fragment không phải tham số server: `https://example.com/x#tab` và `https://example.com/x#other` có cùng request-target HTTP thông thường `/x`; nếu server cần tham số, đặt trong path/query/body theo API contract.

Ở code minh họa chính, scheme và host là literal do ứng dụng kiểm soát; chỉ dữ liệu `fileId` và các query values được phép ảnh hưởng các thành phần cụ thể.

## 12. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Sửa như thế nào? |
| --- | --- | --- |
| `URI.create` ném `IllegalArgumentException` khi có dấu cách | Đang đưa chuỗi chưa được escape vào URI parser | Mã hóa đúng component hoặc dùng constructor `URI` nhận component chưa encoded |
| `/users/a+b` không biểu diễn dấu cách | `URLEncoder` tạo `+` theo form encoding, còn dấu `+` trong URI path là dấu cộng literal | Dùng encoder path segment tạo `%20` cho dấu cách |
| `q=a+b` bị server giải thành `a b` | Server đang áp dụng form decoding | Mã hóa dấu cộng thuộc dữ liệu thành `%2B` |
| Một giá trị `a&b` bị tách thành hai query parameters | Ghép query value chưa encode | `URLEncoder.encode(value, UTF_8)` trước khi ghép dấu `&` |
| Giá trị `a=b` bị parse sai | Dùng `=` của dữ liệu như delimiter | Encode `=` trong value thành `%3D` |
| `%2B` thành `%252B` | Dữ liệu đã percent-encode lại đưa vào constructor escape thêm | Encode đúng **một lần**, chọn rõ luồng xử lý encoded hoặc decoded |
| `getPath()` cho thấy thêm dấu `/` | `%2F` đã bị percent-decode | Dùng `getRawPath()` để bảo toàn thông tin encoded slash trước khi phân đoạn |
| `getQuery().split("&")` làm vỡ giá trị | Percent-decode trước khi tách query raw | Tách `getRawQuery()` trước, decode từng key/value sau |
| Query bị sai vì ký tự Unicode | Không thống nhất UTF-8 hoặc encode theo ký tự thay vì byte | Dùng `StandardCharsets.UTF_8` và percent-encode các octet |
| Resolve URI tương đối ra đường dẫn khác mong đợi | Base có/không dấu `/` cuối làm thay đổi cách resolve | Kiểm tra base URI và sử dụng path builder theo cấu trúc cố định |
| Resolve đột ngột đổi host | Đầu vào thực ra là URI absolute | Kiểm tra/giới hạn scheme-host trước và sau resolution |
| `#fragment` không tới server | Fragment không nằm trong HTTP request-target thông thường | Đặt dữ liệu server cần vào query/path/body |
| API trả 404 khi dùng `%2F` trong ID | Router/proxy có quy tắc riêng với encoded slash | Theo hợp đồng server, từ chối slash trong ID hoặc đổi thiết kế route |

## 13. Checklist khi thiết kế URI cho một endpoint mới

- Xác định trước scheme, host, port và route cố định do ứng dụng kiểm soát.
- Chia rõ **dấu phân cách do API quy định** và **dữ liệu đầu vào**.
- Với path segment động, percent-encode byte UTF-8 theo quy tắc URI path; kiểm tra dot segment/slash phù hợp backend.
- Với query parameter dùng form convention, `URLEncoder.encode` **từng tên và giá trị** bằng UTF-8, rồi ghép `=`, `&`.
- Không form-encode cả URI hoặc toàn bộ path. Không encode lại dữ liệu đã encoded khi dùng constructor nhiều đối số.
- Khi phân tích query form từ URI, tách `getRawQuery()` trước khi `URLDecoder.decode` từng phần.
- Kiểm tra `getRawPath()`/`getRawQuery()` và `toASCIIString()` trong test để phát hiện dấu reserved bị sai vị trí.
- Test với khoảng trắng, `+`, `&`, `=`, `#`, `/`, `%`, ký tự Unicode và giá trị rỗng/lặp theo contract.
- Nếu URL có thể nhập từ bên ngoài, xác thực origin/redirect và chính sách truy cập trước khi gửi request.
- Đảm bảo server/backend thống nhất cách decode và routing, đặc biệt encoded slash, plus-as-space và path normalization.

## 14. Câu hỏi tự kiểm tra có đáp án

**1.** Muốn gửi query value `"A+B"` theo `application/x-www-form-urlencoded`, dùng dạng nào?

**Đáp án:** `A%2BB`. Nếu gửi `A+B`, bộ giải mã form sẽ hiểu `+` là khoảng trắng và kết quả thành `"A B"`.

**2.** Trong path, khoảng trắng nên là `+` hay `%20`?

**Đáp án:** `%20`. Dấu `+` không mang nghĩa khoảng trắng chung trong URI path.

**3.** `URI.create("https://example.com/a b")` có tự mã hóa dấu cách không?

**Đáp án:** Không. Vì có ký tự không hợp lệ trong chuỗi URI literal, phương thức ném `IllegalArgumentException`. Dùng URI constructor cho component chưa mã hóa hoặc encode path segment đúng.

**4.** Tại sao `getRawPath()` trả `/r/a%2Fb` nhưng `getPath()` trả `/r/a/b`?

**Đáp án:** `getPath()` percent-decode `%2F` thành dấu `/`. Nếu cần xác định ranh giới raw segment, không tách từ decoded path.

**5.** Có thể lấy `uri.getQuery().split("&")` để parse các cặp query bất kỳ không?

**Đáp án:** Không. `getQuery()` đã decode `%26` thành `&`, có thể khiến dấu phân cách trong **giá trị** bị nhầm thành delimiter. Tách trên raw query theo contract trước rồi decode từng phần.

**6.** Khi đã có `String encoded = URLEncoder.encode("a+b", UTF_8)`, nên truyền `encoded` vào tham số `query` của `new URI(scheme, host, path, query, fragment)` không?

**Đáp án:** Không theo luồng này, vì constructor escape `%` lần nữa (`%2B` thành `%252B`). Hoặc dùng query **chưa percent-encode** với constructor, hoặc ghép raw query đã encoded và parse bằng `URI.create`.

**7.** Với path segment dữ liệu `"báo cáo"`, vì sao kết quả có `%C3%A1`?

**Đáp án:** `á` được mã hóa thành hai byte UTF-8 `C3 A1`. Mỗi byte được biểu diễn thành một `%HH`, không phải một escape duy nhất theo số code point.

**8.** `URI.resolve("https://evil.example/p")` trên base tin cậy có giữ host cũ không?

**Đáp án:** Không. URI tham số là absolute nên có thể thay thế base. Cần kiểm soát nguồn URI reference và xác thực scheme/host của kết quả.

**9.** Dấu `#fragment` có được gửi như một phần của HTTP/1.1 origin-form request-target không?

**Đáp án:** Không. Origin-form gửi path và query; fragment thuộc URI reference phía client.

**10.** Nếu server không chấp nhận `%2F` trong path ID, có nên cố thêm các lớp encode `%252F` để lách parser không?

**Đáp án:** Không. Điều đó dẫn tới double encoding và cách hiểu khác nhau giữa các tầng proxy/server. Cần đổi contract route/ID hoặc dùng thiết kế đặt dữ liệu vào một vị trí server hỗ trợ rõ ràng.

## 15. Tài liệu tham khảo chính thức, còn áp dụng

- [Java SE 11 — `java.net.URI`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/URI.html): cấu trúc URI, constructor, `getRawPath`/`getPath`, `getRawQuery`/`getQuery`, `toASCIIString`, `resolve` và `normalize`.
- [Java SE 11 — `java.net.URLEncoder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/URLEncoder.html): quy tắc `application/x-www-form-urlencoded`, mã hóa dấu cách thành `+` và overload với `Charset`.
- [Java SE 11 — `java.net.URLDecoder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/URLDecoder.html): giải mã form, bao gồm dấu `+` thành dấu cách.
- [Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): tạo HTTP request từ `URI`, lựa chọn phương thức và request body.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): định nghĩa URI components, path segments, percent-encoding, reserved/unreserved và relative URI resolution.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): cú pháp `request-target`, origin-form và cách HTTP dùng path/query.

**Ghi nhớ:** Cú pháp URI chỉ rõ chỗ nào là **cấu trúc** và chỗ nào là **dữ liệu**. Giữ các dấu `/`, `?`, `&`, `=` của cấu trúc do ứng dụng quyết định; percent-encode dữ liệu theo **đúng path segment hoặc query value**, theo charset và contract đã thống nhất, rồi mới xây `URI`/`HttpRequest`.