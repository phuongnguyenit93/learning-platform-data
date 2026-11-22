# So sánh URI, URL và nguy cơ phân giải tên ngoài ý muốn khi so sánh URL trong Java

Một chương trình Java có thể chỉ muốn kiểm tra hai địa chỉ có giống nhau hay không, nhưng lời gọi `URL.equals()`, `URL.hashCode()` hoặc `URL.sameFile()` **có thể kích hoạt phân giải tên máy**. Điều này đặc biệt bất ngờ khi một `URL` được dùng làm khóa của `HashMap`, phần tử `HashSet` hay trong logic loại bỏ địa chỉ trùng. Kết quả có thể phụ thuộc vào DNS và mất thời gian chờ mạng ngay cả khi chương trình không gọi `openConnection()` hay `openStream()`.

Bài học tập trung vào sự khác biệt giữa **so sánh theo cú pháp của `java.net.URI`** và **so sánh theo ngữ nghĩa `java.net.URL`**, nguyên nhân việc so sánh URL có tác dụng phụ, cùng cách chọn phép so sánh đúng mà không vô tình truy vấn tên miền.

## 1. URI và URL trong Java biểu diễn điều gì?

**URI (Uniform Resource Identifier)** là chuỗi định danh tài nguyên theo một cú pháp. `java.net.URI` phân tích những thành phần như scheme, authority, host, port, path, query và fragment. Một URI có thể là tuyệt đối (`https://example.com/a`), tương đối (`../a`), phân cấp hoặc opaque (`mailto:team@example.com`). `URI` là immutable; việc phân tích, `equals`, `hashCode`, `compareTo`, `normalize` và `resolve` là các thao tác dựa trên cú pháp, **không truy vấn DNS để so sánh**.

**URL (Uniform Resource Locator)** là loại định danh nêu cách định vị/truy cập tài nguyên. `java.net.URL` đại diện địa chỉ tuyệt đối kết hợp với một `URLStreamHandler` theo giao thức. Nó cung cấp các thao tác như `openConnection()` và `openStream()`. Đặc biệt, quy tắc `equals`/`hashCode` của URL có thể dùng **địa chỉ Internet của host** để xét tương đương, từ đó cần phân giải tên.

| Tiêu chí | `java.net.URI` | `java.net.URL` |
| --- | --- | --- |
| Vai trò chính | Biểu diễn, phân tích và xử lý cú pháp định danh | Địa chỉ tài nguyên có handler giao thức và API kết nối |
| Tuyệt đối / tương đối | Hỗ trợ cả hai | Đối tượng URL hoàn chỉnh cần một giao thức; có thể nhận chuỗi tương đối qua URL có ngữ cảnh |
| `equals()` | So sánh thành phần cú pháp theo quy tắc URI | Có thể xét tương đương host qua IP do DNS phân giải |
| `hashCode()` | Dựa vào các thành phần URI, không phân giải DNS | Có thể chờ phân giải tên máy |
| `compareTo()` | Có, theo thứ tự cú pháp của URI | Không triển khai `Comparable<URL>` |
| `normalize()` / `resolve()` | Chuẩn hóa dot-segments / ghép URI tham chiếu thuần cú pháp | URL có cách xử lý địa chỉ tương đối qua handler; không đồng nhất với API URI |
| Mở kết nối | Không có `openStream()` | Có `openConnection()` / `openStream()` |

Lưu ý: từ “resolve” trong `URI.resolve(...)` có nghĩa **ghép tham chiếu tương đối với URI gốc**, hoàn toàn khác “DNS resolution” (tra IP từ tên máy).

## 2. Cấu trúc nào thực sự được so sánh?

Ví dụ:

~~~text
https://user@example.com:443/docs/guide?lang=vi#intro
└https┘ └─ authority ────────┘└─path─────┘└query┘└fragment┘
scheme     userinfo + host + port
~~~

