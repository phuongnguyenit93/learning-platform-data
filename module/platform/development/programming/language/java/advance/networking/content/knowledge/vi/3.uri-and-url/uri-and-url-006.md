# Percent-encoding, Unicode và sự khác nhau giữa thành phần thô với đã giải mã

## Mục tiêu bài học

Khi làm việc với URI/URL trong Java, phải tách hai câu hỏi: **chuỗi này gồm những thành phần nào?** và **dữ liệu trong từng thành phần được mã hóa ra sao?** Sau bài này, bạn sẽ:

- Hiểu percent-encoding dưới dạng `%xy`, chuyển Unicode sang UTF-8 rồi mã hóa theo byte.
- Phân biệt kí tự phân cách URI với kí tự dữ liệu được percent-encode.
- Đọc đúng `getRawPath()`/`getPath()`, `getRawQuery()`/`getQuery()` và những cặp phương thức raw/decoded của `java.net.URI`.
- Phân biệt percent-decoding của `URI` với định dạng HTML form của `URLEncoder`/`URLDecoder`, nhất là cách xử lý dấu `+`.
- Biết khi nào dùng chuỗi URI đã escape, khi nào dùng constructor nhận thành phần chưa escape, và vì sao double-encoding/double-decoding làm thay đổi ngữ nghĩa.

Ví dụ dùng Java 17+ và dữ liệu cố định nên không phụ thuộc DNS hay kết nối mạng.

## 1. Cấu trúc URI và vai trò các dấu phân cách

Một hierarchical URI có thể gồm:

~~~text
https://example.org/caf%C3%A9/notes?name=Vi%E1%BB%87t&tag=a%26b#overview
\___/   \_________/ \_____________/ \______________________/\______/
scheme   authority       path                  query           fragment
~~~

- **Scheme**: `https`, `http`, `file`… xác định loại URI.
- **Authority**: có thể chứa user-info, host và port; trong ví dụ là `example.org`.
- **Path**: đường dẫn; dấu `/` không escape ngăn cách các path segment.
- **Query**: phần sau `?`, trước `#` nếu có; cách biểu diễn key/value bằng `&` và `=` là một quy ước của ứng dụng/giao thức.
- **Fragment**: phần sau `#`. Với HTTP thông thường, fragment xử lý phía client và không nằm trong request target gửi đến server.

Một dấu `&` bên trong **giá trị** có thể được viết `%26`, và dấu `/` bên trong **dữ liệu của một segment** có thể được viết `%2F`. Việc phân biệt “dấu phân cách” với “dữ liệu” là lý do cần xem bản **raw** trước khi giải mã.

Không phải URI nào cũng có đủ các phần trên. URI có thể là **opaque**, như một dạng `mailto:name@example.org`. Khi ấy `URI.getPath()` và `getRawPath()` có thể là `null`; hãy xem `getSchemeSpecificPart()`/`getRawSchemeSpecificPart()` theo ngữ nghĩa scheme. Trong URI phân cấp, thành phần thiếu cũng có thể là `null`; một thành phần rỗng và một thành phần hoàn toàn không tồn tại không nhất thiết giống nhau.

## 2. Percent-encoding hoạt động theo byte

Một percent-escape viết **một byte** thành ba ký tự `%` và hai chữ số hex, thường kí hiệu `%xy`. Chẳng hạn:

| Dữ liệu | Byte hex | Percent-encoding |
|---|---|---|
| dấu cách | `20` | `%20` |
| dấu `/` | `2F` | `%2F` |
| dấu `&` | `26` | `%26` |
| dấu `+` | `2B` | `%2B` |
| dấu `#` | `23` | `%23` |
| dấu `%` | `25` | `%25` |

`%2f` và `%2F` diễn tả cùng byte; cách viết hex hoa thường dễ nhất quán. Dấu `%` luôn phải được escape thành `%25` khi nó **là dữ liệu** chứ không phải mở đầu một escape.

