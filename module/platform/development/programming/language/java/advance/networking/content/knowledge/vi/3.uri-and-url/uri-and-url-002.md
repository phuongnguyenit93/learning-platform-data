# Cấu trúc URI/URL: scheme, authority, host, port, path, query và fragment

## 1. Mục tiêu và phạm vi

Khi lập trình mạng Java, một địa chỉ như `https://example.org:8443/docs?id=7#intro` không chỉ là một chuỗi bất kỳ: dấu `:`, `//`, `/`, `?` và `#` có vai trò phân tách các thành phần. Hiểu đúng cấu trúc giúp bạn xây dựng URL an toàn, định tuyến yêu cầu, mã hóa Unicode, xử lý link tương đối và tránh nhầm query với fragment.

Sau bài học, bạn có thể:

- Phân tích một URI thành **scheme, authority, user-info, host, port, path, query, fragment** và nhận ra thành phần nào không có mặt.
- Phân biệt **URI** (định danh/tham chiếu tài nguyên theo cú pháp tổng quát) với **URL** (URI cung cấp cách định vị/truy cập tài nguyên theo một scheme); biết khi nào dùng `java.net.URI` và `java.net.URL`.
- Dùng đúng `getRaw...()` và `get...()`; hiểu ký tự `%20`, dấu `+`, dấu `?` và `#` không tương đương nhau.
- Xây dựng, phân giải, chuẩn hóa URI trong Java 17+ mà không cắt ghép chuỗi tùy tiện.
- Nhận diện các lỗi phổ biến về default port, IPv6, query parameter, relative reference và dữ liệu đầu vào không đáng tin cậy.

**Giới hạn của chủ đề:** ở đây ta đọc và tạo *địa chỉ*. Các chi tiết về HTTP request body, TCP socket, DNS hay triển khai máy chủ là các tầng khác. Đặc biệt, **phân tích `URI` không tự thực hiện kết nối mạng**.

## 2. Sơ đồ tổng thể của một URI phân cấp

Ví dụ xuyên suốt:

~~~text
https://reader@example.org:8443/docs/java%20networking?lang=vi&tag=uri#basics
└─┬─┘  └───────────┬───────────┘└───────────┬──────────┘└──────┬──────┘└──┬──┘
scheme         authority                path               query         fragment
                │
            reader@example.org:8443
              │       │         │
           user-info  host      port
~~~

Cấu trúc tổng quát (viết giản lược cho URI phân cấp phổ biến):

~~~text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
                 │
               [userinfo "@"] host [":" port]
~~~

Không phải URI nào cũng có đầy đủ các phần. Ví dụ `mailto:team@example.org` là **opaque URI**: có scheme `mailto` nhưng không có authority/host/path như một HTTP URL phân cấp. Một tham chiếu tương đối như `../images/logo.png` có path nhưng không có scheme.

| Thành phần | Phần được lấy từ ví dụ | Ý nghĩa |
| --- | --- | --- |
| **scheme** | `https` | Quy ước cú pháp/cách sử dụng tài nguyên; nằm trước dấu hai chấm đầu tiên |
| **authority** | `reader@example.org:8443` | Vùng mô tả nơi có thẩm quyền, bắt đầu sau `//` và kết thúc trước path/query/fragment |
| **user-info** | `reader` | Phần tùy chọn trước `@` trong authority; không nên chứa bí mật |
| **host** | `example.org` | Tên miền, IPv4 hoặc IPv6 literal có cú pháp phù hợp |
| **port** | `8443` | Cổng tường minh sau host; có thể không xuất hiện |
| **path** | `/docs/java%20networking` | Đường dẫn theo cấu trúc phân cấp của URI |
| **query** | `lang=vi&tag=uri` | Chuỗi sau `?` đến trước `#`; cách hiểu key/value là quy ước ứng dụng |
| **fragment** | `basics` | Tham chiếu vị trí/phần con trong tài nguyên theo ngữ cảnh scheme/media type |

