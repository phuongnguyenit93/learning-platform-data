# URI và URL: phân biệt định danh tài nguyên với khả năng truy cập

## 1. Bài toán: biết một tài nguyên là gì khác với biết truy cập nó ở đâu

Một ứng dụng mạng phải trả lời hai câu hỏi có liên quan nhưng không giống nhau:

- **Định danh:** Chuỗi nào cho phép các bên nói về cùng một tài nguyên? Ví dụ “tài liệu hướng dẫn Java”, “một cuốn sách theo ISBN”, “hồ sơ số 42”.
- **Định vị/truy cập:** Với thông tin đang có, ứng dụng có thể dùng cơ chế nào để tìm, truy cập hoặc tương tác với tài nguyên? Ví dụ HTTPS đến một host và đường dẫn cụ thể.

**URI (Uniform Resource Identifier)** là khái niệm bao quát: một chuỗi ký tự dùng để **định danh tài nguyên** theo một cú pháp chung. **URL (Uniform Resource Locator)** là cách gọi quen thuộc cho **nhóm URI có thông tin về cơ chế truy cập/vị trí của tài nguyên**, chẳng hạn `https://docs.example.org/guide`. Theo cách phân biệt trong RFC 3986, URL là **một tập con của URI**. Vì vậy, một địa chỉ web HTTPS thường **vừa là URI vừa là URL**; đây không phải hai loại loại trừ nhau.

Một **tài nguyên** có thể là trang web, API endpoint, ảnh, dịch vụ, tài liệu hay một khái niệm trừu tượng. URI định danh tài nguyên, nhưng **không bắt buộc** chứa nội dung tài nguyên, và không bảo đảm rằng tại thời điểm hiện tại ai cũng có thể truy cập tài nguyên đó. Một URL vẫn là URL nếu máy chủ tạm thời ngừng hoạt động, tài nguyên yêu cầu đăng nhập, trả lỗi 404 hoặc chuyển hướng sang địa chỉ khác.

Mục tiêu sau bài này:

1. Phân biệt URI với URL theo **mục đích định danh** và **thông tin truy cập**, không đồng nhất hai tên gọi.
2. Phân tích scheme, authority, host, path, query và fragment trên URI phổ biến.
3. Phân biệt URI tuyệt đối, tham chiếu URI tương đối và URN.
4. Dùng `java.net.URI` và `java.net.URL` đúng vai trò; biết lúc nào mới thực sự phát sinh giao tiếp mạng.
5. Tránh các lỗi xử lý encoding, ghép đường dẫn và dùng URI/URL từ dữ liệu không tin cậy.

## 2. Bốn khái niệm dễ bị trộn lẫn

| Khái niệm | Câu hỏi chính | Ví dụ | Điểm quan trọng |
|---|---|---|---|
| **Resource** (tài nguyên) | “Đối tượng nào đang được nhắc tới?” | Một trang hướng dẫn Java, một đơn hàng | Tài nguyên là đối tượng được định danh; nội dung trả về có thể là một **biểu diễn** của tài nguyên |
| **URI** | “Dùng tên/chuỗi nào để định danh đối tượng?” | `urn:isbn:9780134685991` hoặc `https://docs.example.org/guide` | URI có thể định danh bằng tên hoặc thông tin định vị |
| **URL** | “URI này nêu cách/vị trí truy cập nào?” | `https://docs.example.org/guide` | Thường có scheme truy cập và thông tin vị trí; **không bảo đảm** truy cập thành công |
| **URN** (Uniform Resource Name) | “Tên định danh trong không gian tên là gì?” | `urn:isbn:9780134685991` | Một kiểu URI thiên về tên định danh; bản thân chuỗi URN không nói phải gửi HTTP tới máy chủ nào |

**Ví dụ:** `urn:isbn:9780134685991` định danh một ấn phẩm theo không gian tên ISBN; nó không cung cấp host HTTP cụ thể để tải nội dung. Trong khi đó `https://catalog.example.org/books/9780134685991` vừa định danh tài nguyên trong hệ thống catalog vừa cho biết phương thức HTTPS và vị trí truy cập mà một client có thể thử sử dụng.