Các phương thức tương ứng là `getScheme()`, `getRawUserInfo()`, `getHost()`, `getPort()`, `getRawPath()`, `getRawQuery()`, `getRawFragment()`. Bản `getRaw...` giữ nguyên mã hóa phần trăm; bản `get...` tương ứng có thể trả dữ liệu đã giải mã. Ví dụ, `getRawPath()` có thể là `/a%2Fb` trong khi `getPath()` là `/a/b`. Hai biểu diễn không nên tùy tiện đổi chỗ khi lập khóa cache, kiểm tra quyền hoặc xác định đường dẫn.

- **Scheme**: `https`, `http`, `file`, `mailto`. `URI.equals` so sánh scheme không phân biệt hoa/thường.
- **Authority/host**: host của server-based URI được so sánh không phân biệt hoa/thường; userinfo không được phép mặc định bỏ qua.
- **Port**: port không khai báo có giá trị `-1` trong `URI`; `:443` là một giá trị hiện diện, vì vậy hai URI khác nhau dù cùng “effective HTTPS port” về mặt HTTP.
- **Path, query, fragment**: tham gia phép `URI.equals`; path/query/fragment không được tự động sắp lại, bỏ đi hoặc hạ chữ thường.
- **Percent escapes**: hai chữ số hex trong mã hóa `%hh` được so sánh không phân biệt hoa/thường (`%2f` và `%2F` tương đương trong cùng thành phần); **`%2F` và dấu `/` nguyên văn không mặc nhiên tương đương**.

Điều cốt lõi là `URI.equals` kiểm tra quan hệ **cú pháp URI**, không chứng minh hai yêu cầu HTTP sẽ trả cùng nội dung hay cùng máy chủ.

## 3. `URI.equals()` và `URI.hashCode()`: so sánh không có DNS

Với hai URI phân cấp kiểu server-based, Java so sánh scheme và host không phân biệt chữ hoa/thường; với những thành phần khác, nó áp dụng quy tắc bằng nhau của URI, trong đó fragment cũng được xét. `URI.hashCode()` nhất quán với `equals()` và không cần truy vấn tên miền.

| Cặp URI | Kết quả `URI.equals` | Vì sao |
| --- | --- | --- |
| `https://EXAMPLE.com/a` và `https://example.com/a` | `true` | Host không phân biệt hoa/thường |
| `https://example.com/a#one` và `https://example.com/a#two` | `false` | Fragment khác nhau |
| `https://example.com/a` và `https://example.com:443/a` | `false` | Port `-1` khác `443` |
| `https://example.com/x/./y` và `https://example.com/x/y` | `false` trước `normalize()` | Dot-segment vẫn là phần của path |
| `https://example.com/a%2Fb` và `https://example.com/a/b` | `false` | Dấu gạch chéo mã hóa khác dấu phân cách path |

`URI.normalize()` xử lý các đoạn path như `.` hoặc `..`; nó **không** xóa fragment, không tự đổi cổng mặc định, không biến mọi percent-encoding thành ký tự gốc và không bảo đảm chuẩn hóa theo quy tắc riêng của từng HTTP server.

Nếu yêu cầu là **so sánh chính xác từng ký tự của input**, dùng `String.equals` trên chuỗi gốc. Nếu cần **so sánh URI theo cú pháp**, dùng `URI.equals`. Nếu cần **so sánh cùng origin HTTP**, cần chính sách riêng cho scheme/host/effective port; có ví dụ bên dưới. Đừng dùng `URL.equals` để thay thế một trong ba yêu cầu này.

## 4. Vì sao `URL.equals()` có thể truy vấn DNS?

Tài liệu Java SE 17 của `URL.equals(Object)` quy định hai URL bằng nhau khi protocol, host tương đương, port, file và fragment tương ứng bằng nhau. Hai host có thể được xem là tương đương nếu tên máy phân giải về cùng địa chỉ IP; khi không thể phân giải, việc so tên máy không phân biệt hoa/thường được sử dụng. Tài liệu ghi rõ so host cần name resolution nên thao tác có thể **blocking**.

Luồng khái niệm đối với URL sử dụng handler HTTP(S) mặc định:

~~~text
url1.equals(url2)
       |
       v
URLStreamHandler so protocol / host / port / file / fragment
       |
       v