Dấu `:` sau scheme, `//` trước authority, `?` và `#` là **dấu phân cách**. Chúng không thuộc chuỗi nội dung mà `getScheme()`, `getRawQuery()`, `getRawFragment()` trả về. Authority chỉ là một phần của URI phân cấp khi xuất hiện dạng `//authority`. Path ở ví dụ bắt đầu bằng `/`, nhưng không phải mọi path đều như vậy.

## 3. Scheme: quy ước đọc URI

Scheme nằm trước dấu `:` và thường chọn quy tắc diễn giải phần còn lại. Tên scheme phải bắt đầu bằng chữ cái và có thể tiếp tục bằng chữ cái, chữ số, `+`, `-`, `.`. Một số ví dụ:

- `https://example.org`: HTTP over TLS theo scheme `https`.
- `http://example.org`: HTTP thông thường theo scheme `http`.
- `file:///home/user/readme.txt`: tham chiếu dạng file URI; ba dấu `/` phản ánh authority trống và path tuyệt đối.
- `mailto:team@example.org`: địa chỉ thư theo scheme `mailto`, không có `//host` theo kiểu HTTP.
- `urn:isbn:...`: một dạng định danh URN, không giả định có server.

`URI.getScheme()` cho `null` với tham chiếu tương đối. Để xét một địa chỉ có thể gọi là URI tuyệt đối theo ngữ pháp, kiểm tra `uri.isAbsolute()`; điều đó **chỉ cho biết có scheme**, không bảo đảm địa chỉ có host hợp lệ, có thể truy cập, hay mang giao thức HTTP.

Scheme thường được so sánh không phân biệt hoa/thường theo cú pháp URI; nhưng khi kiểm tra chính sách ứng dụng, hãy chuẩn hóa hoặc so sánh tường minh như `"https".equalsIgnoreCase(uri.getScheme())`. Không suy luận scheme chỉ bằng kiểm tra một tiền tố chuỗi như `startsWith("https")`.

## 4. Authority: user-info, host và port

### 4.1. Authority là một khối, host chỉ là một phần

Với `https://reader@example.org:8443/docs`:

~~~text
authority = reader@example.org:8443
user-info = reader
host      = example.org
port      = 8443
~~~

Authority thường có dạng `[userinfo@]host[:port]` với **server-based authority**. Không được coi chuỗi authority luôn bằng host: authority có thể chứa `userinfo` và `port`; một số URI còn cho phép **registry-based authority** mà `getHost()` không tách được thành hostname thông thường.

Trong Java:

- `getRawAuthority()` trả dạng chưa giải mã percent-encoding, hoặc `null` nếu không có authority.
- `getAuthority()` trả chuỗi authority sau giải mã percent-encoding (nếu có).
- `getRawUserInfo()` / `getUserInfo()` trả user-info tùy chọn.
- `getHost()` trả host khi URI có authority kiểu server hợp lệ; có thể trả `null`, kể cả khi `getRawAuthority()` không phải `null`.
- `getPort()` trả cổng tường minh dưới dạng `int`; trả `-1` khi không xác định.

**Không dùng user-info để nhét mật khẩu vào URL.** Chẳng hạn, `https://name:password@example.org/` rất dễ bị lộ qua log, lịch sử, analytics, thông báo lỗi hay chia sẻ liên kết. Các client HTTP hiện đại không nhất thiết chấp nhận hoặc sử dụng user-info như một cơ chế xác thực hợp lệ.

### 4.2. Host và IPv6

Host có thể là tên miền (`api.example.org`), IPv4 (`192.0.2.10`) hoặc IPv6 literal. Trong chuỗi URI, **IPv6 literal cần nằm trong dấu ngoặc vuông** để phân biệt dấu hai chấm bên trong địa chỉ với dấu phân cách cổng:

~~~text
https://[2001:db8::1]:8443/health
          └──IPv6───┘ └port┘
~~~