Không nên diễn đạt “URI chỉ là tên logic, URL chỉ là địa chỉ vật lý”: URL **cũng là một định danh**, và host/path trong URL có thể là địa chỉ logic đứng trước reverse proxy, load balancer hoặc hệ thống định tuyến động. “Địa chỉ web” không nhất thiết tương đương một máy chủ vật lý cố định.

### Những ví dụ cần phân loại

| Chuỗi | Phân loại hợp lý | Giải thích |
|---|---|---|
| `https://example.org/articles/42` | URI tuyệt đối; thường gọi là URL | Scheme HTTPS + thông tin định vị host/path |
| `http://localhost:8080/api/books` | URI tuyệt đối; URL | HTTP tới cổng 8080 của máy chạy client; không nhất thiết truy cập được ngoài máy đó |
| `urn:isbn:9780134685991` | URI tuyệt đối, dạng URN | Có scheme `urn` và tên theo namespace; không phải URL web |
| `mailto:team@example.org` | URI tuyệt đối theo scheme `mailto` | Chỉ ra cách diễn giải địa chỉ thư; không phải HTTP endpoint và không có host theo cấu trúc URI HTTPS |
| `../images/logo.svg` | Tham chiếu URI tương đối | Không có scheme; cần URI gốc (base URI) để giải quyết |
| `/api/orders/42` | Tham chiếu URI có path bắt đầu bằng `/` | Path bắt đầu từ gốc của authority hiện tại nhưng **vẫn chưa phải URI tuyệt đối theo nghĩa có scheme** |
| `#faq` | Tham chiếu chỉ có fragment | Trỏ đến một phần/ngữ cảnh trong tài nguyên cơ sở |
| `example.org/docs` | Chuỗi có thể được diễn giải như path tương đối | Không tự là URL HTTPS; việc trình duyệt tự thêm `https://` là chính sách giao diện, không phải quy tắc chung của URI |

Trong Java, `URI.isAbsolute()` kiểm tra **có scheme hay không**. Do đó `https://example.org/x` và `urn:isbn:...` đều absolute; còn `/api/x` và `../x` đều relative URI references.

## 3. Cấu trúc một URI phân cấp (hierarchical URI)

Với URL web phổ biến:

```text
https://user@example.org:8443/docs/java/index.html?lang=vi&mode=short#install
\___/   \__/ \_________/ \__/ \__________________/ \________________/ \_____/
scheme userinfo  host    port         path               query       fragment
        \___________________ authority ___________________/
```

Cấu trúc tổng quát thường dùng của URI phân cấp là:

```text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
```

**Đây là một dạng thông dụng, không phải toàn bộ cú pháp URI.** Không phải URI nào cũng có `//authority`: `urn:isbn:...` và `mailto:...` là những ví dụ có scheme nhưng không có cấu trúc host/path như HTTPS.

- **Scheme:** nhãn đầu URI trước dấu `:`, ví dụ `https`, `http`, `ftp`, `urn`, `mailto`. Scheme xác định cách diễn giải phần còn lại; **có scheme không đồng nghĩa là có thể truy cập mạng ngay**.
- **Authority:** phần sau `//` (nếu có), thường chứa `[userinfo@]host[:port]`. Với HTTP(S), host biểu thị tên miền hoặc địa chỉ máy chủ; port chọn endpoint dịch vụ. Đưa username/password vào URL là cách làm không an toàn và không nên dùng.
- **Path:** định danh đường dẫn trong không gian của authority, ví dụ `/docs/java/index.html`. Path không nhất thiết là đường dẫn file vật lý trên server; có thể được định tuyến tới controller/handler.
- **Query:** phần sau `?`, ví dụ `lang=vi&mode=short`. Dạng cặp key/value nối bằng `&` là **quy ước thường gặp của web**, không phải mọi query URI đều bắt buộc tuân theo định dạng đó. Server quyết định ý nghĩa query.
- **Fragment:** phần sau `#`, ví dụ `install`. Nó định danh một phần hoặc vị trí bên trong biểu diễn tài nguyên; với HTTP thông thường, **fragment không được gửi trong request-target tới server**.
- **User info:** một phần tùy chọn của authority; nhiều API hiện đại không dùng và nên tránh nhúng credential trong URL.

### Cùng URL, các lớp có thể xử lý những phần khác nhau

