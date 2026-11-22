# Chuyển URI sang URL; hàm tạo URL cũ và hướng sử dụng theo phiên bản Java

## 1. Khi nào cần chuyển `URI` sang `URL`?

Trong `java.net`, **`URI` (Uniform Resource Identifier)** biểu diễn cú pháp định danh tài nguyên; **`URL` (Uniform Resource Locator)** còn gắn với cơ chế truy cập tài nguyên qua một *protocol handler*. Vì vậy, không phải mọi `URI` đều tạo được `URL`.

- `URI` có thể **tương đối**, ví dụ `docs/intro.html`, hoặc **tuyệt đối**, ví dụ `https://example.com/docs/intro.html`. Một URI tuyệt đối có `scheme`; một URI tương đối thì không.
- `URI` có thể là **opaque URI** như `urn:example:widget`; Java vẫn phân tích được cú pháp URI nhưng thường không có `URLStreamHandler` cho scheme đó.
- `URL` phải có giao thức được Java nhận diện qua handler. Các cách tạo URL đời cũ từ chuỗi có thể xử lý/kiểm tra dữ liệu không đồng nhất theo handler và **không phải bộ xác thực URI đầy đủ**.
- Việc tạo `URI` hoặc chuyển `URI.toURL()` **không tự tải trang web**; hành động mạng xảy ra khi gọi API mở kết nối, gửi yêu cầu HTTP hoặc đọc dữ liệu. Một số thao tác khác trên `URL` (đặc biệt `equals`/`hashCode`) có thể đụng đến phân giải tên máy.

**Quy trình khuyến nghị:** nhận/ghép URL dưới dạng `URI` → kiểm tra cú pháp, scheme và authority khi cần → giải quyết đường dẫn tương đối nếu có → **chỉ gọi `toURL()` tại ranh giới API thực sự yêu cầu `URL`**.

```text
Chuỗi / các thành phần URL
       |
       v
  new URI(...) hoặc URI.create(...)
       |
       +--> kiểm tra scheme / host / userinfo / path
       +--> baseUri.resolve(relativeUri), nếu cần
       |
       v
  absolute URI có protocol handler phù hợp
       |
       v
       uri.toURL() --------------------> URL
                                            |
                                            +--> API legacy cần URL/URLConnection
                                            +--> openStream(), connect... nếu thật sự cần I/O
```

Đối với HTTP từ Java 11 trở lên, `java.net.http.HttpRequest.newBuilder(URI)` nhận **`URI` trực tiếp**; nhiều ứng dụng không cần chuyển sang `URL`.

## 2. Quy tắc theo phiên bản Java

| Môi trường | Trạng thái API | Hướng sử dụng |
| --- | --- | --- |
| Java 8–19, gồm **Java 17** | Những constructor `new URL(...)` truyền thống còn được sử dụng và **chưa bị đánh dấu deprecated** theo API của các phiên bản này. `URI.toURL()` đã có từ rất lâu. | Với code mới, ưu tiên `URI` và `uri.toURL()` để chủ động phân tích/kiểm tra URI; duy trì constructor cũ khi cần tương thích mà chưa thể migrate. |
| **Java 20** | Tất cả **public constructors** của `java.net.URL` được gắn `@Deprecated(since="20")`. Java 20 bổ sung `URL.of(URI, URLStreamHandler)`. | Tránh viết thêm `new URL(...)`; dùng `URI.toURL()` thông thường, và cân nhắc `URL.of(...)` khi phải chỉ định custom handler. |
| **Java 21 trở lên** | Hướng dẫn từ Java 20 vẫn áp dụng: các constructor legacy vẫn bị đánh dấu deprecated trong các JDK hiện đại. | Tiếp tục dùng `URI` làm đầu vào chuẩn; sửa cảnh báo deprecation bằng việc thay cơ chế tạo URL, đồng thời kiểm thử sự khác biệt về parse/encode. |