`https://2001:db8::1:8443/` không phải cách biểu diễn tương đương. Khi thao tác với hostname Unicode quốc tế, cần chính sách chuyển IDN phù hợp (ví dụ `IDN.toASCII(...)` cho dạng ASCII/punycode) và kiểm tra đầu vào; đừng tự chèn tên Unicode chưa kiểm chứng rồi đoán kết quả `getHost()`.

`getHost()` **không thực hiện DNS lookup**; nó chỉ phân tích cú pháp chuỗi. Host tồn tại trong URI không chứng minh máy chủ tồn tại. Nếu ứng dụng yêu cầu authority kiểu server nghiêm ngặt, `parseServerAuthority()` có thể giúp phát hiện trường hợp authority không thể phân tích thành user-info/host/port; phương thức này có thể ném `URISyntaxException`.

### 4.3. Port tường minh khác với port mặc định

So sánh:

~~~text
https://example.org/docs
https://example.org:443/docs
https://example.org:8443/docs
~~~

- `URI.getPort()` ở dòng đầu trả **`-1`**, vì URI không viết port; không trả tự động `443`.
- Dòng hai ghi `443` một cách tường minh.
- Dòng ba ghi `8443` tường minh.

Với HTTPS, cổng 443 là cổng mặc định thường được client chọn nếu không chỉ định; đó là **quy tắc của giao thức/client**, không phải số được `URI` tự thêm. Khi validate port cho mạng thực, cần xét phạm vi cổng hợp lệ và chính sách ứng dụng. Giá trị `-1` không có nghĩa là “port âm trên mạng”.

## 5. Path: đường dẫn, segment, dấu `/` và dot-segment

Path thường mô tả vị trí phân cấp trong tài nguyên:

~~~text
https://example.org/
https://example.org/docs/java
https://example.org/docs/java%20networking
https://example.org/a/b/../c
~~~

Các dấu `/` phân tách segment của path. `/` (root) **khác** với path rỗng về mặt chuỗi URI, dù server HTTP có thể quyết định xử lý chúng tương đương. Path cũng có thể không tồn tại ở URI opaque.

`getRawPath()` giữ nguyên dạng percent-encoded, còn `getPath()` giải mã percent-encoding:

~~~text
raw path     = /docs/java%20networking
decoded path = /docs/java networking
~~~

`%20` là dạng mã hóa byte khoảng trắng. **Không dùng `java.net.URLDecoder` để decode path**: `URLDecoder` xử lý quy tắc HTML form, biến `+` thành khoảng trắng, trong khi `+` có thể là một ký tự path hợp lệ. Với ứng dụng cần phân tích segment, lưu ý `%2F` có thể trở thành dấu `/` khi decode; decode quá sớm có thể đánh mất phân biệt giữa dấu phân cách gốc và ký tự đã được mã hóa. Với chữ ký request, cache key hoặc router, hãy quy định và giữ nhất quán dạng raw/canonical mà hệ thống dùng.

**Dot-segment** `.` và `..` mang ý nghĩa đường dẫn tương đối. `URI.normalize()` loại các segment dư thừa như `.`, `..` trong URI phân cấp theo quy tắc của Java; ví dụ `/a/./b/../c` thường chuẩn hóa thành `/a/c`. Đây là phép biến đổi **cú pháp**, không truy cập filesystem, không xác nhận tài nguyên có thật và không thay thế kiểm tra bảo mật ở phía server.

## 6. Query: phần sau `?` là chuỗi quy ước của ứng dụng

Xét `https://example.org/search?q=java&tag=network&tag=uri#result`:

~~~text
raw query = q=java&tag=network&tag=uri
fragment  = result
~~~

URI chuẩn chỉ xác định **chuỗi query**; nó không bắt buộc query phải là map key/value. Cách dùng `&` để tách cặp và `=` để tách tên/giá trị rất phổ biến trong web, nhưng thuộc **quy ước ứng dụng/HTTP form**, không phải tính năng `URI.getQuery()` tự phân tích. Trong Java, `URI` không có `getQueryParameter("q")`.