Khi mở `https://docs.example.org/guide?lang=vi#install`, browser dùng host để tìm endpoint, giao tiếp bằng HTTPS và yêu cầu resource ứng với path + query. Fragment `install` thường được xử lý ở client để điều hướng trong nội dung đã nhận. Yêu cầu HTTP/1.1 về mặt khái niệm có dạng:

```http
GET /guide?lang=vi HTTP/1.1
Host: docs.example.org
Accept: text/html

```

Dòng yêu cầu **không chứa** `#install`. Trong thực tế, HTTP/2 và HTTP/3 có cách biểu diễn message khác HTTP/1.1, nhưng fragment vẫn không phải thành phần của request-target gửi qua HTTP.

**Không đồng nhất URL với một response duy nhất:** cùng URL có thể trả HTML/JSON, ngôn ngữ hoặc dữ liệu khác nhau theo header `Accept`, quyền người dùng, thời điểm hay trạng thái server. URI định danh một resource; response là **representation** tại một thời điểm/ngữ cảnh.

## 4. URI tuyệt đối, tham chiếu tương đối và thao tác resolve

Một **absolute URI** có scheme, ví dụ `https://docs.example.org/guide`. Một **relative reference** như `chapter/1` hoặc `../intro.html` dựa vào một **base URI** để tạo đích cuối cùng. Cơ chế này xuất hiện trong HTML links, API links, tài nguyên tĩnh và xử lý tài liệu.

Giả sử base là `https://docs.example.org/guides/java/`:

| Tham chiếu | Kết quả khi resolve với base | Vì sao |
|---|---|---|
| `../intro.html` | `https://docs.example.org/guides/intro.html` | `..` đi lên một cấp path |
| `examples/demo.html` | `https://docs.example.org/guides/java/examples/demo.html` | Ghép dưới thư mục hiện tại |
| `/about` | `https://docs.example.org/about` | Path bắt đầu từ gốc của authority |
| `?lang=vi` | Có thể thay query trên cơ sở current path; cần kiểm tra semantics của API đang dùng | Tham chiếu chỉ có query có quy tắc resolve riêng, không phải “nối chuỗi” |
| `https://another.example.org/start` | `https://another.example.org/start` | Tham chiếu đã có scheme, không kế thừa host của base |

**Một điểm kỹ thuật trong Java:** `URI.resolve` tuân theo quy tắc triển khai của `java.net.URI`; với những dạng tham chiếu đặc biệt (đặc biệt query-only), không giả định logic ghép chuỗi theo trực giác. Khi xây request quan trọng, hãy kiểm tra URI kết quả bằng các trường `getScheme()`, `getHost()`, `getRawPath()`, `getRawQuery()`, và test những ca edge-case của ứng dụng.

### Không ghép URI bằng phép cộng chuỗi tùy tiện

Ví dụ cơ sở `https://api.example.org/v1` và đường dẫn `users`:

- Nối chuỗi trực tiếp có thể cho ra `https://api.example.org/v1users`.
- Nếu base là `https://api.example.org/v1` (không có dấu `/` cuối) thì giải quyết relative `users` có thể thay thế đoạn `v1`, cho ra `https://api.example.org/users`.
- Nếu mục tiêu là thư mục `/v1/`, base nên được định nghĩa rõ `https://api.example.org/v1/`; khi đó resolve `users` sẽ cho `https://api.example.org/v1/users`.

Dấu slash cuối trong base URI **có ý nghĩa**. `URI.normalize()` hỗ trợ xử lý các đoạn `.` và `..` trong path, nhưng không “biết” business route nào là đúng; cũng không phải bộ lọc bảo mật cho input không tin cậy.

## 5. URI và URL trong thư viện chuẩn Java

Hai lớp quen thuộc là `java.net.URI` và `java.net.URL`. Chúng giải quyết những nhiệm vụ khác nhau:

| `java.net.URI` | `java.net.URL` |
|---|---|
| Biểu diễn và thao tác với **định danh/cú pháp URI** | Biểu diễn một URL với scheme/protocol mà runtime hỗ trợ |
| Có thể chứa tham chiếu relative hoặc scheme như `urn` | Phù hợp khi cần chuyển tới API thao tác URL/connection |
| Có `parse/create`, `resolve`, `normalize`, `getScheme`, `getHost`, `getPath`, `getRawQuery`, `getFragment` | Có `getProtocol`, `getHost`, `getPort` và API kết nối như `openConnection` |
| Tạo/phân tích `URI` **không tự phát sinh truy cập mạng** | Tạo/đổi một `URL` không tự tải resource; **mở kết nối/đọc dữ liệu** mới có thể gây I/O |
| `equals/hashCode` được định nghĩa theo cú pháp URI (với một số quy tắc chuẩn hóa so sánh) | `URL.equals/hashCode` có hành vi lịch sử có thể liên quan phân giải host, không thích hợp làm khóa định danh web ổn định |