**Deprecated ≠ đã bị loại bỏ:** một constructor bị gắn deprecation vẫn có thể biên dịch/chạy, nhưng code mới không nên phụ thuộc vào nó. Không khẳng định mọi constructor `URL` đã bị xóa khỏi JDK 20/21; sự thay đổi chính là cảnh báo và hướng thay thế. Cũng **không gọi `URL.of(...)` trong dự án build với `--release 17`**, vì API này chỉ xuất hiện từ Java 20.

Tại Java 20+, `URL.of(uri, null)` dùng handler mặc định nếu có, nhưng `uri.toURL()` vẫn là đường thông dụng và tương thích Java 17. `URL.of(uri, customHandler)` dành cho nhu cầu handler tùy chỉnh, không phải bước bắt buộc trong mọi lần chuyển đổi.

## 3. Ví dụ hoàn chỉnh: parse, ghép, resolve rồi chuyển sang URL (Java 17+)

**`UriToUrlDemo.java`**

```java
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;

public final class UriToUrlDemo {
    public static void main(String[] args)
            throws URISyntaxException, MalformedURLException {

        // 1. Chuỗi đã mã hóa phần có dấu cách bằng %20.
        URI parsed =
                new URI("https://example.com/a%20b?q=java%20networking");
        URL fromParsed = parsed.toURL();

        System.out.println("parsed: " + fromParsed);
        System.out.println("host: " + parsed.getHost());
        System.out.println("raw query: " + parsed.getRawQuery());
        System.out.println("decoded query: " + parsed.getQuery());

        // 2. Ghép các thành phần; constructor URI tự quote ký tự
        // không hợp lệ (ví dụ dấu cách trong path/query).
        URI composed = new URI("https", null, "example.com", 443,
                "/learn/java basics", "lang=vi VN", null);
        System.out.println("composed: " + composed.toURL());

        // 3. URI tương đối chỉ được chuyển sau khi resolve
        // dựa trên URI gốc tuyệt đối.
        URI relative = URI.create("guide/intro.html");
        URI base = URI.create("https://example.com/docs/");
        System.out.println("resolved: " + base.resolve(relative).toURL());

        // 4. Kiểm tra authority theo cấu trúc host/port của server.
        URI strict = new URI("https://example.com:8443/health")
                .parseServerAuthority();
        System.out.println("server host: " + strict.getHost());

        // 5. Phân biệt ba nhóm lỗi.
        try {
            relative.toURL();
        } catch (IllegalArgumentException e) {
            System.out.println("relative URI: rejected");
        }

        try {
            new URI("https://example.com/a b");
        } catch (URISyntaxException e) {
            System.out.println("raw space: rejected");
        }

        try {
            URI.create("urn:example:widget").toURL();
        } catch (MalformedURLException e) {
            System.out.println("unsupported scheme: rejected");
        }
    }
}
```

Biên dịch/chạy (ví dụ này không truy cập mạng):

```bash
javac --release 17 UriToUrlDemo.java
java UriToUrlDemo
```

Kết quả trên JDK chuẩn (không có handler do ứng dụng cài thêm cho scheme `urn`):

```text
parsed: https://example.com/a%20b?q=java%20networking
host: example.com
raw query: q=java%20networking
decoded query: q=java networking
composed: https://example.com:443/learn/java%20basics?lang=vi%20VN
resolved: https://example.com/docs/guide/intro.html
server host: example.com
relative URI: rejected
raw space: rejected
unsupported scheme: rejected
```

Các điểm đáng nhớ:

1. `new URI("https://example.com/a%20b?...")` phân tích chuỗi URI hoàn chỉnh. `%20` vốn là escape hợp lệ nên vẫn được giữ dưới dạng raw.
2. `getRawQuery()` giữ `%20`; `getQuery()` trả nội dung đã giải mã. Nếu cần gửi lại nguyên trạng, đừng dùng giá trị đã giải mã rồi nối chuỗi thủ công.
3. Constructor nhiều thành phần `new URI(scheme, userInfo, host, port, path, query, fragment)` sẽ quote **ký tự không hợp lệ** như dấu cách. Đây là cách ghép an toàn hơn việc tự chèn khoảng trắng trong URL thô.
4. `resolve` chọn đường dẫn căn cứ vào URL gốc. Dấu `/` cuối `https://example.com/docs/` làm rõ đây là thư mục gốc để ghép `guide/intro.html`.
5. `parseServerAuthority()` xác nhận authority có thể phân tích thành host/port/userInfo theo ngữ pháp server; nó **không xác nhận máy chủ có thật**, không kiểm chứng quyền truy cập và không thay thế chính sách an ninh.
6. `toURL()` yêu cầu URI tuyệt đối. Một URI tuyệt đối như `urn:...` vẫn có thể thất bại vì không có protocol handler tương ứng.