**Unreserved** trong RFC 3986 gồm chữ cái ASCII, chữ số và `- . _ ~` (viết liền là `-._~`). Những ký tự này thường được giữ nguyên. **Reserved** gồm những dấu có thể mang ý nghĩa cú pháp như `:`, `/`, `?`, `#`, `@`, `&`, `=`, `+` và các dấu khác được nêu trong RFC 3986. Không có quy tắc “luôn escape mọi reserved”: trước tiên phải biết ký tự nằm trong **thành phần nào** và giữ vai trò **phân cách** hay **dữ liệu**.

Ví dụ:
- Trong `/a/b`, slash chia hai segment `a` và `b`.
- Trong `/a%2Fb`, `%2F` chưa phải slash phân cách; nó là byte mã hóa bên trong **một** segment.
- Trong `?x=1&y=2`, dấu `&` phân chia hai trường theo quy ước query.
- Trong `?note=a%26b`, dấu `&` là một phần giá trị `a&b`, không phải cặp query mới.

### Unicode phải chuyển sang UTF-8 trước khi percent-encode

Đừng percent-encode bằng cách lấy trực tiếp một ký tự Java `char` làm một byte. Unicode có code point khác byte của UTF-8, và Java `char` là đơn vị UTF-16. Dùng UTF-8 để tạo **dãy byte**, sau đó escape từng byte cần biểu diễn.

| Ký tự | UTF-8 dạng hex | Dạng URI |
|---|---|---|
| `é` | `C3 A9` | `%C3%A9` |
| `đ` | `C4 91` | `%C4%91` |
| `日` | `E6 97 A5` | `%E6%97%A5` |
| `🙂` | `F0 9F 99 82` | `%F0%9F%99%82` |

Chuỗi `café` có ba ký tự ASCII unreserved nên biểu diễn thông dụng là `caf%C3%A9`. Chuỗi `%E9` **không phải UTF-8 của `é`**: đó chỉ là một byte mang giá trị `E9`, chưa tạo thành chuỗi UTF-8 hợp lệ của ký tự ấy.

Có thêm khác biệt về **Unicode normalization**: chữ `é` có thể được biểu diễn thành U+00E9 hoặc thành `e` (U+0065) + dấu sắc kết hợp (U+0301). Hai dạng có thể trông giống nhau nhưng mã hóa UTF-8 lần lượt thành `%C3%A9` và `e%CC%81`. Percent-decoding không tự làm NFC/NFD normalization. Nếu nghiệp vụ muốn đồng nhất chúng, xác định và áp dụng chính sách `java.text.Normalizer` riêng, có chủ đích.

## 3. Raw và decoded trong `java.net.URI`

`URI` cung cấp các cặp phương thức:

| Thành phần | Dạng raw | Dạng decoded |
|---|---|---|
| User info | `getRawUserInfo()` | `getUserInfo()` |
| Authority | `getRawAuthority()` | `getAuthority()` |
| Path | `getRawPath()` | `getPath()` |
| Query | `getRawQuery()` | `getQuery()` |
| Fragment | `getRawFragment()` | `getFragment()` |
| Scheme-specific part | `getRawSchemeSpecificPart()` | `getSchemeSpecificPart()` |

**Raw**: không diễn giải dãy `%xy`, giữ nguyên escape đã có. **Decoded**: giải mã những dãy percent-escaped bằng UTF-8; kể cả ký tự reserved cũng được giải mã. Ví dụ `%2F` có thể thành `/`, `%26` có thể thành `&`.

Cần nhớ hai điều:
1. **Raw không đồng nghĩa chỉ ASCII.** Java có thể giữ các ký tự Unicode trực tiếp trong chuỗi URI; raw getter có thể chứa cả Unicode và percent-escape. Dùng `toASCIIString()` nếu muốn biểu diễn URI chỉ bằng ASCII.
2. **Decoded là dữ liệu đã giải mã, không nhất thiết là đầu vào an toàn để phân tích lại cấu trúc.** `getPath()` đã thay `%2F` thành `/`; `getQuery()` đã thay `%26` thành `&`. Nếu cắt chuỗi decoded theo những dấu phân cách đó, có thể sinh ra các segment hoặc tham số giả.