Host comparison có thể cần địa chỉ IP
       |
       +-- host đã có kết quả cache phù hợp --> dùng kết quả đã có
       |
       +-- cần lookup --> resolver (hosts file / JVM / OS / DNS ...)
                                 |
                                 v
                     tiếp tục tính kết quả equals
~~~

**Không phải mọi `equals` đều gửi một DNS packet**: có nhánh so sánh kết thúc sớm, cache, IP literal, dữ liệu từ hosts file hoặc handler giao thức tùy biến. Nhưng mã nguồn gọi `URL.equals` **không được xem là thuần thao tác chuỗi**, vì API cho phép yêu cầu phân giải mạng.

Hệ quả quan trọng:

1. Hai tên khác nhau như `a.example` và `b.example` có thể được xem là host tương đương nếu cùng phân giải tới một IP và các thành phần URL khác phù hợp. Điều đó **không chứng minh hai HTTP virtual hosts là cùng website, cùng quyền truy cập hay cùng chứng thư TLS**.
2. DNS, hosts file, địa chỉ trả về, cache và trạng thái mạng có thể thay đổi. Cách so sánh phụ thuộc môi trường, khó dự đoán độ trễ hoặc giá trị khi chạy tại máy khác/thời điểm khác.
3. Lookup có thể chờ resolver khi mạng trục trặc; việc “chỉ kiểm tra bằng nhau” có thể khiến luồng request, xử lý collection hoặc mã điều phối chậm bất thường.
4. Nếu URL bắt nguồn từ dữ liệu bên ngoài, việc so sánh/hashing có thể tạo **tra cứu DNS ngoài ý muốn** tới tên máy do bên ngoài chỉ định. Đây là một dạng tác dụng phụ mạng; **không có nghĩa `equals` tự gửi HTTP request**.

Các chi tiết hành vi có thể được handler giao thức tùy biến điều chỉnh; các nhận định trên là cảnh báo đặc biệt quan trọng với URL HTTP(S) thông dụng.

## 5. Ngay cả `hashCode()`, `sameFile()` và collection cũng cần chú ý

`URL.hashCode()` dựa trên các thành phần liên quan đến `URL.equals`; Javadoc cũng xác nhận thao tác này có thể blocking. Đây là bẫy rất thường gặp:

~~~java
// ĐOẠN MINH HỌA RỦI RO, không chạy khi chưa có môi trường DNS kiểm soát.
// Các dòng này là fragment dùng bên trong phương thức có "throws Exception".
URL first = URI.create("https://a.example/report").toURL();
URL second = URI.create("https://b.example/report").toURL();

boolean equal = first.equals(second);  // Có thể phân giải tên máy.
boolean same = first.sameFile(second); // Bỏ fragment, nhưng vẫn có thể phân giải host.

Set<URL> set = new HashSet<>();
set.add(first);                         // HashSet gọi URL.hashCode().
Map<URL, String> map = new HashMap<>();
map.put(second, "report");              // HashMap cũng gọi URL.hashCode().
~~~

Đoạn trên cần `import java.net.URI;`, `import java.net.URL;`, `import java.util.*;`; nó minh họa **anti-pattern**, không phải phần cần chạy để hoàn thành bài. `URL.sameFile` bỏ qua fragment, nhưng kiểm tra cùng file của URL vẫn liên quan protocol/host/port/file qua handler. Đừng cho rằng bỏ fragment cũng bỏ nguy cơ DNS.

Ngay cả khi không có va chạm hash, `HashSet.add` hay `HashMap.put` đã cần tính hash của khóa. Các thao tác `contains`, `get`, `remove` hoặc khởi tạo collection cũng có thể gọi `hashCode`/`equals`. Nếu mục đích là đánh chỉ mục hoặc loại trùng địa chỉ theo cú pháp, thay `URL` bằng `URI` làm khóa, sau khi xác định rõ chính sách chuẩn hóa cần thiết.

**Cảnh báo tính đúng đắn:** hash/equality URL bị ảnh hưởng bởi việc phân giải host; không nên thiết kế khóa lâu dài dựa trên dữ liệu DNS vốn có thể đổi theo thời gian. Một địa chỉ host trỏ cùng IP hôm nay không đồng nghĩa danh tính tài nguyên bất biến. URL cũng không triển khai `Comparable<URL>` để cung cấp một thứ tự so sánh tương đương như URI.