## 4. Chuyển constructor URL cũ sang URI theo từng tình huống

Dưới đây là các **mảnh mã để đối chiếu khi migrate** (không phải một lớp Java độc lập). Với ví dụ có `new URI(...)`, phương thức bao ngoài cần xử lý `URISyntaxException`; các phép chuyển `toURL()` cần xử lý `MalformedURLException`.

| API cũ | Ý định ban đầu | Cách thay thế được khuyến nghị |
| --- | --- | --- |
| `new URL(String spec)` | Phân tích URL hoàn chỉnh từ chuỗi | `new URI(spec).toURL()` hoặc `URI.create(spec).toURL()` khi chuỗi được tin là hợp lệ |
| `new URL(String protocol, String host, String file)` | Ghép protocol + host + path/file | Tạo `new URI(scheme, null, host, -1, path, query, fragment)` rồi `toURL()` |
| `new URL(String protocol, String host, int port, String file)` | Ghép host và port | `new URI(scheme, null, host, port, path, query, fragment).toURL()` |
| `new URL(URL context, String spec)` | Resolve URL tương đối | `baseUri.resolve(relativeUri).toURL()` |
| Các constructor có tham số `URLStreamHandler` | Chỉ định handler theo giao thức | Java 20+: `URL.of(uri, handler)`; nếu cần Java 17, xem hướng tương thích riêng bên dưới |

### 4.1. URL hoàn chỉnh

**Trước (legacy; từ Java 20 có cảnh báo):**

```java
URL endpoint = new URL("https://example.com/search?q=java%20uri");
```

**Sau (Java 17+):**

```java
URI endpointUri =
        new URI("https://example.com/search?q=java%20uri");
URL endpoint = endpointUri.toURL();
```

Khi đầu vào do người dùng cung cấp, `new URI(rawInput)` giúp ứng dụng xử lý **`URISyntaxException` tường minh**. `URI.create(rawInput)` là cách ngắn cho hằng số hoặc đầu vào đã được xác thực: nếu cú pháp sai, nó ném `IllegalArgumentException` (bọc nguyên nhân `URISyntaxException`).

### 4.2. Các thành phần scheme/host/port/path/query

**Trước:**

```java
URL endpoint = new URL(
        "https", "example.com", 8443, "/api/items?name=java%20net");
```

**Sau (Java 17+):**

```java
URI endpointUri = new URI(
        "https",          // scheme
        null,             // userInfo
        "example.com",    // host
        8443,             // port
        "/api/items",     // path
        "name=java net",  // query (thành phần chưa mã hóa)
        null              // fragment
);
URL endpoint = endpointUri.toURL();
```

**Cẩn thận với mã hóa hai lần:** constructor theo thành phần mong đợi ký tự *chưa escape*; truyền chuỗi `"name=java%20net"` vào tham số `query` dạng thành phần có thể làm `%` bị quote thành `%25`, tạo `java%2520net`. Ngược lại, khi dùng `new URI(fullString)`, chuỗi đầy đủ phải có escape hợp lệ sẵn. Hãy lựa chọn **một** phương pháp encode nhất quán.

Không được suy diễn constructor URI sẽ tự encode mọi ký tự đặc biệt trong **giá trị tham số query**: dấu `&` và `=` là ký tự có ý nghĩa phân tách trong query và có thể được giữ nguyên. Nếu đầu vào là một giá trị bất kỳ có dấu `&`, `+` hoặc `=`, hãy dùng encoder phù hợp cho phần giá trị theo định dạng query mong muốn, tránh tự ghép gây thay đổi semantics. `URLEncoder`/`URLDecoder` phục vụ *form encoding* (`application/x-www-form-urlencoded`), không phải bộ encode/decode toàn bộ URI tổng quát.