Trong mã Java mới, thường **giữ URI để phân tích, validate, lưu và truyền vào HTTP client**. Khi cần `URL` cho API cũ, chuyển từ URI hợp lệ qua `uri.toURL()`. Đối với HTTP client hiện đại (Java 11+), `java.net.http.HttpRequest` nhận `URI`; không cần chuyển sang `URL`.

**Ba thao tác khác nhau:**

1. `URI.create("https://example.org/a")`: tạo đối tượng và kiểm tra cú pháp (sai cú pháp sẽ lỗi), không gửi network request.
2. `uri.toURL()`: chuyển sang URL nếu hợp lệ và giao thức được hỗ trợ; bản thân thao tác này không tải nội dung.
3. `HttpClient.send(...)` hoặc `URL.openStream()`: thực hiện giao tiếp/đọc dữ liệu; có thể gặp DNS failure, connection refused, timeout, TLS errors, HTTP status lỗi…

Một URI hợp cú pháp không bảo đảm URL truy cập được. Đặc biệt, `URI.create("urn:isbn:...")` là URI hợp lệ, nhưng không thể coi nó là URL HTTP và gửi trực tiếp bằng `HttpClient`.

## 6. Java 17+: ví dụ đầy đủ, chạy hoàn toàn offline

Chương trình sau chỉ tạo, resolve và phân tích URI/URL; **không kết nối Internet**. Cách này giúp thấy rõ ranh giới giữa định danh và truy cập.

Tạo file **`UriUrlDemo.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriUrlDemo {
    public static void main(String[] args) throws Exception {
        URI base = URI.create("https://docs.example.org/guides/java/");
        URI relative = URI.create("../intro.html?lang=vi#toc");
        URI resolved = base.resolve(relative).normalize();

        System.out.println("Relative absolute: " + relative.isAbsolute());
        System.out.println("Resolved: " + resolved);
        System.out.println("Scheme: " + resolved.getScheme());
        System.out.println("Host: " + resolved.getHost());
        System.out.println("Path: " + resolved.getPath());
        System.out.println("Query: " + resolved.getQuery());
        System.out.println("Fragment: " + resolved.getFragment());

        URI urn = URI.create("urn:isbn:9780134685991");
        System.out.println("URN absolute: " + urn.isAbsolute());
        System.out.println("URN opaque: " + urn.isOpaque());

        URL url = resolved.toURL(); // chỉ chuyển kiểu, không mở kết nối
        System.out.println("URL protocol: " + url.getProtocol());

        URI escaped = URI.create(
                "https://docs.example.org/search?q=caf%C3%A9%20Java");
        System.out.println("Raw query: " + escaped.getRawQuery());
        System.out.println("Decoded query: " + escaped.getQuery());

        String encodedFormValue = URLEncoder.encode(
                "cà phê", StandardCharsets.UTF_8);
        System.out.println("Form value: " + encodedFormValue);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 UriUrlDemo.java
java UriUrlDemo
```

Kết quả:

```text
Relative absolute: false
Resolved: https://docs.example.org/guides/intro.html?lang=vi#toc
Scheme: https
Host: docs.example.org
Path: /guides/intro.html
Query: lang=vi
Fragment: toc
URN absolute: true
URN opaque: true
URL protocol: https
Raw query: q=caf%C3%A9%20Java
Decoded query: q=café Java
Form value: c%C3%A0+ph%C3%AA
```

**Giải thích từng phần:**