## 6. Ví dụ Java 17+: so sánh an toàn, kết quả xác định

Chương trình sau **không gọi `URL.equals()` hoặc `URL.hashCode()`**. Mọi phép so sánh và dùng khóa map đều dựa trên `URI`; `URL` chỉ xuất hiện ở bước chuyển đổi cuối. Tạo đúng tệp `UriComparisonDemo.java`:

~~~java
import java.net.URI;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;

public class UriComparisonDemo {
    public static void main(String[] args) throws Exception {
        URI first = URI.create("https://EXAMPLE.com/manual/guide#top");
        URI same = URI.create("https://example.com/manual/guide#top");
        URI otherFragment = URI.create(
                "https://example.com/manual/guide#bottom");
        URI withDot = URI.create(
                "https://example.com/manual/./guide#top");
        URI explicitPort = URI.create(
                "https://example.com:443/manual/guide#top");

        System.out.println("scheme-host-case: " + first.equals(same));
        System.out.println("fragment-matters: "
                + first.equals(otherFragment));
        System.out.println("dot-before-normalize: "
                + withDot.equals(same));
        System.out.println("dot-after-normalize: "
                + withDot.normalize().equals(same));
        System.out.println("implicit-vs-explicit-port: "
                + same.equals(explicitPort));

        Map<URI, String> index = new HashMap<>();
        index.put(first, "manual");
        System.out.println("map-value: " + index.get(same));

        URL target = same.toURL();
        System.out.println("host: " + target.getHost());
        System.out.println("round-trip: "
                + target.toURI().equals(same));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac UriComparisonDemo.java
java UriComparisonDemo
~~~

Kết quả xác định của ví dụ:

~~~text
scheme-host-case: true
fragment-matters: false
dot-before-normalize: false
dot-after-normalize: true
implicit-vs-explicit-port: false
map-value: manual
host: example.com
round-trip: true
~~~

**Giải thích:** `first` và `same` chỉ khác chữ hoa trong host nên URI bằng nhau; khác fragment hoặc khác cách khai báo port làm URI khác nhau. `normalize()` bỏ đoạn `.` trên đường dẫn. `Map<URI, String>` dùng hash thuần cú pháp nên không cần giải quyết tên máy. `same.toURL()` chuyển URI HTTP(S) hợp lệ thành URL, còn `getHost()` chỉ đọc host đã phân tích; các dòng này không yêu cầu phát sinh truy vấn DNS để so sánh. Với handler tùy biến, cần đánh giá thêm hành vi riêng của handler.

**Không được nhầm:** việc in được `host: example.com` không chứng minh máy đó đang tồn tại hoặc truy cập được; chương trình này cố ý không kiểm tra kết nối mạng.

## 7. So sánh “cùng origin HTTP” là một bài toán khác `URI.equals`

Trong HTTP, **origin** xét tổ hợp **scheme + hostname + cổng hiệu lực**. Ví dụ `https://example.com/docs` và `https://example.com:443/other` có cùng origin thông dụng, nhưng `URI.equals` trả `false` vì port và path khác nhau. Ngược lại, hai host khác tên cùng trỏ về một IP **không tự động là cùng origin**.

Một cách xác định origin bằng cú pháp, không gọi DNS (ví dụ độc lập Java 17+):

Tệp `HttpOriginDemo.java`:

~~~java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

public class HttpOriginDemo {
    record Origin(String scheme, String host, int port) {}

    static Origin from(URI input) throws URISyntaxException {
        URI uri = input.parseServerAuthority();
        String scheme = uri.getScheme();
        String host = uri.getHost();

        if (scheme == null || host == null ||
                uri.isOpaque() || uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Expected absolute HTTP(S) URI with a host");
        }

        scheme = scheme.toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Not HTTP(S)");
        }

        int port = uri.getPort();
        if (port == -1) {
            port = scheme.equals("https") ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid HTTP port");
        }

        return new Origin(
                scheme, host.toLowerCase(Locale.ROOT), port);
    }

    public static void main(String[] args) throws Exception {
        URI left = URI.create("HTTPS://Example.COM/docs");
        URI right = URI.create("https://example.com:443/docs");

        System.out.println("uri-equals: " + left.equals(right));
        System.out.println("same-origin: "
                + from(left).equals(from(right)));
    }
}
~~~

~~~bash
javac HttpOriginDemo.java
java HttpOriginDemo
~~~

~~~text
uri-equals: false
same-origin: true
~~~

Phương thức `from` gọi `parseServerAuthority()` để kiểm tra authority kiểu server, từ chối URI không phải HTTP(S), host thiếu, userinfo và port sai. Sau đó nó quy đổi cổng mặc định rồi so sánh record theo giá trị. **Đây là phép so sánh origin cú pháp dành cho các host ASCII thông thường**, không phải bộ chuẩn hóa URL hoàn chỉnh cho mọi chuẩn IDN/Unicode/IPv6 và càng không phải cơ chế phê duyệt kết nối mạng. Các ứng dụng thực tế phải xác định chính sách đối với IDN, trailing dot, IPv6, port, userinfo và proxy khi cần.

## 8. Chọn cách so sánh theo yêu cầu thực tế

| Nhu cầu | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Hai chuỗi đầu vào có giống nguyên văn? | `rawA.equals(rawB)` | Phân biệt chữ hoa và khác biệt mã hóa |
| Hai URI có bằng nhau theo quy tắc Java? | `uriA.equals(uriB)` | Thuần cú pháp; fragment được xét |
| Dùng URI làm khóa map/set? | `Map<URI, ...>` / `Set<URI>` | Định nghĩa chính sách `normalize()` trước khi lưu nếu cần |
| So sánh cùng origin HTTP? | Tạo khóa scheme + host + effective port theo chính sách | Không được đồng nhất host khác tên chỉ vì DNS trả cùng IP |
| Coi hai URL khác fragment là “cùng request target”? | Thiết kế phép so sánh bỏ fragment trên URI | Không gọi `URL.sameFile` chỉ để loại fragment |
| Xác minh máy thực sự có IP hoặc kết nối được? | Phân giải/kết nối **tường minh**, có timeout và xử lý lỗi | Đây là hoạt động I/O có chủ đích, khác với so sánh cú pháp |
| Muốn HTTP GET/POST? | Kiểm tra URI, sau đó dùng HTTP client hay URL ở tầng I/O | So sánh URI không thay thế kiểm tra bảo mật đầu ra |

Đặc biệt, fragment (`#...`) thông thường không được gửi như một phần request target HTTP, nhưng vẫn là thành phần của `URI.equals`. Nếu định nghĩa “cùng tài nguyên tải về” bỏ fragment, hãy quyết định rõ điều đó và xây khóa mới theo quy tắc thống nhất; đừng mặc định mọi thành phần khác có thể loại hoặc sắp xếp.

## 9. Parse, chuẩn hóa và chuyển đổi URI ↔ URL đúng chỗ

**Parse input từ bên ngoài:**

~~~java
// Fragment minh họa bên trong method; URI.create ném IllegalArgumentException
// nếu chuỗi không tuân theo cú pháp URI.
URI uri = URI.create("https://example.com/docs");
URI normalized = uri.normalize(); // Chỉ xử lý dot-segments của path
~~~

Nếu muốn lỗi parse có kiểu checked, dùng `new URI(text)` và bắt `URISyntaxException`. `URI.create(text)` thích hợp với hằng số/config đã kiểm soát, vì lỗi cú pháp được báo bằng `IllegalArgumentException`.

**Tạo URL khi thật sự cần API truy cập mạng:**

~~~java
// Fragment minh họa bên trong method có "throws Exception".
URI uri = URI.create("https://example.com/docs");
URL url = uri.toURL();         // Chuyển đối tượng, không gọi GET.
URI back = url.toURI();       // Có thể báo URISyntaxException nếu URL
                              // chứa cú pháp không hợp lệ đối với URI.
~~~

`URI.toURL()` yêu cầu URI tuyệt đối và cần handler hỗ trợ scheme; không phải mọi URI (ví dụ relative hay một URN tùy ý) đều có thể chuyển thành URL dùng để mở kết nối. Trên **Java 20+**, các constructor truyền thống của `URL` đã bị đánh dấu deprecated; dùng `URI` để parse/validate và `toURL()` để chuyển đổi khi cần. Cách này cũng hoạt động trên Java 17.

**Không “chuẩn hóa” quá mức:** tự lower-case toàn bộ đường dẫn, giải mã `%2F` thành `/`, sắp xếp query parameters, bỏ dấu `/` cuối hay gộp mọi host có cùng IP đều có thể thay đổi ý nghĩa tài nguyên. Với API yêu cầu chữ ký HMAC, đường dẫn và query thậm chí có thể phải được giữ chính xác ở dạng raw. `URI.normalize()` không phải bộ canonicalization an toàn toàn diện.

## 10. Hệ quả hiệu năng, độ ổn định và bảo mật

**Hiệu năng:** Một hàm loại trùng danh sách URL có vẻ chỉ chạy CPU nhưng vẫn có thể đợi DNS. Nếu danh sách được xử lý trong HTTP request handler hoặc event loop, nó làm tăng latency và có thể chặn luồng xử lý. Dùng `Set<URI>` khi mục đích là so trùng cú pháp.

**Tính xác định:** DNS phân phối nhiều địa chỉ, thay đổi IP, bộ nhớ đệm và lỗi resolver làm hành vi dựa trên phân giải khó tái lập. Thay đổi host → IP không đổi cùng lúc với giá trị URI; `URI.equals` vì thế có tính dự đoán tốt hơn cho khóa và dedup cú pháp.

**Bảo mật:** Một URL do người dùng cung cấp có thể chứa tên miền ngoài ý muốn. Nếu ứng dụng chỉ định “không truy cập mạng” nhưng đưa URL vào `HashSet`, `HashMap` hoặc `equals`, nó vẫn có thể kích hoạt truy vấn DNS. Điều này khác với SSRF qua HTTP connection, nhưng vẫn là hoạt động mạng cần được kiểm soát nếu có chính sách chặn lookup.

**Không coi `URI.equals` là giải pháp SSRF:** khi ứng dụng **thực sự** kết nối tới URI do người dùng cung cấp, cần xác thực scheme, authority, userinfo, hostname, port, chuyển hướng, DNS rebinding và các IP đích sau phân giải (bao gồm địa chỉ loopback/private/link-local tùy chính sách). Hai host khác tên dù cùng IP cũng có thể là hai HTTP origins với virtual host/TLS khác nhau. Không dựa vào `URL.equals` để kiểm tra allowlist, phân quyền, same-origin hoặc truy cập tài nguyên.

**Ranh giới mạng:** `URI.equals()` không resolve hostname. Ngược lại, khi gọi `InetAddress.getByName(host)`, `HttpClient.send(...)` hoặc `URL.openStream()`, ứng dụng đã chuyển sang lớp I/O; cần quy định rõ timeout, retry và kiểm soát địa chỉ. `URL.openConnection()` tạo `URLConnection`, còn việc kết nối thực tế có thể bắt đầu tại phương thức truy cập/đọc tùy handler; không dùng nó làm ví dụ “so sánh đơn thuần”.

## 11. Thí nghiệm kiểm chứng tác dụng phụ DNS (trong môi trường kiểm soát)

Nếu muốn quan sát tác dụng phụ của `URL.equals`/`hashCode`, dùng hostname do bạn kiểm soát, DNS resolver hoặc môi trường test có log truy vấn. **Không lấy một kết quả thời gian từ máy công cộng làm bằng chứng phổ quát.**

1. Chọn hai hostname thử nghiệm và ghi cấu hình resolver, phiên bản JDK, cache hiện có. Đảm bảo không có tên/địa chỉ nội bộ nhạy cảm cần giữ kín.
2. Trong JVM mới, tạo các `URI` từ hostname và gọi `equals`, `hashCode`, `compareTo`; ghi nhận đây là thao tác cú pháp. Đọc DNS log để xác nhận môi trường không ghi nhận lookup do những phép so sánh này.
3. Ở một lần chạy riêng, chuyển sang `URL` và gọi `equals`, `hashCode` hoặc thêm làm khóa `HashMap`; theo dõi resolver và độ trễ. Cần lưu ý URL handler, cache JVM/OS, hosts file và DNS server có thể làm số query quan sát được khác nhau.
4. Thử resolver lỗi/chậm hoặc đổi IP chỉ trong môi trường test; so sánh độ trễ và đầu ra. Không dùng việc “lần này URL.equals nhanh” để kết luận API không thực hiện DNS.
5. Thay lại toàn bộ logic index/dedup thành `URI` và kiểm tra hành vi nghiệp vụ. Sau đó chỉ làm phân giải/kết nối ở tầng I/O với kiểm soát rõ ràng.

Thí nghiệm phải tách hai điều: **API có thể gây lookup** (đã được Javadoc xác nhận) và **một lần chạy cụ thể có tạo gói DNS ra mạng hay không** (phụ thuộc cache, resolver, các nhánh so sánh). Không nên khẳng định “mỗi lời gọi equals tạo một DNS packet”.

## 12. Sai lầm phổ biến và câu hỏi tự kiểm tra

**Sai lầm 1 — “`URL.equals` chỉ so hai chuỗi.”** Sai: có thể so host qua địa chỉ IP và chặn chờ name resolution.

**Sai lầm 2 — “Tôi không gọi `URL.equals`, chỉ đưa URL vào `HashMap`.”** `HashMap` vẫn gọi `URL.hashCode`; `URL.hashCode` cũng có thể blocking.

**Sai lầm 3 — “`URL.sameFile` bỏ fragment nên không cần DNS.”** Phép so sánh host của URL vẫn có thể phân giải tên.

**Sai lầm 4 — “Hai hostname phân giải cùng IP thì là cùng HTTP origin.”** Sai: origin dựa trên scheme, hostname và effective port, không phải IP trả từ DNS.

**Sai lầm 5 — “`URI.equals` tự chuẩn hóa mọi cách viết URL tương đương.”** Sai: cổng mặc định, dot-segments, encoded slash, query và fragment có các quy tắc riêng; chỉ chuẩn hóa điều mà nghiệp vụ thực sự cho phép.

**Sai lầm 6 — “So sánh URI bảo đảm không có nguy cơ SSRF về sau.”** Sai: ứng dụng còn phải kiểm soát bước phân giải và kết nối thực tế.

Tự kiểm tra:

- **Câu 1:** Vì sao `HashSet<URL>.add(url)` có thể chờ DNS? **Trả lời:** vì `HashSet` gọi `url.hashCode()`, mà Javadoc `URL` cho phép dùng kết quả phân giải host khi tính hash.
- **Câu 2:** `URI.create("https://a.example/x").equals(URI.create("https://b.example/x"))` có DNS lookup không? **Trả lời:** không; URI so theo cú pháp nên trả `false` dù hai host có thể cùng IP.
- **Câu 3:** `URI.resolve("../x")` có phân giải IP không? **Trả lời:** không; nó ghép và chuẩn hóa path theo ngữ cảnh URI.
- **Câu 4:** So sánh cú pháp có cần bỏ fragment trước khi lưu map không? **Trả lời:** chỉ khi định nghĩa khóa nghiệp vụ cho phép; mặc định `URI.equals` có xét fragment.
- **Câu 5:** Khi nào nên chuyển sang `URL`? **Trả lời:** khi thật sự cần một API làm việc với URL/handler/kết nối; tiếp tục dùng `URI` làm khóa và để kiểm tra cú pháp.

## Tài liệu chính thức

- Java SE 17 — `java.net.URI`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 — `java.net.URL`, đặc biệt `equals()`, `hashCode()` và `sameFile()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 — `java.net.URLStreamHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandler.html
- Java SE 20 — ghi chú về constructor `URL` deprecated và `URI.toURL()`: https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/net/URL.html
- RFC 3986 — cú pháp URI và các cân nhắc khi chuẩn hóa/bảo mật: https://www.rfc-editor.org/rfc/rfc3986