### 4.3. URL tương đối dựa trên một URL gốc

**Trước:**

```java
URL baseUrl = new URL("https://example.com/docs/");
URL chapter = new URL(baseUrl, "chapter-2.html");
```

**Sau (Java 17+):**

```java
URI baseUri = URI.create("https://example.com/docs/");
URI chapterUri = baseUri.resolve("chapter-2.html");
URL chapter = chapterUri.toURL();
```

Khi `baseUri` là `https://example.com/docs/index.html`, `resolve("chapter-2.html")` cũng tạo `https://example.com/docs/chapter-2.html`, vì nó thay thế segment cuối của đường dẫn file. Nhưng với base `https://example.com/docs` **không có dấu slash cuối**, `docs` được xem như segment file và kết quả trở thành `https://example.com/chapter-2.html`. Đó là hành vi URI resolution, không phải lỗi `toURL()`.

### 4.4. URL liên quan đến tệp trên máy

**Tránh** tạo `file:` URL bằng cách nối chuỗi đường dẫn hệ điều hành, vì Windows dùng dấu `\` và tên tệp có thể chứa khoảng trắng/ký tự Unicode.

```java
import java.nio.file.Path;
import java.net.URL;

// Bên trong một phương thức xử lý MalformedURLException:
Path report = Path.of("reports", "bao cao.txt").toAbsolutePath();
URL fileUrl = report.toUri().toURL();
```

`Path.toUri()` tạo URI tệp đúng cho môi trường đang chạy; `toURL()` chỉ chuyển representation, **không bảo đảm tệp tồn tại**. Từ Java 20, hướng này cũng tránh constructor `URL` bị deprecated.

## 5. Điểm khác biệt giữa các ngoại lệ

| Tình huống | API | Ngoại lệ chính | Giải pháp |
| --- | --- | --- | --- |
| Chuỗi URI sai cú pháp, chẳng hạn dấu cách thô | `new URI(raw)` | `URISyntaxException` (checked) | Kiểm tra nguồn đầu vào/escape đúng |
| Chuỗi URI sai cú pháp nhưng dùng factory tiện lợi | `URI.create(raw)` | `IllegalArgumentException` (unchecked) | Chỉ dùng với hằng số hoặc input đã được kiểm tra |
| URI tương đối như `"guide.html"` | `relative.toURL()` | `IllegalArgumentException` | `base.resolve(relative).toURL()` |
| URI tuyệt đối có scheme không có URL handler | `uri.toURL()` | `MalformedURLException` (checked) | Chỉ chuyển các giao thức được hỗ trợ/thực sự cần |
| URL legacy được tạo với cấu trúc khó hiểu | `new URL(...)` | Có thể `MalformedURLException`, nhưng kiểm tra tùy handler | Parse bằng `URI`, kiểm tra authority/scheme rồi convert |
| Chuyển URL cũ về URI | `url.toURI()` | `URISyntaxException` (checked) | Xử lý URL không chuẩn tạo từ API cũ |

**Không gộp hai nhóm lỗi:** `URI.toURL()` có thể ném cả `IllegalArgumentException` (URI không tuyệt đối) lẫn `MalformedURLException` (scheme không được hỗ trợ/handler từ chối). Việc chỉ `catch (MalformedURLException)` **không** bắt được URI tương đối.

Một `URL` tạo thành công không chứng minh endpoint có thể truy cập: DNS, TLS, HTTP status và I/O là những bước thực tế sau đó.

## 6. Java 20+: API `URL.of(URI, URLStreamHandler)`

Java 20 giới thiệu factory sau:

```java
public static URL of(URI uri, URLStreamHandler handler)
        throws MalformedURLException