- `relative.isAbsolute()` là `false` vì tham chiếu `../intro.html?lang=vi#toc` chưa có scheme.
- `base.resolve(relative)` giải quyết `..` so với path của base, kết quả thành URI HTTPS tuyệt đối. `normalize()` xử lý các đoạn path dạng `.`, `..` còn sót theo ngữ nghĩa URI.
- `getScheme()` trả `https`; `getHost()` trả host trong authority; `getPath()` là path (không có query/fragment).
- `getFragment()` là `toc`. Nó có trong URI client xử lý, không phải phần của HTTP request-target thông thường.
- `urn.isAbsolute()` là `true` vì có scheme `urn:`; `urn.isOpaque()` là `true` vì đây là URI không phân cấp theo API Java. “Absolute” **không** đồng nghĩa “URL web”.
- `toURL()` tạo đối tượng URL tương ứng, **không tải** `intro.html`.
- `getRawQuery()` giữ phần trăm mã hóa, còn `getQuery()` trả chuỗi được giải mã. Vì vậy giá trị query raw và decoded khác nhau ngay cả khi chỉ một resource được định danh.
- `URLEncoder` phục vụ quy tắc `application/x-www-form-urlencoded` cho **giá trị form/query**: khoảng trắng trở thành `+`, ký tự UTF-8 được biểu diễn bằng percent encoding. Không dùng đầu ra `URLEncoder` cho nguyên URL hoặc toàn bộ path.

### Khi nào thực sự xảy ra truy cập mạng?

Ví dụ tiếp theo là **mã minh họa tích hợp**, không thuộc chương trình offline ở trên; nó đòi hỏi một endpoint thực sự tồn tại và cho phép client truy cập.

```java
// Bên trong một phương thức có thể throws IOException,
// InterruptedException; uri phải là URI HTTP(S) được phép truy cập.
java.net.http.HttpClient client =
        java.net.http.HttpClient.newHttpClient();
java.net.http.HttpRequest request =
        java.net.http.HttpRequest.newBuilder(uri).GET().build();
java.net.http.HttpResponse<String> response = client.send(
        request,
        java.net.http.HttpResponse.BodyHandlers.ofString());
int status = response.statusCode();
String body = response.body();
```

Tại đây, `newBuilder(uri)` mô tả yêu cầu; `client.send(...)` mới là thao tác giao tiếp mạng. Thông thường cần cấu hình timeout, xử lý lỗi, xác thực và giới hạn tài nguyên tùy ứng dụng. Dịch vụ có thể trả `404`/`401`/`500`; việc có một URI đúng cú pháp không ngăn những kết quả đó.

## 7. Encoding: ranh giới giữa chuỗi nhìn thấy và chuỗi truyền đi

Một URI có cú pháp giới hạn đối với các ký tự dành riêng như `/`, `?`, `#`, `&`, `=`, `%`. Khi dữ liệu có khoảng trắng hoặc ký tự Unicode, phải mã hóa đúng cho **thành phần** đang xây dựng.

**Percent encoding** biểu diễn một byte bằng `%HH` (hex). Ví dụ ký tự `é` trong UTF-8 trở thành byte `C3 A9`, viết trên URI là `%C3%A9`. Trong một query, `q=caf%C3%A9%20Java` có raw text khác với giá trị decoded `q=café Java`.

| Việc muốn làm | Cách nên làm |
|---|---|
| Đọc nguyên văn thành phần đã mã hóa | `getRawPath()`, `getRawQuery()`, `getRawFragment()` |
| Lấy giá trị đã được Java giải mã | `getPath()`, `getQuery()`, `getFragment()` |
| Tạo URI từ các thành phần **chưa encode** | Xem xét constructor nhiều tham số `new URI(scheme, userInfo, host, port, path, query, fragment)` hoặc URI builder đáng tin |
| Encode **giá trị form** | `URLEncoder.encode(value, UTF_8)`; sau đó mới ghép theo quy tắc form/query tương ứng |
| Encode toàn bộ URL bằng `URLEncoder` | **Sai mục đích:** nó có thể đổi `:`, `/`, `?`, `&` của cấu trúc URI thành dữ liệu form |

**Hai lỗi rất phổ biến:**

1. **Double encoding:** dữ liệu đã có `%20` lại bị encode thêm thành `%2520` vì ký tự `%` đổi thành `%25`. Tránh trộn “chuỗi đã mã hóa” với “giá trị thành phần chưa mã hóa”; chọn một API xây URI và quy ước đầu vào thống nhất.
2. **Nhầm mã hóa query và path:** trong form encoding, khoảng trắng dùng `+`; trong path URI, khoảng trắng thường dùng `%20`. Không lấy `URLEncoder` để tạo một path segment rồi mặc nhiên tin rằng mọi server sẽ giải mã `+` như dấu cách.