Những điều cần lưu ý:

1. Tên tham số có thể lặp: `tag=network&tag=uri`. Biến tất cả thành một `Map<String,String>` đơn giản có thể làm mất giá trị.
2. Thứ tự tham số có thể quan trọng với chữ ký, cache hoặc ứng dụng. Không tự sắp xếp lại nếu giao thức không quy định.
3. Giá trị rỗng (`x=`) khác với khóa không được truyền; quy ước xử lý cả `x` (không có dấu `=`) cũng tùy ứng dụng.
4. `getRawQuery()` giữ dấu `%` cùng mã hóa; `getQuery()` giải mã percent-encoding, nhưng **không tự biến dấu `+` thành khoảng trắng** theo quy ước form. Đừng decode toàn bộ query trước khi xác định cặp/giá trị: `%26` có thể được biến thành `&` rồi bị tách nhầm.
5. Dấu `?` đầu tiên phân định query của URI phân cấp; các ký tự dành riêng muốn đóng vai trò *dữ liệu* phải được mã hóa phù hợp ngữ cảnh.

Ví dụ với một tham số có giá trị `C++ & Java` theo dạng `application/x-www-form-urlencoded`:

~~~text
Giá trị gốc:        C++ & Java
Giá trị form-encode: C%2B%2B+%26+Java
Query:              q=C%2B%2B+%26+Java
~~~

Ở đây `%2B` là dấu cộng thật, `+` biểu diễn khoảng trắng **theo quy tắc form**, `%26` là ký tự `&` trong **giá trị**, không phải dấu ngăn hai tham số. `URLEncoder`/`URLDecoder` của Java dành cho định dạng form này; chúng **không phải** hàm encode/decode tùy ý cho toàn bộ URI, path hay fragment.

## 7. Fragment: phần sau `#`, thường dành cho client

Trong `https://example.org/docs?lang=vi#installation`:

- `query` = `lang=vi`.
- `fragment` = `installation`.

Fragment có thể giúp trình duyệt nhảy đến vị trí trong HTML hoặc ứng dụng client định vị một phần tài nguyên theo quy ước riêng. Khi trình duyệt truy cập URL HTTP(S) thông thường, **fragment không nằm trong HTTP request-target gửi tới server**. Server nhận phần path/query phù hợp, còn browser dùng fragment trong ngữ cảnh tài liệu. Vì vậy đừng thiết kế tính năng server phụ thuộc vào việc nhận fragment qua request URL.

`URI.getRawFragment()` giữ dạng mã hóa; `getFragment()` giải mã. Fragment có thể không tồn tại (`null`) hoặc được viết rỗng trong chuỗi. Nếu muốn ký tự `#` xuất hiện trong **giá trị query/path**, phải mã hóa nó theo thành phần tương ứng (thường `%23`), nếu không phần sau sẽ được hiểu là fragment.

Lưu ý: fragment vẫn có thể xuất hiện trong history, log ở client hoặc các đoạn mã JavaScript. Không coi việc fragment không được gửi trong HTTP request-target là bảo đảm bí mật tuyệt đối.

## 8. URI phân cấp, URI opaque, URI tuyệt đối và tham chiếu tương đối

Cần tách hai câu hỏi độc lập:

- **Absolute hay relative?** Có scheme hay không? `https://example.org/docs` là absolute URI; `../docs` và `//cdn.example.org/lib.js` là reference tương đối theo cách dùng với base URI. Một reference bắt đầu bằng `//` có authority nhưng chưa có scheme.
- **Hierarchical hay opaque?** `https://example.org/docs` là hierarchical; `mailto:team@example.org` là opaque theo cách phân loại của `java.net.URI`. Ở opaque URI, phần sau dấu `:` được xem là scheme-specific part chứ không mặc định tách thành host/port/path như HTTP URL.