```

- Với `handler == null`, Java dùng handler mặc định của scheme (nếu có); ví dụ này tương tự `uri.toURL()`.
- Với `handler` tùy chỉnh, ứng dụng có thể gắn custom protocol handler theo quy định của nền tảng. Handler không hợp lệ hoặc không được phép có thể gây lỗi; việc tạo handler tùy chỉnh là chủ đề nâng cao và không cần thiết cho HTTP/HTTPS thông thường.
- **Chỉ biên dịch trên Java 20+**. Trong thư viện cần tương thích Java 17, cứ dùng `URI.toURL()` đối với giao thức chuẩn.

**`UrlFactoryDemo.java`** (riêng cho Java 20+):

```java
import java.net.URI;
import java.net.URL;

public final class UrlFactoryDemo {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://example.com/v1");
        URL url = URL.of(uri, null);
        System.out.println("factory: " + url);
    }
}
```

```bash
javac --release 20 UrlFactoryDemo.java
java UrlFactoryDemo
```

```text
factory: https://example.com/v1
```

Đừng nhầm `URL.of(uri, handler)` với `URI.of(...)`: **Java 17 không có phương thức `URL.of(...)`**, trong khi `URI.create(...)`/`new URI(...)` là lựa chọn phổ biến xuyên các phiên bản.

## 7. Nên giữ URI cho đến khi thực sự phải có URL

### 7.1. HTTP client hiện đại nhận URI trực tiếp

Trong Java 11+ (bao gồm Java 17+), API `java.net.http.HttpRequest` cho phép cấu hình URI trực tiếp:

```java
import java.net.URI;
import java.net.http.HttpRequest;

// Mảnh mã cấu hình request; chưa gửi HTTP.
URI endpoint = URI.create("https://example.com/api/items");
HttpRequest request = HttpRequest.newBuilder(endpoint).GET().build();
```

Không cần tạo `URL` trung gian. Gọi `HttpClient.send(...)` hoặc `sendAsync(...)` mới kích hoạt thao tác HTTP; API và chính sách kết nối thuộc lớp HTTP client.

### 7.2. URI phù hợp cho so sánh, lưu bản đồ hoặc chuẩn hóa đường dẫn

`URI.equals`/`hashCode` so sánh dựa trên nội dung URI theo quy tắc của lớp `URI`, không tra DNS. Trong khi đó, `URL.equals`/`hashCode` có thể phụ thuộc vào địa chỉ IP của host, gây lookup và vấn đề hiệu năng/độ ổn định. Vì vậy:

- Giữ `URI` cho định danh/cấu hình/khóa trong collection.
- Dùng `uri.normalize()` để xử lý phân đoạn `.`/`..` nếu đó là semantics bạn cần; đừng mặc định rằng normalize giải quyết mọi vấn đề canonicalization hay bảo mật.
- Chuyển sang `URL` khi một thư viện cũ yêu cầu tham số `URL` hoặc cần API `URLConnection`.

Đặc biệt, `URI.toString()`, `URI.toASCIIString()`, `getRawPath()` và `getPath()` **không hoàn toàn tương đương**: `getPath` trả dạng đã giải mã, `getRawPath` giữ dấu `%` đã escape, còn `toASCIIString` có thể escape ký tự ngoài ASCII. Tránh giải mã rồi encode lại một cách không kiểm soát.

## 8. Kiểm tra đầu vào trước khi dùng URL từ bên ngoài

`new URI(raw)` kiểm tra cú pháp URI tổng quát; `parseServerAuthority()` làm rõ việc phân tích hostname/port. Đối với ứng dụng chỉ cho phép HTTP/HTTPS, còn cần chính sách riêng về scheme, hostname, userInfo và port.

Ví dụ **mảnh mã trong class** (Java 17+, phương thức khai báo ngoại lệ checked):

```java
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;