Cũng cần nhớ `getQuery()` trả về **toàn bộ query đã giải mã**, không tự phân tách các key/value. Nếu dữ liệu có `&`, `=` hoặc percent encoding, việc `split("&")`/`split("=")` một cách ngây thơ có thể làm mất thông tin. Hãy dùng parser hoặc thư viện đúng chuẩn query/form mà ứng dụng yêu cầu.

## 8. Phân biệt identity của resource với representation và endpoint thực thi

Trong API, `https://api.example.org/orders/42` là một URL có thể dùng để xác định resource “đơn hàng 42”. Nhưng:

- `GET /orders/42` có thể đọc biểu diễn của resource, chẳng hạn JSON.
- `PUT /orders/42` có thể yêu cầu thay thế trạng thái resource theo hợp đồng API.
- `DELETE /orders/42` có thể yêu cầu xóa resource.
- Cùng URL có thể được xử lý khác nhau theo **HTTP method** và quyền người dùng; URL tự nó không chứa toàn bộ ngữ nghĩa nghiệp vụ.
- Nếu server trả `301`/`302`/`307`/`308` redirect, đường dẫn truy cập kế tiếp có thể khác địa chỉ ban đầu; vẫn không có nghĩa URL ban đầu “không phải URL”.

**URL xác định nơi/cách client thử giao tiếp; API contract quyết định thao tác được hỗ trợ và nội dung trả về.** Muốn biết endpoint có thể truy cập thực tế hay không cần điều kiện runtime: DNS, routing, TCP/QUIC, TLS, quyền truy cập, trạng thái dịch vụ và HTTP response. Đó là vấn đề khác với việc phân tích chuỗi URI/URL.

Khi thiết kế, ưu tiên canonical URI ổn định, giới hạn việc thay đổi định danh tùy tiện; nếu cần đổi vị trí, sử dụng redirect hoặc cơ chế phát hiện địa chỉ phù hợp. Tuy nhiên, không mặc định một URL sẽ vĩnh viễn tồn tại, hoặc rằng cùng một URL luôn trả cùng byte nội dung.

## 9. Validation và an toàn khi nhận URI/URL từ bên ngoài

Một chuỗi có thể **hợp cú pháp URI** mà vẫn **không hợp lệ theo chính sách ứng dụng**. Ví dụ ứng dụng chỉ được gọi HTTPS tới `api.example.org`; khi đó phải xác thực scheme, host, port, đường dẫn và mục tiêu thực tế trước khi gửi request.

Những nguyên tắc thực hành:

1. **Parse trước, kiểm tra từng thành phần:** dùng `URI` rồi kiểm tra `getScheme()`, `getHost()`, `getPort()`; đừng chỉ so `startsWith("https://api.example.org")` vì `https://api.example.org.attacker.invalid` vẫn có cùng tiền tố.
2. **Tách dữ liệu khỏi cấu trúc URI:** encode dữ liệu ở đúng component; không đưa input chưa kiểm soát vào chuỗi `host`, `path` hay `query`.
3. **Không mặc định normalize là kiểm tra an toàn:** dot segments, percent encoding, encoded slash và cách proxy/server diễn giải path có thể khác nhau. Security checks phải đồng bộ với chính thành phần sẽ xử lý request.
4. **Chú ý redirects và DNS:** xác thực URL ban đầu là chưa đủ nếu HTTP client tự theo redirect đến host khác; với các tác vụ nhạy cảm, phải kiểm soát từng đích sau redirect và kết quả phân giải mạng để tránh SSRF.
5. **Không để bí mật trong URI:** URL thường xuất hiện trong history, log, monitoring, analytics, referer hoặc thông báo lỗi. Tránh đặt password/token nhạy cảm trong path/query nếu có cách thay thế phù hợp.
6. **Thiết lập timeout và xử lý lỗi theo lớp:** lỗi parse URI, lỗi DNS, lỗi kết nối/TLS và HTTP status là những kiểu thất bại khác nhau; không gộp tất cả thành “URL sai”.

Đây là lý do **“URI hợp lệ”**, **“URL được phép truy cập”** và **“request thành công”** là ba phép kiểm tra khác nhau.