| Ví dụ | Đặc điểm cần nhớ |
| --- | --- |
| `https://example.org/a?q=1#p` | Absolute, hierarchical, có authority/query/fragment |
| `/a/b` | Relative reference có path tuyệt đối theo server gốc, không có scheme |
| `../b` | Relative path reference, cần base để xác định đích |
| `//cdn.example.org/a.js` | Reference có authority nhưng không có scheme; nhận scheme từ base khi resolve |
| `#part` | Reference chỉ thay fragment khi resolve trong ngữ cảnh base |
| `mailto:team@example.org` | Absolute nhưng opaque; không trích host như HTTPS |
| `urn:isbn:9780000000000` | Absolute, opaque theo cấu trúc Java URI |

### 8.1. Resolve và normalize

Với base `https://example.org/docs/guide/index.html`:

~~~text
resolve("lesson.html") -> https://example.org/docs/guide/lesson.html
resolve("../api.html") -> https://example.org/docs/api.html
resolve("/assets/x.css") -> https://example.org/assets/x.css
~~~

Base kết thúc bằng tên file được xử lý khác với base kết thúc bằng `/`. Ví dụ với `https://example.org/docs/guide/`, `resolve("lesson.html")` đi đến `/docs/guide/lesson.html`. Luôn thử các trường hợp có/không có slash cuối khi thiết kế đường dẫn.

`resolve()` ghép URI theo quy tắc reference, `normalize()` đơn giản hóa một số segment; cả hai **không gọi HTTP/DNS**. Nếu base hoặc reference đến từ nguồn không đáng tin cậy, kết quả `resolve()` vẫn có thể chuyển sang host khác qua reference `//attacker.example/...` hoặc một absolute URI mới. Đừng mặc định nó giữ nguyên domain.

## 9. Java 17+: đọc đủ các thành phần và dựng query đúng

Java có hai kiểu quan trọng:

- `java.net.URI` đại diện một URI/reference theo cú pháp; dùng để parse, so sánh, resolve, normalize, inspect và tạo URI. `URI.create(String)` ném `IllegalArgumentException` nếu chuỗi không hợp lệ (nguyên nhân thường là `URISyntaxException`); `new URI(String)` ném `URISyntaxException` có kiểm tra.
- `java.net.URL` gắn với một cơ chế truy cập tài nguyên theo scheme/handler. Việc chuyển `uri.toURL()` chỉ có nghĩa với URI tuyệt đối và handler hỗ trợ; không phải URI nào cũng trở thành URL truy cập mạng. Các thao tác sử dụng connection/stream từ URL mới có thể thực hiện I/O. Khi chỉ phân tích cấu trúc, hãy ưu tiên `URI`.

### 9.1. Ví dụ hoàn chỉnh có thể chạy