static URL requireHttpUrl(String raw)
        throws URISyntaxException, MalformedURLException {
    URI uri = new URI(raw).parseServerAuthority();
    String scheme = uri.getScheme();

    if (scheme == null
            || !(scheme.equalsIgnoreCase("http")
                 || scheme.equalsIgnoreCase("https"))
            || uri.isOpaque()
            || uri.getHost() == null
            || uri.getUserInfo() != null
            || (uri.getPort() != -1
                && (uri.getPort() < 1 || uri.getPort() > 65535))) {
        throw new IllegalArgumentException("Invalid HTTP(S) endpoint");
    }
    return uri.toURL();
}
```

Đây **chỉ là bộ lọc cú pháp và chính sách tối thiểu**, không phải giải pháp phòng chống SSRF đầy đủ. Với URL không đáng tin, còn cần kiểm soát DNS và IP đích thực, redirect, proxy, giới hạn mạng, timeout, TLS và các trường hợp thay đổi kết quả DNS giữa bước kiểm tra và kết nối.

**Một số lỗi phổ biến khi migrate:**

1. Chỉ thay `new URL(raw)` bằng `URI.create(raw).toURL()` mà không xem lại luồng xử lý ngoại lệ: malformed URI có thể chuyển từ `MalformedURLException` sang `IllegalArgumentException`.
2. Gọi `toURL()` trên URI tương đối, hoặc cho rằng **cứ có scheme là URL dùng được**.
3. Ghép chuỗi thủ công chứa khoảng trắng, dấu `#`, `?`, `&` hoặc mã hóa percent đã có, dẫn đến sai đường dẫn/query.
4. Dùng `new URL(base, child)` ở JDK 20+ dù chỉ cần `URI.resolve(child)`.
5. Suy luận API bị đánh dấu `@Deprecated` là đã biến mất khỏi runtime, hoặc dùng `URL.of` trong project còn đặt `--release 17`.
6. Cho rằng `URL` là lựa chọn bắt buộc cho HTTP client mới hoặc dùng `URL.equals` làm phép so sánh rẻ và thuần túy.

## 9. Bài tập và checklist ứng dụng

1. Với `https://example.com/docs/` và `quick-start.html`, tạo `URL` của trang con mà **không dùng constructor `URL`**.
2. Giải thích vì sao `URI.create("/docs/quick-start.html").toURL()` ném `IllegalArgumentException` dù URI này đúng cú pháp.
3. Giải thích khác nhau giữa `new URI("https://example.com/a b")` và `new URI("https", null, "example.com", -1, "/a b", null, null)`.
4. Dự án Java 17 cần build chạy được ngay; có nên thay `new URL(...)` thành `URL.of(uri, null)` không?
5. Dịch vụ HTTP hiện đại dùng `HttpRequest.newBuilder(URI)` có cần chuyển `URI` thành `URL` trước hay không?

**Đáp án gợi ý:** (1) `URI.create("https://example.com/docs/").resolve("quick-start.html").toURL()`; (2) đây là URI **tương đối**, không có scheme; (3) constructor một chuỗi sẽ từ chối dấu cách thô, constructor theo thành phần sẽ quote dấu cách thành `%20`; (4) không, `URL.of` chỉ có từ Java 20, dùng `uri.toURL()`; (5) không cần, vì `HttpRequest` đã nhận `URI`.

**Ghi nhớ khi chuyển đổi:** tạo và xử lý URI có cấu trúc trước, resolve phần tương đối, xác thực ràng buộc ứng dụng, rồi gọi `toURL()` tại nơi cần tích hợp API cũ. Với Java 17 và Java 20+, lộ trình `URI → URL` này giúp code có cùng ý tưởng và hạn chế phát sinh constructor deprecated.

## 10. Tài liệu chính thức

- [Java SE 17: `java.net.URI`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html) — constructor, `URI.create`, `parseServerAuthority`, `resolve`, `toURL`.
- [Java SE 17: `java.net.URL`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html) — URL legacy trước thay đổi deprecation.
- [Java SE 20: `java.net.URL`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/net/URL.html) — `@Deprecated(since="20")`, `URL.of(URI, URLStreamHandler)` và hướng dẫn migrate.
- [JDK 20 Release Notes](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html) — xác nhận việc deprecate URL constructors.
- [Java SE 17: `java.net.http.HttpRequest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html) — xây dựng HTTP request từ URI.