## 10. Lỗi thường gặp và cách giải thích chính xác

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “URI là URL không có domain.” | URI là khái niệm bao quát; URI HTTPS có thể chứa domain và đồng thời là URL. |
| “Mọi URI đều có thể gọi qua HTTP.” | `urn:`, `mailto:` và relative reference không tự là endpoint HTTP(S). |
| “URL khác URI vì URL có thể gọi được còn URI không gọi được.” | Một URL là một URI định vị/truy cập; khả năng kết nối thực tế còn tùy hạ tầng, quyền và trạng thái dịch vụ. |
| “`/api/users` là absolute URI vì bắt đầu bằng `/`.” | Nó là path tuyệt đối trong authority, nhưng theo `URI.isAbsolute()` không absolute vì không có scheme. |
| “Fragment `#intro` được gửi lên server để route.” | HTTP request-target thông thường không gửi fragment; client thường tự xử lý fragment. |
| “`new URL(...)` hoặc `uri.toURL()` tự tải dữ liệu.” | Tạo/chuyển đối tượng không phải gửi HTTP request; I/O xảy ra khi mở kết nối và đọc/gửi dữ liệu. |
| “Cứ ghép `base + path` hoặc `URLEncoder` toàn chuỗi là đúng.” | Phải giải quyết relative reference đúng quy tắc và encode riêng từng component. |
| “Chuỗi pass `URI.create` là an toàn.” | Hợp lệ cú pháp không nói gì về chính sách truy cập, SSRF, auth hoặc tài nguyên có tồn tại hay không. |

## 11. Bài tập tự kiểm tra

1. **`https://example.org/a?x=1#top` là URI hay URL?** Cả hai. Đây là absolute URI với scheme HTTPS và có thông tin định vị nên thường được gọi là URL. Fragment `top` không nằm trong HTTP request-target.
2. **`urn:isbn:9780134685991` có `isAbsolute()==true` không? Có thể mở bằng `HttpClient` ngay không?** Có scheme `urn:` nên absolute, nhưng không phải HTTP(S) endpoint để `HttpClient` gửi yêu cầu.
3. **Base `https://example.org/docs/java/` + `../overview.html` thành gì?** `https://example.org/docs/overview.html`. Vì `..` lùi về thư mục `/docs/`.
4. **Nếu `URI.create(urlString)` không báo lỗi, tải resource có chắc thành công?** Không. Cần DNS/kết nối/bảo mật/quyền/server hoạt động và phản hồi phù hợp.
5. **`getQuery()` và `getRawQuery()` khác gì?** Giá trị đầu là dạng đã giải mã percent-encoding theo API URI, giá trị sau giữ text raw. Muốn phân tích tham số form còn cần quy tắc của định dạng query đang dùng.
6. **Tại sao `https://api.example.org.attacker.invalid` nguy hiểm nếu dùng `startsWith("https://api.example.org")`?** Chuỗi có tiền tố giống nhưng host là tên miền khác; phải parse rồi so chính xác thành phần host và kiểm soát redirect/đích mạng thực tế.

## 12. Ghi nhớ để áp dụng

- **URI = định danh tài nguyên. URL = trường hợp URI mô tả cơ chế/vị trí truy cập**; chúng có quan hệ tập con, không đối lập nhau.
- **Tên tài nguyên khác với đường truyền và trạng thái truy cập.** Một URI hợp cú pháp không bảo đảm có endpoint, có quyền hoặc có phản hồi thành công.
- **Với Java, ưu tiên `URI` để parse, resolve, normalize và validate;** chỉ chuyển sang `URL` khi API cần. `HttpClient` nhận `URI` để thực sự gửi HTTP(S).
- **Resolve và encoding phụ thuộc thành phần.** Dấu `/` cuối base, `?query`, `#fragment` và percent encoding đều có ngữ nghĩa riêng; tránh nối chuỗi không kiểm soát.
- **Kiểm tra truy cập là vấn đề runtime và bảo mật.** Phân tích URI đúng mới là bước đầu khi xây một client–server application tin cậy.

Tài liệu tham khảo: *RFC 3986 – Uniform Resource Identifier (URI): Generic Syntax*; JDK API `java.net.URI`, `java.net.URL`, `java.net.http.HttpClient`.