Tạo file **UriPartsDemo.java** bằng UTF-8:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriPartsDemo {
    public static void main(String[] args) {
        URI uri = URI.create(
                "https://reader@example.org:8443/docs/java%20networking"
                + "?lang=vi&tag=uri#basics");

        System.out.println("scheme         = " + uri.getScheme());
        System.out.println("authority      = " + uri.getRawAuthority());
        System.out.println("user-info      = " + uri.getRawUserInfo());
        System.out.println("host           = " + uri.getHost());
        System.out.println("port           = " + uri.getPort());
        System.out.println("path(raw)      = " + uri.getRawPath());
        System.out.println("path(decoded)  = " + uri.getPath());
        System.out.println("query(raw)     = " + uri.getRawQuery());
        System.out.println("fragment(raw)  = " + uri.getRawFragment());

        URI base = URI.create("https://example.org/guide/");
        System.out.println("resolved       = " + base.resolve("intro.html"));

        // URLEncoder dành cho *giá trị tham số form*, không phải path.
        String term = "C++ & Java";
        String encoded = URLEncoder.encode(term, StandardCharsets.UTF_8);
        URI search = URI.create(
                "https://example.org/search?q=" + encoded);
        System.out.println("query(form)    = " + search.getRawQuery());

        // Chỉ decode GIÁ TRỊ đã tách từ raw query.
        String rawValue = search.getRawQuery().substring("q=".length());
        System.out.println("form decoded   = " + URLDecoder.decode(
                rawValue, StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UriPartsDemo.java
java UriPartsDemo
~~~

Stdout:

~~~text
scheme         = https
authority      = reader@example.org:8443
user-info      = reader
host           = example.org
port           = 8443
path(raw)      = /docs/java%20networking
path(decoded)  = /docs/java networking
query(raw)     = lang=vi&tag=uri
fragment(raw)  = basics
resolved       = https://example.org/guide/intro.html
query(form)    = q=C%2B%2B+%26+Java
form decoded   = C++ & Java
~~~

Giải thích các điểm quan trọng trong kết quả:

1. `getRawAuthority()` gồm user-info, host và port; `getHost()` chỉ lấy host.
2. `getRawPath()` giữ `%20`, trong khi `getPath()` cho chuỗi có khoảng trắng. **Dạng decoded không còn là chuỗi URI an toàn để copy y nguyên vào đường dẫn mới.**
3. `getRawQuery()` không chứa `?`; `getRawFragment()` không chứa `#`.
4. `resolve()` dùng base kết thúc `/` nên chèn `intro.html` ngay sau thư mục `/guide/`.
5. `URLEncoder` mã hóa từng giá trị theo form; `URLDecoder` khôi phục từ đúng giá trị đã tách. Không cần socket hay Internet để chạy chương trình này.

### 9.2. Dựng URI từ các thành phần, hạn chế nối chuỗi tùy tiện

Khi có các thành phần **chưa được percent-encode**, constructor theo thành phần giúp tránh lỗi khoảng trắng hoặc ký tự đặc biệt ngoài ý muốn:

~~~java
// Đoạn minh họa khi đã import java.net.URI.
URI built = new URI(
        "https",              // scheme
        null,                 // userInfo
        "example.org",        // host
        8443,                 // port
        "/tai lieu/huong dan",// path chưa encode
        "lang=vi",            // query chưa encode
        "muc 1"               // fragment chưa encode
);
System.out.println(built.toASCIIString());
~~~

Đoạn trên dùng constructor 7 tham số, có thể ném `URISyntaxException`; khi đưa vào phương thức `main` cần khai báo/handle exception. Constructor tự quote các ký tự không hợp lệ theo ngữ cảnh thành phần. **Đừng truyền chuỗi đã percent-encode một cách tùy tiện**: dấu `%` có thể bị encode tiếp thành `%25`. Riêng query gồm nhiều tham số cần xử lý **từng tên và giá trị** theo chuẩn dữ liệu ứng dụng trước khi ghép dấu `&`/`=`, thay vì nghĩ constructor sẽ tự hiểu một map tham số.

Khi cần URL HTTP từ URI đã kiểm tra, có thể dùng `uri.toURL()` rồi dùng thư viện HTTP phù hợp. Với HTTP client Java 11+, `HttpRequest.newBuilder(uri)` dùng `URI` trực tiếp; code HTTP thực tế vẫn cần kiểm tra scheme, host, port, timeout, redirects và chính sách bảo mật trước khi gọi mạng.

## 10. Percent-encoding, Unicode và khác biệt raw/decoded

URI có bộ ký tự cú pháp giới hạn. Percent-encoding biểu diễn từng **byte** dưới dạng `%HH` (hai chữ số hex), ví dụ:

| Dữ liệu hoặc ký tự | Dạng thường gặp | Điều cần hiểu |
| --- | --- | --- |
| Space trong path | `%20` | Không dùng dấu cách thô trong URI string |
| Dấu `#` muốn làm dữ liệu | `%23` | Dấu `#` thô bắt đầu fragment |
| Dấu `?` muốn làm dữ liệu trong path | `%3F` | Dấu `?` thô chuyển sang query |
| Dấu `&` trong giá trị form | `%26` | Không bị hiểu nhầm là dấu phân cách cặp |
| Dấu `+` thật trong giá trị form | `%2B` | Không bị coi thành khoảng trắng khi form decode |
| Dấu `%` thật | `%25` | Tránh percent sequence không hợp lệ |

Với ký tự Unicode như `ữ` hoặc emoji, thường phải chuyển thành byte UTF-8 rồi percent-encode các byte không được viết trực tiếp trong URI ASCII; không thể đơn giản thay một ký tự bằng một escape `%HH` duy nhất nếu UTF-8 của nó nhiều byte. `URI.toASCIIString()` hữu ích khi cần biểu diễn ASCII của URI có ký tự quốc tế hợp lệ.

Phải phân biệt ba lớp:

1. **Chuỗi URI thô:** có delimiters và percent-encoded bytes, ví dụ `/a%2Fb`.
2. **Giá trị component sau percent decode:** có thể là `/a/b`; nếu giải mã trước khi tách segment, ký tự `%2F` sẽ mất dấu hiệu “nó từng được encode”.
3. **Ngữ nghĩa riêng của giao thức/ứng dụng:** một số server/router quyết định xử lý slash encoded, dấu chấm, key lặp và query parameters theo cách riêng.

Một lỗi nguy hiểm là **double decoding**: `%252F` được percent-decode một lần thành `%2F`; decode lần nữa thành `/`. Nếu các tầng bảo mật và router giải mã khác nhau, dữ liệu có thể được diễn giải ngoài dự kiến. Thiết kế cần thống nhất thời điểm và số lần decode, đồng thời validate trên cùng dạng mà hệ thống định tuyến thực sự sử dụng.

## 11. Các trường hợp đặc biệt và lỗi phổ biến

| Trường hợp | Diễn giải đúng | Lỗi dễ gặp |
| --- | --- | --- |
| `https://example.org` | Không có port tường minh; path không tự là `/` trong chuỗi đầu vào | Tưởng `getPort() == 443` |
| `https://example.org:8443/p` | Authority có host và port | So sánh cả authority với hostname |
| `https://[2001:db8::1]:443/p` | IPv6 literal trong ngoặc vuông | Tách host và port bằng `split(":")` |
| `https://example.org/p?q=%23#t` | Query có `%23`; fragment là `t` | Coi `%23` là dấu `#` phân cách |
| `https://example.org/a%2Fb` | Raw path có encoded slash | Decode path rồi tự tách slash không theo chính sách |
| `https://example.org/search?q=a+b` | Trong query raw, `+` là literal; trong quy ước form, `+` mang nghĩa space | Nghĩ `URI.getQuery()` tự form-decode |
| `https://example.org/a#top` | Fragment cho phía client/ngữ cảnh tài nguyên | Mong HTTP server nhận `#top` |
| `mailto:user@example.org` | Opaque URI không có HTTP host/path | Gọi `getHost()` rồi mặc định không null |
| `../image.png` | Relative reference, cần base | Dùng như absolute URL không có ngữ cảnh |
| `https://user:secret@example.org/` | User-info có nguy cơ lộ credentials | Log hoặc chia sẻ nguyên URI |

**Không parse URI bằng `split("://")`, `split("@")`, `split(":")` hoặc regex đơn giản.** Ví dụ IPv6 có nhiều dấu hai chấm, user-info có cú pháp escape và các scheme không dùng `//`. Sử dụng `URI`, rồi kiểm tra những thành phần phù hợp với giao thức của bạn.

**Không coi `URI.normalize()` là canonicalization đầy đủ.** Nó không tự quy đổi hostname về cùng dạng DNS, không tự xóa default port, không tự sắp xếp query, không áp đặt quy tắc riêng của ứng dụng. Khi so sánh URI cho cache key hoặc chữ ký, cần đặc tả canonicalization rõ ràng ở tất cả các bên.

**Đừng dùng `URI.getHost() != null` làm kiểm tra URL an toàn duy nhất.** Với URL nhận từ người dùng và tính năng tải tài nguyên từ máy chủ, cần giới hạn scheme, host/cổng, địa chỉ IP sau phân giải, mạng nội bộ, redirect và đường đi thực tế. Đừng kiểm tra host bằng chuỗi con của authority hoặc `startsWith("https://trusted.example")`; chuỗi như `https://trusted.example.attacker.invalid` có thể qua mặt cách kiểm tra sai. Log nên che user-info, token query và dữ liệu nhạy cảm.

## 12. Bài thực hành tự kiểm tra

### Bài 1: Tách một URI thành bảy phần

Cho:

~~~text
https://api.example.org:9443/v1/items/42?include=price&lang=vi#details
~~~

Hãy chỉ ra scheme, authority, host, port, path, query, fragment. Đáp án:

| Thành phần | Giá trị |
| --- | --- |
| scheme | `https` |
| authority | `api.example.org:9443` |
| host | `api.example.org` |
| port | `9443` |
| path | `/v1/items/42` |
| query | `include=price&lang=vi` |
| fragment | `details` |

Không có user-info. Chú ý client HTTP không gửi `#details` làm request-target.

### Bài 2: Phân biệt đường dẫn và form query

Cho giá trị tìm kiếm `a+b & c`. Hãy tạo tham số `q` bằng `URLEncoder.encode(value, UTF_8)` và đưa vào query. Kết quả value encoded là `a%2Bb+%26+c`. Nếu `+` là ký tự thật nhưng bị giữ nguyên trong chuỗi form query, `URLDecoder` sẽ diễn giải nhầm thành khoảng trắng.

### Bài 3: Dự đoán kết quả Java

~~~java
URI base = URI.create("https://example.org/docs/start.html");
System.out.println(base.resolve("next.html"));
System.out.println(base.resolve("../home.html"));
System.out.println(URI.create("https://example.org").getPort());
~~~

Đây là đoạn code minh họa đặt trong chương trình đã import `java.net.URI`. Kết quả dự kiến:

~~~text
https://example.org/docs/next.html
https://example.org/home.html
-1
~~~

Lời giải: relative reference không bắt đầu `/` thay thế segment cuối của path ở base; `..` đi lên thư mục cha; không có port tường minh nên `getPort()` trả `-1`.

## 13. Checklist dùng URI/URL trong ứng dụng Java

- [ ] Đã xác định scheme được phép và URI có **absolute/hierarchical** đúng nhu cầu?
- [ ] Đã tách **authority** khỏi **host**, xử lý user-info, IPv6 và port tường minh/port mặc định đúng?
- [ ] Path được thao tác theo raw/decoded nhất quán, không decode slash hoặc dot segment nhiều lần?
- [ ] Query đã encode **từng giá trị** đúng quy ước của dịch vụ, xử lý được key lặp và ký tự `&`, `=`, `+`?
- [ ] Fragment có được hiểu là dữ liệu phía client, không trông đợi backend HTTP nhận nó?
- [ ] Relative reference được resolve với base phù hợp, kể cả base có/không có slash cuối?
- [ ] URI được xây dựng qua API thành phần/encoder thích hợp, tránh double-encode `%`?
- [ ] Nếu URI đến từ nguồn không tin cậy, đã kiểm tra host/cổng/IP/redirect và che thông tin nhạy cảm?

Điểm cốt lõi: **URI có cú pháp phân tách chung, nhưng ngữ nghĩa của từng phần phụ thuộc scheme và giao thức ứng dụng.** Khi nắm chắc ranh giới giữa scheme, authority, host, port, path, query và fragment, bạn sẽ đọc đúng địa chỉ mạng, dùng `java.net.URI` hiệu quả và tránh sai sót khó phát hiện khi lập trình Java.