`getHost()`/`getScheme()` được parser trích xuất riêng; không có cặp getter `getRawHost()`/`getRawScheme()` tương ứng. `URI` cũng không tự tạo một map query parameters từ `getQuery()`.

### Quan sát trên một URI cố định

Xét URI:

~~~text
https://example.org/caf%C3%A9/%E6%97%A5%E6%9C%AC?note=a%26b&plus=a+b#r%C3%A9sum%C3%A9
~~~

| Getter | Giá trị |
|---|---|
| `getRawPath()` | `/caf%C3%A9/%E6%97%A5%E6%9C%AC` |
| `getPath()` | `/café/日本` |
| `getRawQuery()` | `note=a%26b&plus=a+b` |
| `getQuery()` | `note=a&b&plus=a+b` |
| `getRawFragment()` | `r%C3%A9sum%C3%A9` |
| `getFragment()` | `résumé` |

`getQuery()` giải mã `%26` thành `&`, nhưng không biến dấu `+` thành khoảng trắng. Nếu bạn lấy chuỗi `note=a&b&plus=a+b` rồi `split("&")` sẽ lầm tưởng `b` là một tham số riêng. Ở đây giá trị `note` thực ra là `a&b`.

## 4. Ví dụ Java 17+ chạy được và đầu ra kiểm chứng được

Lưu mã sau vào **`UriEncodingDemo.java`**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriEncodingDemo {
    public static void main(String[] args) {
        URI uri = URI.create(
            "https://example.org/caf%C3%A9/%E6%97%A5%E6%9C%AC"
            + "?note=a%26b&plus=a+b#r%C3%A9sum%C3%A9"
        );

        System.out.println("raw path: " + uri.getRawPath());
        System.out.println("path: " + uri.getPath());
        System.out.println("raw query: " + uri.getRawQuery());
        System.out.println("query: " + uri.getQuery());
        System.out.println("raw fragment: " + uri.getRawFragment());
        System.out.println("fragment: " + uri.getFragment());

        String form = URLEncoder.encode(
            "café + trà", StandardCharsets.UTF_8
        );
        System.out.println("form: " + form);
        System.out.println("decoded form: " +
            URLDecoder.decode(form, StandardCharsets.UTF_8));

        URI tricky = URI.create("https://example.org/a%2Fb/%252F");
        System.out.println("path2 raw: " + tricky.getRawPath());
        System.out.println("path2: " + tricky.getPath());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UriEncodingDemo.java
java UriEncodingDemo
~~~

**Stdout chính xác** (đã kiểm tra trong Java runtime, không dùng mạng):

~~~text
raw path: /caf%C3%A9/%E6%97%A5%E6%9C%AC
path: /café/日本
raw query: note=a%26b&plus=a+b
query: note=a&b&plus=a+b
raw fragment: r%C3%A9sum%C3%A9
fragment: résumé
form: caf%C3%A9+%2B+tr%C3%A0
decoded form: café + trà
path2 raw: /a%2Fb/%252F
path2: /a/b/%2F
~~~

Ba ý nghĩa quan trọng từ output:
- `%C3%A9` và các byte UTF-8 khác được `URI.getPath()` giải mã thành Unicode.
- `%26` trong query được giải mã thành `&`, khiến query decoded **không còn đủ thông tin ranh giới** để tách lại theo dấu `&`.
- `/a%2Fb/%252F` thành `/a/b/%2F`: `%2F` đã thành dấu slash; `%252F` sau **một lần** decode chỉ còn `%2F`. Decode tiếp lần nữa là đổi nghĩa dữ liệu.

## 5. Quy tắc riêng của `URLEncoder` và `URLDecoder`

Tên `URLEncoder` dễ gây hiểu nhầm. Trong Java, lớp này mã hóa dữ liệu theo định dạng **`application/x-www-form-urlencoded`**, thường dùng cho **giá trị trường form hoặc query đã thống nhất quy ước này**. Nó không phải bộ mã hóa tùy ý cho một URI hoàn chỉnh.

Với form encoding:
- Khoảng trắng thành dấu `+`.
- Dấu `+` thật trong dữ liệu thành `%2B`.
- Các ký tự không an toàn được chuyển thành byte theo charset, nên ưu tiên `StandardCharsets.UTF_8`, rồi escape.
- `URLDecoder.decode(value, UTF_8)` làm quá trình ngược lại và **biến `+` thành khoảng trắng**.

| Lệnh / dữ liệu | Kết quả |
|---|---|
| `URLEncoder.encode("a b", UTF_8)` | `a+b` |
| `URLEncoder.encode("a+b", UTF_8)` | `a%2Bb` |
| `URLDecoder.decode("a+b%2Bc", UTF_8)` | `a b+c` |
| `URI.create("https://e.test/?q=a+b%2Bc").getQuery()` | `q=a+b+c` |

Dòng cuối minh họa rằng `URI.getQuery()` chỉ percent-decode `%2B` thành dấu `+`, **không** diễn giải dấu `+` thường thành space. Bởi vậy, đừng chạy `URLDecoder` trên nguyên path hoặc toàn URL: nó có thể làm thay đổi những dấu `+` vốn là dữ liệu hợp lệ.

### Mã hóa từng query parameter, rồi mới ghép delimiter

Nếu dịch vụ dùng query kiểu form:

~~~java
String query = "term=" +
        URLEncoder.encode("cà phê & trà", StandardCharsets.UTF_8)
        + "&page=1";
URI request = URI.create("https://example.org/search?" + query);
~~~

Đây là **mã minh họa đặt trong method/class** có import `URI`, `URLEncoder` và `StandardCharsets`; không phải chương trình Java độc lập. Kết quả phần raw query là:

~~~text
term=c%C3%A0+ph%C3%AA+%26+tr%C3%A0&page=1
~~~

Dấu `&` thuộc **giá trị** được mã hóa thành `%26`; dấu `&` thực sự phân tách hai tham số được giữ nguyên. Không gọi `URLEncoder.encode` trên chuỗi hoàn chỉnh `https://example.org/search?term=...`: nó sẽ escape cả các ký tự cấu trúc như `:`, `/`, `?`, `&`.

### Tách query raw trước khi decode giá trị

Khi đã biết query tuân theo `application/x-www-form-urlencoded`, thứ tự đúng là:
1. Lấy `uri.getRawQuery()`.
2. Tách ở dấu `&` thực sự xuất hiện trong raw query.
3. Trong từng cặp, tách dấu `=` đầu tiên.
4. `URLDecoder.decode(..., UTF_8)` **từng tên và giá trị**.

Ví dụ **phương thức minh họa**, đặt trong class Java có import `java.net.URI`, `java.net.URLDecoder`, `java.nio.charset.StandardCharsets`, `java.util.ArrayList`, `java.util.List`:

~~~java
static List<String[]> parseFormPairs(URI uri) {
    String raw = uri.getRawQuery();
    if (raw == null || raw.isEmpty()) {
        return List.of();
    }

    List<String[]> result = new ArrayList<>();
    for (String entry : raw.split("&", -1)) {
        String[] fields = entry.split("=", 2);
        String key = URLDecoder.decode(
            fields[0], StandardCharsets.UTF_8);
        String value = URLDecoder.decode(
            fields.length == 2 ? fields[1] : "",
            StandardCharsets.UTF_8);
        result.add(new String[] { key, value });
    }
    return result;
}
~~~

Với `note=a%26b&tag=1`, cách này cho hai cặp với giá trị `a&b` và `1`; không tạo tham số `b` giả. `List` còn giữ được nhiều tham số trùng tên (ví dụ `tag=A&tag=B`), tránh làm mất dữ liệu như cách đưa ngay vào `Map<String,String>`.

Phương thức trên là **parser tối giản theo giả định form encoding**. Ứng dụng thực cần quy định xử lý khóa rỗng, thiếu dấu `=`, cặp rỗng, charset, tham số trùng, giới hạn kích thước và chuỗi escape lỗi. Không dùng `URLDecoder` bừa bãi cho generic query mà giao thức không định nghĩa `+` là space.

## 6. Chuỗi URI đã escape và các constructor nhận component

Java có hai nhóm cách tạo URI cần phân biệt.

**Chuỗi URI hoàn chỉnh đã escape:**

~~~java
URI uri = URI.create(
    "https://example.org/files/a%2Fb?name=Vi%E1%BB%87t"
);
~~~

`URI.create(String)` parse nguyên chuỗi và bảo toàn `%2F`, `%E1...` trong các raw getter. `new URI(String)` cũng parse chuỗi, nhưng khai báo checked exception `URISyntaxException`; `URI.create` bọc lỗi cú pháp thành `IllegalArgumentException`.

**Các thành phần chưa escape:**

~~~java
URI uri = new URI(
    "https", null, "example.org", -1,
    "/café Việt Nam", null, null
);
System.out.println(uri.getRawPath());
System.out.println(uri.toASCIIString());
~~~

Đây là đoạn minh họa dùng constructor 7 tham số, cần import `java.net.URI` và xử lý/khai báo `URISyntaxException`. Hai dòng in:

~~~text
/café%20Việt%20Nam
https://example.org/caf%C3%A9%20Vi%E1%BB%87t%20Nam
~~~

Constructor nhiều tham số tự quote ký tự không hợp lệ trong thành phần; ký tự Unicode có thể còn nguyên trong **raw path**. `toASCIIString()` chuyển toàn URI sang dạng ASCII, percent-encode các ký tự Unicode khi cần. `toString()` thì có thể giữ Unicode trực tiếp.

**Bẫy double-encoding:** nếu đưa path `"/a%2Fb"` vào constructor nhiều tham số, dấu `%` sẽ được quote thành `%25`, tạo `"/a%252Fb"` ở raw getter. Lý do: constructor nhận **dữ liệu component**, không coi dãy `%2F` từ đầu vào là một escape cần giữ nguyên. Hãy quyết định đầu vào đã percent-encoded hay chưa trước khi dùng API; không trộn hai kiểu tùy tiện.

Constructor cũng không biết query `"term=a&b"` có hai tham số hay một giá trị chứa dấu `&`. Đối với HTTP query, dùng thư viện URI builder có khái niệm query parameter hoặc chủ động mã hóa **từng giá trị** đúng với giao thức, rồi mới ghép delimiter.

### Unicode hostname khác Unicode path/query

Tên miền quốc tế hóa theo DNS dùng **IDNA/Punycode**. Java có `java.net.IDN.toASCII(host)` cho một số tình huống chuyển hostname Unicode sang dạng ASCII để phân giải. Không dùng `URLEncoder` cho cả hostname và đừng mặc định percent-encoding Unicode host là đủ để DNS hiểu đúng. Khi truy cập HTTPS, thư viện client phải áp dụng quy tắc tên host và kiểm tra chứng chỉ TLS phù hợp.

## 7. Percent-decoding quá sớm gây lỗi gì?

### Path segment bị chia sai

~~~text
Raw URI path: /files/a%2Fb
Decoded path: /files/a/b
~~~

Ở dạng raw, `a%2Fb` là một segment dữ liệu, dù bên trong có escape cho dấu slash. Nếu một router hoặc đoạn code gọi `getPath()` rồi `split("/")`, nó có thể hiểu sai thành hai segment `a` và `b`. Quy tắc xử lý slash đã escape phụ thuộc server/framework; đây là lý do các lớp gateway, route và ứng dụng cần thống nhất cách xử lý.

### Query có ký tự phân cách giả

~~~text
Raw query:     note=a%26b&sort=asc
Decoded query: note=a&b&sort=asc
~~~

Nếu tách decoded query, ứng dụng tưởng có ba mục `note=a`, `b` và `sort=asc`. Tách raw query trước rồi decode từng field mới bảo toàn `note=a&b`.

### Double-encoding và double-decoding

~~~text
/a%252Fb  --decode 1 lần-->  /a%2Fb  --decode lần nữa-->  /a/b
~~~

`%252F` biểu diễn dấu `%` đã escape cộng hai ký tự `2F`. **Một lần** decode tạo `%2F`. Nếu một thành phần hệ thống tiếp tục decode không kiểm soát, dữ liệu lại thành slash, làm thay đổi route, đường dẫn hoặc cache key.

Trong hệ thống có browser, reverse proxy, framework và backend, cần hợp đồng rõ ràng về **định dạng vào/ra ở mỗi ranh giới**. Chỉ decode theo giao thức, đúng thời điểm, tránh decode lại chuỗi đã decoded. Khi kiểm tra quyền truy cập file/path, áp quy tắc trên biểu diễn thực sự dùng để truy cập; không giả định một phép gọi `URI.normalize()` là đủ.

### Ký tự escape không hợp lệ

`URI.create("https://example.org/a%G1")` hoặc một dấu `%` lẻ sẽ bị từ chối vì cú pháp percent escape sai. Một dãy `%xx` có thể hợp lệ về cú pháp nhưng các byte lại không phải UTF-8 hợp lệ; Java `URI` có thể đưa ký tự thay thế `U+FFFD` trong phần decoded. `URLDecoder` có thể ném `IllegalArgumentException` khi gặp escape không hợp lệ. Với dữ liệu không tin cậy, nên xử lý lỗi rõ ràng, kiểm tra giới hạn độ dài và không coi decoded-only log là bản gốc.

## 8. Liên hệ giữa URI, URL và các loại normalization

`java.net.URI` là đối tượng biểu diễn cú pháp URI; parse và gọi raw/decoded getter không tự mở socket hay thực hiện HTTP request. `java.net.URL` gắn với protocol/resource locator, có API dùng để mở kết nối, nhưng `URL.getPath()` và `URL.getQuery()` không cung cấp các cặp raw/decoded như `URI`. Khi cần phân tích cú pháp, làm việc với `URI` hoặc thư viện URL phù hợp thay vì đoán `URLDecoder` sẽ xử lý đúng mọi thành phần.

Ba thao tác sau **không đồng nghĩa**:
- **Percent-decoding**: đổi dãy `%xx` thành byte rồi diễn giải ký tự; có thể giải mã reserved thành delimiter.
- **`URI.normalize()`**: xử lý các path segment `.` và `..` theo cú pháp URI, không phải hàm “làm sạch mọi input”.
- **Unicode normalization**: đồng nhất dạng mã điểm Unicode (NFC/NFD…) bằng `java.text.Normalizer` khi nghiệp vụ cần.

Việc so sánh/canonicalize URI, ký URL, đặt cache key hoặc kiểm tra quyền truy cập nên quy định rõ raw/decoded, mức độ chuẩn hóa và ký tự được phép. Không tùy tiện decode ký tự reserved hoặc tái tạo URI từ getter decoded như thể những chuỗi ấy vẫn nguyên cú pháp.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Một ký tự Unicode tương ứng một `%xx`.” | Một ký tự có thể cần nhiều byte UTF-8 và nhiều escape. |
| “`getRawPath()` luôn ASCII.” | Raw chỉ giữ escaped octets; chuỗi raw vẫn có thể chứa Unicode trực tiếp. |
| “`getPath()` tách theo slash luôn đúng.” | `%2F` đã decode thành `/`, có thể làm thay đổi segment boundary. |
| “`getQuery()` rồi tách ở `&`.” | `%26` trong giá trị cũng đã thành `&`; hãy tách raw trước. |
| “Dấu `+` luôn là dấu cách.” | Chỉ theo quy ước form encoding; `URI.getQuery()` không đổi dấu `+` thành space. |
| “`URLEncoder` dùng để encode nguyên URL.” | Nó dùng cho dữ liệu HTML form; encode toàn URI sẽ phá delimiter. |
| “Constructor component giữ nguyên `%2F`.” | Nó quote dấu `%` thành `%25`, tạo `%252F`. |
| “Decode thêm lần nữa an toàn.” | `%252F` có thể đổi nghĩa thành slash khi decode hai lần. |
| “Hai chữ nhìn giống nhau cho cùng bytes URI.” | Unicode NFC/NFD có thể khác nhau; normalization là bước riêng. |
| “URI hợp lệ là đường dẫn/hostname an toàn.” | Cú pháp hợp lệ không thay thế validation/authorization/host policy. |

## 10. Tự luyện tập

1. Giải thích tại sao `/image/a%2Fb` có một cấu trúc segment khác với `/image/a/b` dù hai chuỗi có thể giống nhau sau `getPath()`.
2. Với `?note=a%26b&tag=A&tag=B`, hãy viết kết quả đúng khi phân tích query form; tại sao cần giữ giá trị `tag` trùng tên?
3. Mã hóa UTF-8 thành percent-escape cho `é`, `đ` và `日`, rồi giải thích tại sao `%E9` không thay thế được `%C3%A9`.
4. So sánh `URLEncoder.encode("a b", UTF_8)` và `URLEncoder.encode("a+b", UTF_8)`; sau khi form-decode chúng khác nhau như thế nào?
5. Với constructor 7 tham số nhận path `"/a%2Fb"`, `getRawPath()` cho kết quả gì? Khi nào nên dùng `URI.create(String)` thay thế?
6. Với `%252F`, sau một lần percent-decode sẽ được gì? Vì sao hai lần decode có nguy cơ ảnh hưởng routing và kiểm tra path?
7. So sánh `toString()` và `toASCIIString()` đối với path chứa `"café Việt Nam"`; giá trị raw getter có bắt buộc chỉ là ASCII không?

**Đáp án trọng tâm:** (1) raw giữ `%2F` là dữ liệu, decoded có dấu slash; (2) `note=a&b` và hai giá trị `tag=A`, `tag=B`; (3) `%C3%A9`, `%C4%91`, `%E6%97%A5`; (4) `a+b` và `a%2Bb`; (5) `/a%252Fb`; (6) `%2F`, decode tiếp thành slash; (7) `toASCIIString()` escape Unicode, raw getter vẫn có thể chứa Unicode.

## 11. Tóm tắt kỹ thuật

- Percent-encoding là **byte → `%xx`**; với văn bản Unicode thường là **Unicode → UTF-8 → percent-encoding**.
- Java `URI.getRaw*()` cho biểu diễn chưa percent-decode; `URI.get*()` cho biểu diễn đã decode, có thể chứa dấu delimiter vốn được escape.
- Dùng **raw query/path để xác định cấu trúc**, rồi decode dữ liệu theo đúng quy tắc giao thức. Đừng tách lại decoded text như URI nguyên bản.
- `URLEncoder`/`URLDecoder` dùng quy ước HTML form: **space ↔ `+`**; không dùng bừa cho whole URL/path.
- Constructor nhiều tham số có thể quote `%` và tạo double-encoding. Với chuỗi URI đã escape, dùng parser phù hợp; khi cần ASCII, dùng `toASCIIString()`.
- Với hostname Unicode, xem xét IDNA; với so sánh text Unicode, xem xét normalization; với security/routing, thống nhất thứ tự parse/decode/validate.

### Tài liệu tham khảo

- [Oracle Java SE 21 — URI, escaped octets, raw/decoded getters, constructors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html)
- [Oracle Java SE 21 — URLEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html)
- [Oracle Java SE 21 — URLDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html)
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax, mục 2](https://www.rfc-editor.org/rfc/rfc3986.html)
