# URI, địa chỉ mạng và phân giải tên miền

## 1. Ba lớp khái niệm: URI, tên máy và địa chỉ IP

Trong ứng dụng Java 27, một chuỗi như **https://api.example.com:8443/v1/items?q=java** chứa nhiều thông tin khác nhau. Một số mô tả **tài nguyên ứng dụng**, một số mô tả **đích kết nối mạng** và một số cần được chuyển đổi qua hệ thống phân giải tên.

- **URI (Uniform Resource Identifier)** định danh một tài nguyên theo cú pháp có cấu trúc. Java biểu diễn URI bằng **java.net.URI**.
- **Hostname/domain name** là tên như **api.example.com**, không nhất thiết là địa chỉ IP đã được xác định.
- **IP address** là địa chỉ mạng IPv4 hoặc IPv6, biểu diễn trong Java bằng **InetAddress**, **Inet4Address** hoặc **Inet6Address**.
- **Port** là số cổng của dịch vụ giao tiếp, ví dụ 443 cho HTTPS theo quy ước thông dụng.
- **DNS (Domain Name System)** là một nguồn phân giải tên miền thành địa chỉ và cung cấp nhiều loại bản ghi khác. Trong Java, **InetAddress** sử dụng bộ phân giải của runtime/hệ điều hành, không nhất thiết chỉ DNS.

~~~mermaid
flowchart LR
    U["URI: https://api.example.com:443/orders"] --> P["Phân tích: scheme / host / port / path"]
    P --> N["Host: api.example.com"]
    N --> R["Hệ thống phân giải tên"]
    R --> I["Một hoặc nhiều địa chỉ IPv4 / IPv6"]
    I --> S["Kết nối tới IP và port"]
    S --> H["TLS và giao thức HTTP"]
~~~

**Điểm phân biệt quan trọng:** **URI.create(...)** hay **new URI(...)** chỉ xử lý cú pháp, không tự mở socket và không tự gửi DNS query. Việc thực hiện HTTP request bằng **HttpClient** mới đòi hỏi quá trình giao tiếp mạng và phân giải địa chỉ phù hợp.

Bài này thuộc chương **Mạng và HTTP** của module **Java 27 và các kiến thức liên quan**. Chỉ sử dụng những API hiện hành của **java.net**, **java.net.http** và các thành phần Java SE còn được hỗ trợ; không dựa vào cơ chế kết nối cũ đã bị thay thế cho nhu cầu thiết kế mới.

## 2. URI khác URL như thế nào?

URI là khái niệm tổng quát để định danh tài nguyên. **URL (Uniform Resource Locator)** là dạng định danh có thông tin vị trí/cách truy cập tài nguyên, thường gặp dưới dạng HTTP/HTTPS URL.

Trong Java:

| Loại | Lớp / ý nghĩa | Ví dụ |
|---|---|---|
| URI tuyệt đối, phân cấp | Có scheme và các thành phần như authority, path | **https://example.com/docs/** |
| URI tương đối | Không có scheme, cần base khi giải quyết | **../images/logo.svg** |
| URI opaque | Có scheme nhưng không phân tích thành host/path theo cấu trúc phân cấp | **mailto:team@example.com** |
| HTTP/HTTPS URL | Một URI dùng scheme cho tài nguyên web | **https://example.com:443/api** |
| IP literal | Địa chỉ IP viết trực tiếp | **192.0.2.10**, **2001:db8::10** |

Lớp **java.net.URI** là một giá trị immutable để phân tích, xây dựng và biến đổi URI, thích hợp cho **HttpRequest.Builder.uri(URI)**.

Lớp **java.net.URL** cũng tồn tại, nhưng **các constructor của URL đã bị deprecated**; trong code mới, nên tạo **URI** trước và chỉ chuyển sang URL nếu API cụ thể cần nó. Hơn nữa, các thao tác so sánh trên URL có những đặc tính lịch sử không lý tưởng cho so sánh định danh mạng; nên dùng URI để giữ hành vi so sánh cú pháp rõ ràng hơn.

**Không nhầm URI là kết nối đã mở.** Một URI hợp lệ về cú pháp không chứng minh host tồn tại, địa chỉ có thể phân giải, cổng đang mở hoặc tài nguyên HTTP đang trả 200.

## 3. Các thành phần của một URI phân cấp

Xét URI:

~~~text
https://api.example.com:8443/v1/products/coffee?q=java%20http&lang=vi#details
│───│  │─────────────│ │──││─────────────────│ │────────────────────││─────│
scheme       host       port           path               query         fragment
~~~

Có thể có thêm **user-info** trong authority theo cú pháp chung, nhưng **không nên đưa mật khẩu, API key hoặc token vào URI**.

Cấu trúc của URI phân cấp thường có dạng:

~~~text
[scheme:][//authority][path][?query][#fragment]
~~~

**Authority** ở dạng server-based có thể bao gồm **user-info@host:port**. URI cũng cho phép những authority không phân tích thành host/port theo quy tắc server-based; vì thế đôi khi **getAuthority() khác null nhưng getHost() là null**.

~~~java
import java.net.URI;

URI uri = URI.create(
    "https://api.example.com:8443/v1/products?q=java%20http#details"
);

System.out.println(uri.getScheme());    // https
System.out.println(uri.getHost());      // api.example.com
System.out.println(uri.getPort());      // 8443
System.out.println(uri.getPath());      // /v1/products
System.out.println(uri.getQuery());     // q=java http
System.out.println(uri.getFragment());  // details
~~~

**Các thành phần vắng mặt có thể trả null**; **getPort()** trả **-1** khi không có port tường minh. Port -1 **không có nghĩa port âm sẽ được dùng trên mạng**: tầng giao thức (ví dụ HTTPS) mới xác định cổng mặc định phù hợp.

## 4. URI tuyệt đối, tương đối và opaque

Một URI được gọi là **absolute** nếu có scheme. URI phân cấp (*hierarchical*) có thể có path, authority, query; URI **opaque** có scheme-specific part nhưng không phân tích thành những thành phần đó.

~~~java
import java.net.URI;

URI absolute = URI.create("https://example.com/a/b");
URI relative = URI.create("../images/logo.svg");
URI opaque = URI.create("mailto:team@example.com");

System.out.println(absolute.isAbsolute()); // true
System.out.println(relative.isAbsolute()); // false
System.out.println(opaque.isOpaque());     // true
System.out.println(opaque.getHost());      // null
~~~

Một URI **không có host** không nhất thiết sai. **mailto:**, **urn:**, file URI và relative URI có thể không có host vì ngữ nghĩa của chúng khác với HTTP URL.

Tuy nhiên, nếu một hàm đang chuẩn bị gửi **HTTP/HTTPS request**, phải **kiểm tra scheme, dạng URI, host và các điều kiện khác** theo hợp đồng. Không thể nhận mọi URI rồi mặc định rằng **uri.getHost()** luôn có giá trị.

## 5. Tạo URI từ chuỗi: URI.create và new URI

Hai cách tạo thường gặp:

~~~java
import java.net.URI;
import java.net.URISyntaxException;

// Phù hợp với hằng số URI do lập trình viên kiểm soát.
URI known = URI.create("https://example.com/docs");

// Phù hợp để bắt riêng lỗi cú pháp từ nguồn có thể sai.
static URI parseUserUri(String text) throws URISyntaxException {
    return new URI(text);
}
~~~

**URI.create(String)** bọc lỗi cú pháp thành **IllegalArgumentException**, thuận tiện khi đầu vào phải là hằng số hợp lệ trong mã. Constructor **new URI(String)** ném **URISyntaxException**, thường thích hợp khi parse dữ liệu bên ngoài và cần thông báo rõ lỗi cú pháp.

**URI không tự xác thực chính sách ứng dụng.** Ví dụ, có thể parse thành công một URI có scheme **file:** hoặc **mailto:** nhưng API chỉ cho phép **https:**. Phần kiểm tra chính sách phải thực hiện riêng.

Không coi **URI.create** là một hàm “làm sạch URL” hoặc hàm chống SSRF. Nó chỉ phân tích biểu diễn URI theo các quy tắc của lớp URI.

## 6. Tạo URI từ các thành phần để tránh sai dấu phân cách

Ghép URI bằng cộng chuỗi tùy tiện dễ làm sai dấu **/**, **?**, **#** hoặc chèn những ký tự đặc biệt vào thành phần không phù hợp.

Với các thành phần riêng biệt, constructor có đối số giúp quote ký tự không hợp lệ:

~~~java
import java.net.URI;

URI uri = new URI(
    "https",
    null,
    "example.com",
    443,
    "/sản phẩm/áo trắng",
    "lang=vi",
    null
);

System.out.println(uri.getPath());    // /sản phẩm/áo trắng
System.out.println(uri.getRawPath()); // Các ký tự không phải ASCII được % mã hóa
System.out.println(uri.toASCIIString());
~~~

Lưu ý quan trọng:

- Với URI có scheme, path trong constructor phân cấp phải trống hoặc bắt đầu bằng **/**.
- Các đối số thành phần được quote theo quy tắc tương ứng, nhưng **constructor không tự hiểu query thành các cặp tên/giá trị**.
- Nếu một **giá trị query** chứa **&** hoặc **=**, không được chỉ cộng thẳng vào query và mong hệ thống nhận biết đó là dữ liệu thay vì ký tự phân cách.

Vì vậy, với URI có nhiều query parameters, hãy dùng quy tắc mã hóa tham số phù hợp với giao thức hoặc một builder đã được kiểm chứng của thư viện HTTP đang sử dụng.

## 7. Raw component và decoded component

Các ký tự đặc biệt trong URI thường được biểu diễn bằng **percent-encoding**. Ví dụ khoảng trắng trong path có thể thành **%20**.

~~~java
URI uri = URI.create(
    "https://example.com/files/hello%20world.txt?q=caf%C3%A9"
);

System.out.println(uri.getRawPath());
// /files/hello%20world.txt

System.out.println(uri.getPath());
// /files/hello world.txt

System.out.println(uri.getRawQuery());
// q=caf%C3%A9

System.out.println(uri.getQuery());
// q=café
~~~

| API | Trả về |
|---|---|
| **getRawPath()** | Path còn dạng percent-encoded |
| **getPath()** | Path đã giải mã các escape octets |
| **getRawQuery()** | Query còn dạng percent-encoded |
| **getQuery()** | Query đã giải mã các escape octets |
| **getRawFragment()** | Fragment chưa giải mã |
| **getFragment()** | Fragment đã giải mã |
| **toString()** | Biểu diễn URI có thể chứa ký tự Unicode |
| **toASCIIString()** | Biểu diễn ASCII với quoting/encoding khi cần |

**Không được giải mã hai lần** một cách vô ý. Ví dụ một chuỗi chứa **%252F** có thể biến thành **%2F** sau lần đầu, rồi thành dấu **/** nếu một tầng khác giải mã thêm lần nữa. Lỗi canonicalization kiểu này đặc biệt nguy hiểm khi kiểm tra đường dẫn, kiểm tra quyền truy cập hoặc ký request.

Hãy chọn rõ **một dạng dữ liệu (raw hay decoded)** cho mỗi bước xử lý và tránh truyền qua nhiều tầng có quy tắc giải mã không thống nhất.

## 8. Percent-encoding và UTF-8

Khi chuyển ký tự Unicode thành URI ASCII, ký tự được mã hóa thành byte UTF-8 rồi mỗi byte cần thiết được biểu diễn bằng **%HH**.

Ví dụ:

~~~text
café
  ↓ UTF-8: "é" = C3 A9
caf%C3%A9
~~~

**Percent-encoding không phải URL encoding của cả một đối tượng bất kỳ theo một quy tắc duy nhất.** Những ký tự như **/**, **?**, **&**, **=**, **#** có ý nghĩa khác nhau giữa path, query và fragment. Một cách quote hợp lệ cho query value chưa chắc phù hợp khi đưa cùng chuỗi vào path segment.

Java có lớp **URLEncoder**, nhưng nó dành cho **application/x-www-form-urlencoded** thường dùng với dữ liệu form và giá trị query theo quy ước đó. Trong kiểu encoding này, dấu cách thành **+**, khác với cách biểu diễn không gian bằng **%20** trong URI thông thường.

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String value = "cà phê + Java";
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);

URI query = URI.create(
    "https://example.com/search?q=" + encoded
);

System.out.println(encoded);
// c%C3%A0+ph%C3%AA+%2B+Java
~~~

**Không dùng URLEncoder cho toàn bộ URI**. Ví dụ, mã hóa toàn bộ **https://...** sẽ làm hỏng các dấu phân cách cần thiết. Khi server nhận các query theo form encoding, dùng **URLDecoder** cho đúng phạm vi giá trị và đúng charset; không áp dụng nó tùy tiện lên mọi raw path.

## 9. resolve: giải URI tương đối dựa trên base URI

**URI.resolve(...)** có ích khi xử lý liên kết tương đối:

~~~java
import java.net.URI;

URI base = URI.create("https://example.com/docs/");
URI next = base.resolve("intro.html");

System.out.println(next);
// https://example.com/docs/intro.html
~~~

Nếu base có phần cuối không phải dấu **/**, phần cuối thường được coi như thành phần tên tài liệu để thay thế:

~~~java
URI directory = URI.create("https://example.com/docs/");
URI document = URI.create("https://example.com/docs");

System.out.println(directory.resolve("chapter.html"));
// https://example.com/docs/chapter.html

System.out.println(document.resolve("chapter.html"));
// https://example.com/chapter.html
~~~

Điểm này thường gây lỗi khi code tự xây URL đến API endpoint.

Ví dụ path có **..**:

~~~java
URI base = URI.create("https://example.com/a/b/");
URI resolved = base.resolve("../c/page.html");

System.out.println(resolved);
// https://example.com/a/c/page.html
~~~

**resolve không tự bảo đảm kết quả nằm trong một đường dẫn hay một host được phép**. Một relative reference như **//other.example/path** có thể thay authority, và một URI absolute có thể thay cả scheme/host. Nếu nguồn tham chiếu đến từ người dùng, hãy xác thực **URI cuối cùng sau resolve** theo chính sách ứng dụng.

## 10. normalize và relativize không phải bộ lọc bảo mật

**URI.normalize()** xử lý một số thành phần đường dẫn như **.**, **..** và phân đoạn trống theo quy tắc URI phân cấp:

~~~java
URI uri = URI.create(
    "https://example.com/a/./b/../c"
);

System.out.println(uri.normalize());
// https://example.com/a/c
~~~

**URI.relativize** tạo reference tương đối nếu hai URI tương thích và đường dẫn của URI đích nằm trong phần prefix tương ứng:

~~~java
URI base = URI.create("https://example.com/docs/");
URI target = URI.create("https://example.com/docs/api/index.html");

System.out.println(base.relativize(target));
// api/index.html
~~~

Tuy nhiên, **normalize không phải cơ chế chặn path traversal**. Nó không thay thế quy tắc canonicalization của filesystem, reverse proxy hay router; encoded separators, double decoding, Unicode normalization, case sensitivity và symlink là các vấn đề khác nhau.

Khi xây chính sách truy cập file, hãy dùng **Path** và kiểm tra ranh giới filesystem phù hợp, không coi một URI đã normalize là bằng chứng chắc chắn đường dẫn an toàn.

## 11. Fragment không phải một phần địa chỉ yêu cầu HTTP gửi đến server

**Fragment** là phần sau **#**, dùng để định danh vùng hoặc trạng thái ở phía client theo ngữ nghĩa URI. Nó **không được gửi như một phần HTTP request-target** khi trình duyệt hoặc HTTP client truy xuất tài nguyên.

~~~java
URI first = URI.create(
    "https://example.com/guide.html#installation"
);
URI second = URI.create(
    "https://example.com/guide.html#examples"
);

System.out.println(first.getPath().equals(second.getPath())); // true
System.out.println(first.getFragment()); // installation
System.out.println(second.getFragment()); // examples
~~~

Với ứng dụng HTTP, không nên đặt tham số bảo mật, điều khiển server hoặc dấu vết giao dịch bắt buộc chỉ trong fragment rồi kỳ vọng server sẽ nhận. Nếu gửi HTTP request bằng Java HttpClient, request được xử lý theo scheme/authority/path/query, không dùng fragment như một giá trị protocol trao đổi với server.

## 12. Host, port và endpoint kết nối

Một **host** có thể là tên miền hoặc IP literal. Một endpoint TCP thường được xác định bởi **địa chỉ IP và port**, cùng với loại giao thức và môi trường mạng tương ứng.

~~~text
api.example.com:443
└────host────┘ └port┘

[2001:db8::10]:443
└──IPv6 literal──┘ └port┘
~~~

Khi biểu diễn **IPv6 trong authority của URI**, dấu ngoặc vuông **[ ]** phân biệt các dấu **:** của địa chỉ IPv6 với dấu **:** trước port:

~~~java
URI ipv6Uri = URI.create(
    "https://[2001:db8::10]:8443/status"
);

System.out.println(ipv6Uri.getPort()); // 8443
System.out.println(ipv6Uri.getScheme()); // https
~~~

**2001:db8::/32** và **192.0.2.0/24** là các dải địa chỉ dành cho tài liệu/ví dụ, không phải địa chỉ máy chủ production phải kết nối.

Port hợp lệ cho **InetSocketAddress** nằm trong khoảng **0 đến 65535**; port **0** thường được dùng khi bind để hệ điều hành chọn cổng tạm. Trong thiết kế một client đến dịch vụ cụ thể, nên xác định port thực sự từ scheme hoặc cấu hình thay vì coi port 0 là endpoint bên ngoài hợp lệ.

## 13. InetAddress: biểu diễn một địa chỉ IP

**java.net.InetAddress** biểu diễn địa chỉ IP 32 bit (IPv4) hoặc 128 bit (IPv6). **Inet4Address** và **Inet6Address** là hai dạng cụ thể.

~~~java
import java.net.InetAddress;
import java.net.Inet4Address;
import java.net.Inet6Address;

InetAddress ipv4 = InetAddress.ofLiteral("127.0.0.1");
InetAddress ipv6 = InetAddress.ofLiteral("::1");

System.out.println(ipv4 instanceof Inet4Address); // true
System.out.println(ipv6 instanceof Inet6Address); // true

System.out.println(ipv4.isLoopbackAddress()); // true
System.out.println(ipv6.isLoopbackAddress()); // true
~~~

**InetAddress.ofLiteral(String)** là API chính thức từ **Java 22**, hiện dùng được trong Java 27. Nó chỉ phân tích **IP literal**, **không thực hiện DNS lookup** và **không chặn chờ kết quả phân giải ngược**. Đầu vào không phải IP literal hợp lệ khiến phương thức ném **IllegalArgumentException**.

~~~java
try {
    InetAddress.ofLiteral("not-an-ip");
} catch (IllegalArgumentException invalid) {
    System.out.println("Invalid IP literal");
}
~~~

Nếu dữ liệu chỉ được phép là IP literal, **ofLiteral** rõ nghĩa và an toàn về mặt hành vi phân giải hơn **getByName**, vì getByName còn có nhánh phân giải hostname qua hệ thống resolver.

## 14. IPv4 và IPv6: khác nhau ở dạng địa chỉ, không phải ứng dụng tầng trên

**IPv4** có 32 bit, thường viết dạng bốn số thập phân, ví dụ **192.0.2.15**. **IPv6** có 128 bit, thường viết bằng các nhóm hex phân tách bằng dấu hai chấm, ví dụ **2001:db8::15**.

| Nội dung | IPv4 | IPv6 |
|---|---|---|
| Độ dài địa chỉ | 32 bit = 4 byte | 128 bit = 16 byte |
| Ví dụ tài liệu | **192.0.2.15** | **2001:db8::15** |
| Loopback thông dụng | **127.0.0.1** | **::1** |
| Wildcard khi bind | **0.0.0.0** | **::** |
| Trong URI authority có port | **192.0.2.15:8080** | **[2001:db8::15]:8080** |

Có thể đọc các byte địa chỉ:

~~~java
InetAddress address = InetAddress.ofLiteral("192.0.2.15");
byte[] bytes = address.getAddress();

System.out.println(bytes.length); // 4

for (byte value : bytes) {
    System.out.print((value & 0xFF) + " ");
}
// 192 0 2 15
~~~

Byte Java có dấu, nên dùng **value & 0xFF** khi muốn biểu diễn byte địa chỉ theo số nguyên 0–255.

Không tự phân tích IPv6 bằng **split(":")**: biểu diễn rút gọn với **::**, địa chỉ có vùng (*scope*) và những dạng kết hợp phức tạp khiến phép tách chuỗi đơn giản dễ sai. Hãy dùng API chuẩn của Java.

## 15. DNS phân giải tên miền như thế nào?

DNS ánh xạ tên miền sang nhiều loại dữ liệu. Với kết nối IP thông thường, hai loại bản ghi quan trọng:

- **A record**: chứa địa chỉ **IPv4**.
- **AAAA record**: chứa địa chỉ **IPv6**.

Các bản ghi **CNAME**, **MX**, **TXT**, **SRV** có ngữ nghĩa khác; riêng **InetAddress.getAllByName** là API phân giải **địa chỉ IP**, không phải công cụ truy vấn mọi loại DNS record.

Một hostname có thể trả về **nhiều địa chỉ IPv4 và/hoặc IPv6**. Kết quả có thể đổi theo thời điểm, mạng, DNS resolver, chính sách cân bằng tải, vị trí người dùng hoặc cache.

~~~mermaid
flowchart TD
    A["Hostname: api.example.com"] --> B["Hệ thống phân giải tên"]
    B --> C["Nguồn: hosts / DNS / dịch vụ tên khác"]
    C --> D["A: địa chỉ IPv4"]
    C --> E["AAAA: địa chỉ IPv6"]
    D --> F["Client chọn đường kết nối phù hợp"]
    E --> F
~~~

Trong Java, bản thân phương thức **getAllByName** không cam kết rằng nguồn dữ liệu chỉ đến từ DNS. Bộ phân giải tích hợp có thể tham khảo thông tin máy cục bộ và dịch vụ đặt tên theo cấu hình hệ điều hành; Java còn có cơ chế provider cho resolver. Vì vậy, kết quả tên → IP có thể phụ thuộc môi trường.

## 16. Phân giải tên bằng InetAddress.getAllByName

Ví dụ mạng trực tiếp:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

static void printResolvedAddresses(String hostname)
        throws UnknownHostException {

    for (InetAddress address : InetAddress.getAllByName(hostname)) {
        System.out.println(address.getHostAddress());
    }
}
~~~

Gọi với hostname hợp lệ:

~~~java
printResolvedAddresses("example.com");
~~~

**Đây là ví dụ phụ thuộc kết nối mạng và cấu hình resolver.** Số địa chỉ, thứ tự, phiên bản IP và giá trị cụ thể có thể thay đổi. Không viết bài kiểm thử với kỳ vọng hostname luôn trả một IP cố định, hoặc luôn có A và AAAA trong cùng môi trường.

**getByName(host)** trả một địa chỉ phù hợp; **getAllByName(host)** trả danh sách các ứng viên theo resolver. Không được hiểu rằng địa chỉ đầu tiên là địa chỉ duy nhất, hoặc nó sẽ luôn được chọn khi HTTP client thực hiện kết nối.

Khi hostname không phân giải được, phương thức có thể ném **UnknownHostException**. Lỗi này không luôn chứng minh tên miền vĩnh viễn không tồn tại: DNS timeout, mạng bị giới hạn, cấu hình resolver sai hoặc cache kết quả âm đều có thể là nguyên nhân.

**Không truyền null hoặc chuỗi rỗng để kiểm tra lỗi hostname.** Với **InetAddress.getByName/getAllByName**, giá trị null/rỗng có hành vi đặc biệt liên quan đến loopback; code nhận hostname của người dùng nên tự từ chối chuỗi rỗng trước khi gọi API.

## 17. Phân giải tên và phép tra cứu ngược không giống nhau

Hai chiều:

- **Forward lookup:** hostname → một hoặc nhiều IP.
- **Reverse lookup:** IP → hostname được hệ thống phân giải trả về, nếu có.

~~~java
InetAddress address = InetAddress.ofLiteral("127.0.0.1");

System.out.println(address.getHostAddress());
// 127.0.0.1

System.out.println(address.getCanonicalHostName());
// Có thể trả hostname theo resolver hoặc chính địa chỉ IP
~~~

Một **InetAddress** tạo từ IP literal không mặc nhiên có hostname đã được xác thực. **getCanonicalHostName()** có thể thực hiện reverse lookup qua resolver, có thể chặn trong lúc chờ, và có thể trả về chuỗi IP nếu không có tên được xác định.

**Không dùng reverse DNS như bằng chứng danh tính của một dịch vụ**. PTR record có thể thiếu, không đồng nhất với forward records, hoặc không phản ánh quyền kiểm soát ứng dụng. Với HTTPS, xác thực server phải dựa vào TLS certificate và tên máy hợp lệ theo giao thức, không chỉ dựa vào kết quả reverse DNS.

**getHostName()** có thể trả tên đã gắn với đối tượng hoặc kích hoạt lookup nếu chưa có; khi chỉ cần biểu diễn IP cho logging, dùng **getHostAddress()** để tránh lookup ngược không cần thiết.

## 18. InetAddress caching và DNS TTL

Để giảm truy vấn lặp lại, **InetAddress có bộ nhớ đệm cho cả kết quả thành công và thất bại**. Chính sách cache ảnh hưởng đến khả năng phản ánh thay đổi DNS và tải của hệ thống phân giải.

Những **Java security properties** hiện hành:

| Property | Ý nghĩa |
|---|---|
| **networkaddress.cache.ttl** | Khoảng thời gian cache kết quả phân giải thành công |
| **networkaddress.cache.negative.ttl** | Khoảng thời gian cache kết quả phân giải thất bại |
| **networkaddress.cache.stale.ttl** | Khoảng thời gian có thể giữ dữ liệu cũ khi làm mới không thành công, theo chính sách |

Một số giá trị:

- **0** thường có nghĩa không cache theo loại tương ứng.
- **-1** có ý nghĩa cache không thời hạn đối với positive/negative TTL khi được hỗ trợ theo tài liệu.
- Các giá trị dương thường biểu diễn số giây.

**Các giá trị mặc định có thể phụ thuộc phiên bản và implementation**, vì vậy không nên viết mã dựa vào một TTL dương cố định cho mọi Java runtime. Theo tài liệu Java SE 27, negative TTL mặc định thông dụng là 10 giây; TTL thành công có thể mang giá trị tùy implementation.

Đây là **security properties** của Java, **không phải** mặc nhiên là các system properties có thể điều khiển ổn định bằng **-Dnetworkaddress.cache.ttl=...** ở mọi cấu hình. Nếu cần điều chỉnh, hãy sử dụng cơ chế cấu hình security properties của runtime và kiểm thử trên JDK đang triển khai.

**Không đổi TTL toàn cục chỉ để sửa một request riêng lẻ.** Cache là chính sách ở phạm vi quá trình/runtime, có thể tác động đến mọi client trong cùng JVM.

## 19. DNS không giống phép kiểm tra HTTP health

Phân giải được IP chỉ chứng minh tên đã có một kết quả địa chỉ tại thời điểm tra cứu; nó **không chứng minh**:

- Máy có thể nhận kết nối TCP tới port cần thiết.
- TLS handshake sẽ thành công hoặc chứng chỉ hợp lệ.
- Reverse proxy định tuyến đến đúng ứng dụng.
- Endpoint HTTP sẵn sàng hoặc trả trạng thái 2xx.
- Client có route, quyền mạng, proxy và firewall phù hợp.

~~~text
Hostname resolve OK
        ≠
TCP connect OK
        ≠
TLS validate OK
        ≠
HTTP request successful
~~~

**InetAddress.isReachable(timeout)** cũng không phải kiểm tra sức khỏe HTTP. Cách xác định reachability có thể phụ thuộc hệ điều hành, đặc quyền và cơ chế mạng (ví dụ ICMP hoặc phương án thay thế); một dịch vụ HTTPS đang hoạt động vẫn có thể không trả lời theo phương thức này.

Khi cần kiểm tra khả dụng của API, sử dụng HTTP request phù hợp với health endpoint có quyền truy cập và timeout rõ ràng, không dùng kết quả DNS hoặc ICMP để thay thế.

## 20. InetSocketAddress: kết hợp hostname/IP với port

**InetSocketAddress** đại diện cho một địa chỉ socket gồm hostname hoặc IP và port. Nó được sử dụng trong các API TCP/UDP socket và một số cấu hình proxy.

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

InetSocketAddress resolved =
    new InetSocketAddress("example.com", 443);

System.out.println(resolved.getPort()); // 443
System.out.println(resolved.isUnresolved());
// Phụ thuộc khả năng phân giải hostname tại môi trường chạy

InetSocketAddress literal =
    new InetSocketAddress(
        InetAddress.ofLiteral("127.0.0.1"), 8080
    );

System.out.println(literal.isUnresolved()); // false
~~~

Constructor nhận **String hostname** cố gắng phân giải hostname; nếu thất bại, địa chỉ có thể tồn tại dưới dạng **unresolved**.

Nếu muốn tạo một endpoint **chưa thực hiện DNS lookup**:

~~~java
InetSocketAddress unresolved =
    InetSocketAddress.createUnresolved("example.com", 443);

System.out.println(unresolved.isUnresolved()); // true
System.out.println(unresolved.getAddress());   // null
System.out.println(unresolved.getHostString()); // example.com
~~~

**getHostString()** phù hợp để lấy chuỗi hostname không kích hoạt reverse lookup ngoài ý muốn trong những trường hợp thích hợp, khác với một số đường đi của **getHostName()**.

Không được giả định unresolved socket address tự kết nối được trong mọi API. Cách xử lý phụ thuộc loại socket/client/proxy và việc tên cuối cùng được phân giải ở đâu.

## 21. Tên miền quốc tế với IDN và Punycode

Tên miền có thể chứa ký tự ngoài ASCII, ví dụ **bücher.example**. DNS theo quy tắc IDN thường sử dụng dạng ASCII Compatible Encoding (**ACE**, thường gọi Punycode cho phần nhãn được mã hóa).

Java cung cấp **java.net.IDN**:

~~~java
import java.net.IDN;

String unicodeHost = "bücher.example";

String asciiHost = IDN.toASCII(
    unicodeHost,
    IDN.USE_STD3_ASCII_RULES
);

System.out.println(asciiHost);
// xn--bcher-kva.example

System.out.println(IDN.toUnicode(asciiHost));
// bücher.example
~~~

**IDN.toASCII** chuyển tên miền Unicode thành dạng ASCII theo cơ chế mà Java API mô tả, dựa trên mô hình IDNA trong tài liệu lớp. **toUnicode** dùng cho biểu diễn/hiển thị khi phù hợp.

Tuy nhiên:

- **Không truyền cả URI cho IDN.toASCII**; nó nhận **domain name**, không nhận scheme, path và query.
- **Không áp dụng IDN.toASCII lên IPv6 literal** hoặc IP literal nói chung.
- **IDN Java không phải trình xác minh quyền sở hữu domain**.
- Các phiên bản chuẩn IDNA và chính sách Unicode của các hệ sinh thái có thể khác nhau; khi tương tác với hạ tầng cụ thể, cần kiểm tra hợp đồng tên miền mà hệ thống hỗ trợ.
- Tên miền nhìn gần giống nhau (*homograph*) có thể được tạo từ ký tự của nhiều bảng chữ khác nhau. Chuyển đổi sang ACE **không thay thế kiểm soát spoofing**.

## 22. Dựng URI cho hostname quốc tế

Để tránh hành vi phân tích host không như mong muốn, có thể chuẩn hóa **hostname Unicode thành ASCII** trước rồi tạo URI:

~~~java
import java.net.IDN;
import java.net.URI;

String asciiHost = IDN.toASCII(
    "bücher.example",
    IDN.USE_STD3_ASCII_RULES
);

URI endpoint = new URI(
    "https",
    null,
    asciiHost,
    443,
    "/sản phẩm",
    "lang=vi",
    null
);

System.out.println(endpoint.getHost());
// xn--bcher-kva.example

System.out.println(endpoint.getPath());
// /sản phẩm

System.out.println(endpoint.toASCIIString());
// URI ASCII với hostname ACE và path percent-encoded
~~~

**Chuyển đổi IDN không đồng nghĩa kiểm tra domain đang tồn tại.** Ở ví dụ, **.example** là miền dành cho tài liệu. Không chạy lookup rồi mặc định DNS sẽ có bản ghi phù hợp.

Nếu dữ liệu có thể chứa IPv4 hoặc IPv6 literal thay vì domain, nên xác định loại input ngay từ đầu. Một cách xử lý duy nhất gọi **IDN.toASCII** cho mọi loại host có thể làm sai địa chỉ IP, nhất là IPv6 có dấu hai chấm.

## 23. Dùng URI với HttpClient trong Java hiện đại

Sau khi phân tích và xác thực URI theo chính sách, ứng dụng có thể xây request với **java.net.http.HttpClient**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

URI endpoint = URI.create("https://example.com/");

HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

HttpRequest request = HttpRequest.newBuilder(endpoint)
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();

// Đoạn dưới có network I/O; chỉ chạy khi được phép truy cập endpoint.
// HttpResponse<String> response = client.send(
//     request, HttpResponse.BodyHandlers.ofString()
// );
// System.out.println(response.statusCode());
~~~

Các điểm cần nhớ:

- **URI** xác định scheme/host/port/path/query của request.
- **HttpClient** xử lý kết nối, proxy, TLS, HTTP protocol và có thể sử dụng DNS/resolver của runtime.
- **connectTimeout** điều chỉnh thời gian dành cho việc thiết lập kết nối trong phạm vi hợp đồng API.
- **HttpRequest.timeout** áp dụng giới hạn cho yêu cầu theo cơ chế của client; không có nghĩa một API ở xa luôn chấm dứt công việc server ngay khi client hết hạn.
- **Redirects** có thể dẫn tới hostname khác; việc bật follow redirects phải đi kèm chính sách tin cậy tương ứng.

Không dùng **new URL(...).openConnection()** như lựa chọn mặc định cho code HTTP mới khi HttpClient chuẩn cung cấp API phù hợp hơn cho request/response, timeout và xử lý bất đồng bộ.

## 24. URI.getHost() null và parseServerAuthority

Một số URI parse được ở mức cú pháp chung nhưng có **authority không thể tách thành host và port** theo định dạng server-based. Vì thế:

~~~java
URI uri = URI.create("https://example.com:badport/path");

System.out.println(uri.getAuthority());
// example.com:badport

System.out.println(uri.getHost());
// null (không phân tích được như server-based authority)
~~~

Khi API yêu cầu địa chỉ HTTP hợp lệ, có thể gọi:

~~~java
import java.net.URI;
import java.net.URISyntaxException;

static URI requireServerAuthority(URI candidate)
        throws URISyntaxException {

    URI checked = candidate.parseServerAuthority();

    if (checked.getHost() == null || checked.getHost().isBlank()) {
        throw new IllegalArgumentException("Host is required");
    }

    return checked;
}
~~~

**parseServerAuthority()** giúp yêu cầu authority phải thỏa cú pháp server-based; nó vẫn không tự kiểm tra scheme được phép, host có thuộc allowlist, DNS đang trỏ đến đâu, hoặc HTTP endpoint có đáng tin cậy không.

Với URI do người dùng nhập, nên bắt **URISyntaxException** và phản hồi lỗi đầu vào thích hợp. Với URI hằng số do code sở hữu, **URI.create** có thể đủ cho thao tác khởi tạo, nhưng vẫn cần chính sách riêng nếu nó được dùng để truy cập hệ thống khác.

## 25. Bảo mật: tránh SSRF với địa chỉ do người dùng kiểm soát

**Server-Side Request Forgery (SSRF)** xảy ra khi một hệ thống server có khả năng truy cập mạng bị điều khiển để gửi yêu cầu đến đích không được phép, ví dụ tài nguyên mạng nội bộ hoặc dịch vụ metadata của môi trường triển khai.

**Không gửi HTTP request tùy ý đến URI do người dùng cung cấp mà không có chính sách egress rõ ràng.**

Các bước phòng vệ cần kết hợp:

1. **Giới hạn scheme**: với một API chỉ tải nội dung HTTPS, chỉ cho phép **https**; không chấp nhận **file**, **jar**, **mailto**, **ftp** hay bất kỳ scheme tùy ý nào.
2. **Kiểm tra host**: host phải hiện diện, phân tích được và thuộc danh sách đích cho phép. Nếu có thể, dùng **allowlist chính xác** thay vì regex hoặc so hậu tố thiếu dấu ranh giới.
3. **Kiểm tra port**: chỉ những port được phép theo nhu cầu dịch vụ.
4. **Kiểm soát DNS và IP đích thực sự**: phải xét tất cả địa chỉ phân giải được, gồm IPv4, IPv6, loopback, link-local, private/unique-local và các dải đặc biệt khác theo chính sách mạng.
5. **Đề phòng DNS rebinding và TOCTOU**: nếu tra DNS để kiểm tra rồi HTTP client tự phân giải lần nữa khi connect, IP có thể đổi giữa hai bước. Cần thiết kế một cơ chế kiểm soát ở **thời điểm kết nối** hoặc egress proxy/gateway thực thi chính sách, không chỉ kiểm tra một lần.
6. **Kiểm tra redirects**: một URI ban đầu được phép có thể trả redirect sang đích cấm. Tắt tự động theo dõi hoặc kiểm tra lại mọi hop.
7. **Giới hạn tài nguyên**: timeout, kích thước phản hồi, số redirect, tần suất và lượng dữ liệu tải.
8. **Quản lý chứng thực**: không tự bỏ kiểm tra TLS hostname/certificate khi cần truy cập đích HTTPS.

**Lưu ý:** **InetAddress.isSiteLocalAddress()** hoặc **isLoopbackAddress()** có thể hỗ trợ một số bước kiểm tra, nhưng **không phải bộ lọc SSRF đầy đủ**. Địa chỉ đặc biệt có nhiều loại, hệ thống có thể có NAT, proxy, IPv4-mapped IPv6 và nhiều cách diễn giải địa chỉ. Không chỉ kiểm tra chuỗi host hoặc một flag rồi kết luận mọi đích mạng đều an toàn.

## 26. DNS rebinding và giới hạn của kiểm tra trước

Một thiết kế chưa đủ an toàn:

~~~text
Bước 1: resolve hostname → nhận IP cho phép
Bước 2: kiểm tra IP → PASS
Bước 3: HttpClient tự resolve lại hostname
Bước 4: kết nối đến IP có thể đã đổi
~~~

Khoảng cách thời gian giữa bước kiểm tra và bước kết nối gọi là một dạng **time-of-check/time-of-use (TOCTOU)**. DNS TTL, cache, nhiều địa chỉ và load balancing có thể khiến kết quả thay đổi.

**Không coi đoạn mã sau là giải pháp SSRF hoàn chỉnh:**

~~~java
// Chỉ mang tính minh họa về giới hạn kiểm tra trước.
InetAddress[] candidates = InetAddress.getAllByName(hostname);

for (InetAddress address : candidates) {
    if (address.isLoopbackAddress()) {
        throw new IllegalArgumentException("Forbidden destination");
    }
}

// Việc kết nối riêng sau đó có thể phân giải lại,
// và chưa kiểm tra đầy đủ các loại địa chỉ đặc biệt.
~~~

Đối với hệ thống nhận URI bên ngoài, giải pháp đáng tin cậy hơn thường là chỉ cho phép **đích được cấu hình sẵn**, hoặc thực thi chính sách egress qua một tầng có khả năng kiểm soát IP **đã được chọn để kết nối** và mọi chuyển hướng. Không tự tạo một “URL validator” đơn giản và coi đó là ranh giới bảo mật duy nhất.

## 27. TLS hostname và chứng chỉ không thể thay bằng DNS

Khi thiết lập HTTPS:

- DNS giúp tìm IP ứng viên cho hostname.
- TCP kết nối đến endpoint mạng.
- TLS xác thực chứng chỉ theo hostname, trust configuration và các quy tắc giao thức.
- HTTP gửi request đến tài nguyên.

Một **DNS response hợp lệ không chứng minh server là bên được phép đại diện cho hostname**. Tương tự, reverse DNS có tên đẹp không phải bằng chứng về chứng chỉ TLS.

Vì vậy:

- Không tắt hostname verification hoặc trust validation chỉ để “chạy được” trên mạng không đúng cấu hình.
- Không nhúng bí mật vào user-info của URI.
- Không log đầy đủ URI có query tokens khi request chứa dữ liệu nhạy cảm.
- Không coi một IP cố định là cách tự động thay thế kiểm tra danh tính của server HTTPS.

Dùng **HttpClient** với cơ chế TLS chuẩn và cấu hình trust phù hợp với hạ tầng thật. Khi qua proxy hoặc load balancer, cần hiểu rõ nơi nào chịu trách nhiệm resolution và kiểm soát endpoint.

## 28. Debug lỗi mạng theo từng tầng

| Hiện tượng | Tầng nghi vấn | Hướng kiểm tra |
|---|---|---|
| **URISyntaxException** | URI syntax | Scheme, phần host/authority, percent-encoding và dấu phân cách |
| **uri.getHost() == null** | URI parsing / authority | URI có opaque/relative? Authority server-based hợp lệ? |
| **UnknownHostException** | Resolver | Tên miền, cấu hình mạng, bản ghi A/AAAA, cache âm, DNS nội bộ |
| DNS trả địa chỉ nhưng connect lỗi | Routing/TCP | Port, firewall, route, proxy, listener |
| **ConnectException** | TCP connection | Không có listener, từ chối kết nối hoặc chính sách mạng |
| **HttpConnectTimeoutException** | Kết nối HTTP client | Ngân sách kết nối, địa chỉ đích, mạng |
| **HttpTimeoutException** | Request HTTP client | Thời gian toàn request, server latency, tài nguyên |
| TLS handshake lỗi | TLS/PKI | Trust store, chứng chỉ, hostname, protocol, môi trường |
| HTTP 401/403 | Application/security | Authentication, authorization; DNS không phải nguyên nhân trực tiếp |
| HTTP 404 | HTTP routing/application | Path, resource, router, context path |
| HTTP 5xx | Server/dependency | Log/tracing của server, downstream failures |
| Chỉ lỗi ở IPv6 | IP/route/DNS | Hạ tầng IPv6, địa chỉ AAAA, firewall và lựa chọn kết nối |
| Chỉ lỗi khi chạy module/CI | Runtime environment | Proxy, DNS resolver, hosts, firewall, container network, JDK configuration |

Không dùng lỗi DNS để kết luận tài nguyên HTTP không tồn tại, và không dùng HTTP 404 để kết luận hostname không được phân giải. Tách từng tầng giúp điều tra nhanh và tránh thay đổi cấu hình sai chỗ.

## 29. Ví dụ hoàn chỉnh không cần mạng: phân tích URI, IDN và IP literal

Lưu mã vào tệp **UriAndNetworkDemo.java**. Ví dụ cố ý **không thực hiện DNS lookup hoặc HTTP request**, vì mục tiêu là học cú pháp và các kiểu giá trị trước khi kết nối mạng.

~~~java
import java.net.IDN;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URISyntaxException;

public class UriAndNetworkDemo {
    static void showUri(URI uri) {
        System.out.println("scheme=" + uri.getScheme());
        System.out.println("host=" + uri.getHost());
        System.out.println("port=" + uri.getPort());
        System.out.println("rawPath=" + uri.getRawPath());
        System.out.println("path=" + uri.getPath());
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("fragment=" + uri.getFragment());
    }

    public static void main(String[] args)
            throws URISyntaxException {

        // 1. Phân tích một URI mà không kết nối mạng.
        URI resource = URI.create(
            "https://example.com:8443/a%20b?q=java%20http#section"
        );
        showUri(resource);

        // 2. Resolve một reference tương đối.
        URI base = URI.create("https://example.com/docs/");
        URI article = base.resolve("networking.html");

        System.out.println("resolved=" + article);

        // 3. Chuyển hostname quốc tế sang dạng ASCII.
        String asciiHost = IDN.toASCII(
            "bücher.example",
            IDN.USE_STD3_ASCII_RULES
        );

        URI internationalized = new URI(
            "https", null, asciiHost, 443,
            "/sản phẩm", "lang=vi", null
        );

        System.out.println("idnHost=" + internationalized.getHost());
        System.out.println("idnUri=" + internationalized.toASCIIString());

        // 4. Phân tích địa chỉ IP literal - không DNS.
        InetAddress loopback4 = InetAddress.ofLiteral("127.0.0.1");
        InetAddress loopback6 = InetAddress.ofLiteral("::1");

        System.out.println("ipv4Loopback="
            + loopback4.isLoopbackAddress());
        System.out.println("ipv6Loopback="
            + loopback6.isLoopbackAddress());

        // 5. Tạo endpoint hostname + port nhưng chưa phân giải.
        InetSocketAddress unresolved =
            InetSocketAddress.createUnresolved("example.com", 443);

        System.out.println("unresolved=" + unresolved.isUnresolved());
        System.out.println("socketHost=" + unresolved.getHostString());
        System.out.println("socketPort=" + unresolved.getPort());
    }
}
~~~

Biên dịch và chạy với JDK 27:

~~~bash
javac -encoding UTF-8 UriAndNetworkDemo.java
java UriAndNetworkDemo
~~~

Các dòng kết quả dự kiến:

~~~text
scheme=https
host=example.com
port=8443
rawPath=/a%20b
path=/a b
rawQuery=q=java%20http
fragment=section
resolved=https://example.com/docs/networking.html
idnHost=xn--bcher-kva.example
idnUri=https://xn--bcher-kva.example:443/s%E1%BA%A3n%20ph%E1%BA%A9m?lang=vi
ipv4Loopback=true
ipv6Loopback=true
unresolved=true
socketHost=example.com
socketPort=443
~~~

**Giải thích:** URI chỉ được phân tích và biến đổi; hostname IDN được mã hóa; hai IP loopback được parse trực tiếp qua ofLiteral; endpoint được tạo ở trạng thái unresolved. Không có DNS network request nên kết quả không lệ thuộc vào Internet hoặc DNS của máy chạy.

Các ví dụ **InetAddress.getAllByName** và **HttpClient.send** ở những phần trước mới là các thao tác có thể cần truy cập môi trường mạng thật, và nên được kiểm thử tích hợp riêng.

## 30. Kiểm thử và hợp đồng đầu vào

Khi xây một thư viện xử lý URI, nên kiểm thử tách ba mức:

**Kiểm thử thuần túy không cần mạng:**

- Parse URI tuyệt đối/tương đối, opaque/hierarchical.
- Lấy scheme, host, port, path, query, fragment.
- So sánh raw/decoded của percent-encoded path.
- Thử base URI có và không có dấu **/** cuối đường dẫn.
- Thử IPv6 literal trong authority với dấu **[ ]**.
- Kiểm tra **InetAddress.ofLiteral** với IPv4/IPv6 hợp lệ và chuỗi sai.
- Chuyển đổi **IDN.toASCII** và không đưa cả URI vào hàm.
- Kiểm tra danh sách scheme và host hợp lệ theo chính sách ứng dụng.

**Kiểm thử tích hợp có mạng được kiểm soát:**

- Resolver trả nhiều địa chỉ/không có địa chỉ/thất bại tạm thời.
- Ứng dụng qua proxy, đổi DNS, IPv4/IPv6.
- Kết nối bị từ chối, HTTP timeout, TLS certificate không hợp lệ.
- Redirect đến host khác và chính sách từ chối.
- Cache, latency và giới hạn kích thước response.

**Kiểm thử bảo mật:**

- URI không thuộc scheme/host/port được phép.
- Tên miền nhầm lẫn vì suffix, Unicode confusables hoặc case.
- DNS trả địa chỉ nội bộ hoặc thay đổi địa chỉ giữa check và connect.
- Path đã percent-encode nhiều lớp hoặc được chuẩn hóa khác nhau giữa các tầng.
- URI chứa credentials hoặc token trong query/fragment và chính sách logging.

Không phải mọi test phải truy cập Internet. Phần lớn logic parse, IDN conversion, local IP literal và chính sách xử lý URI có thể kiểm thử hoàn toàn offline.

## 31. Những lỗi phổ biến

| Lỗi hoặc hiểu lầm | Nguyên nhân | Giải pháp |
|---|---|---|
| Coi URI là kết nối mạng | URI chỉ là cấu trúc định danh | Dùng HttpClient/Socket riêng khi cần giao tiếp |
| Ghép toàn bộ URI rồi URLEncoder.encode | Form encoding phá dấu **:**, **/**, **?** | Mã hóa đúng thành phần/giá trị |
| Bỏ qua **getRawPath** rồi decode thêm lần nữa | Double decoding làm thay đổi cấu trúc | Xác định rõ trạng thái raw/decoded |
| **URI.getHost()** null dù chuỗi có authority | URI tương đối/opaque hoặc authority không server-based | Kiểm tra scheme/authority và parseServerAuthority |
| resolve tạo URL khác host | Relative reference có authority/scheme riêng | Xác thực kết quả cuối cùng sau resolve |
| Path có **..** được normalize thì coi là an toàn | URI normalize không thay thế filesystem/security policy | Kiểm tra path ở đúng hệ thống đích |
| IPv6 với port không dùng ngoặc vuông | Dấu **:** mơ hồ trong authority | Dùng **[IPv6]:port** |
| getByName với hostname rỗng | Hành vi đặc biệt liên quan loopback | Tự kiểm tra nonblank trước |
| Dùng getByName chỉ để kiểm tra IP literal | Có thể kích hoạt DNS | Dùng **InetAddress.ofLiteral** |
| getAllByName chỉ trả một địa chỉ ở một máy | Resolver và mạng khác nhau | Không hardcode số lượng/thứ tự |
| UnknownHostException được coi là HTTP 404 | Lỗi phân giải tên khác lỗi resource | Phân loại đúng tầng mạng/ứng dụng |
| getCanonicalHostName làm code chậm | Có thể thực hiện reverse lookup | Dùng getHostAddress khi chỉ cần IP |
| isReachable false được coi là server chết | Reachability không phải HTTP health check | Kiểm tra endpoint theo giao thức |
| Dùng IDN.toASCII cho toàn URI | IDN xử lý tên miền, không phải scheme/path | Chỉ chuyển hostname |
| Dùng một IP đã kiểm tra trước làm bằng chứng SSRF an toàn | DNS có thể đổi trước khi connect | Enforce egress ở thời điểm kết nối |
| Bật redirects mà không xác thực đích tiếp theo | Redirect có thể dẫn tới host cấm | Tắt hoặc revalidate từng hop |
| Kiểm tra DNS thay TLS | DNS không xác thực danh tính ứng dụng | Giữ xác thực TLS hostname/certificate |

## 32. Bài tập thực hành

**Bài tập 1 — Phân tích URI.** Cho URI **https://example.com:8443/a%20b?q=java%20net#top**. In scheme, host, port, raw path, decoded path, raw query và fragment. Giải thích vì sao path đã giải mã không nên được đưa qua URLDecoder thêm lần nữa.

**Bài tập 2 — Resolve.** Cho base URI **https://example.com/api/v1/** và những reference **items**, **../health**, **/status**. Tính URI cuối cùng bằng resolve. Sau đó thay base thành **https://example.com/api/v1** và giải thích vì sao kết quả của **items** khác.

**Bài tập 3 — IDN.** Chuyển hostname **bücher.example** sang ACE bằng **IDN.toASCII**. Tạo URI HTTPS chứa hostname đó và một path tiếng Việt, rồi in **toASCIIString**.

**Bài tập 4 — IP literal.** Dùng **InetAddress.ofLiteral** cho **127.0.0.1**, **::1**, **192.0.2.1** và một chuỗi không phải địa chỉ. Quan sát loại IPv4/IPv6, loopback và ngoại lệ của dữ liệu sai.

**Bài tập 5 — DNS và môi trường.** Trên môi trường mạng được phép, dùng **getAllByName("example.com")** và ghi địa chỉ trả về. So sánh với máy/mạng khác, nhưng không viết test yêu cầu địa chỉ hoặc số bản ghi cố định.

**Bài tập 6 — InetSocketAddress.** So sánh **new InetSocketAddress("example.com",443)** và **createUnresolved("example.com",443)** về thời điểm phân giải, **isUnresolved** và **getHostString**.

**Bài tập 7 — HTTP health.** Viết một HttpClient request có **connectTimeout**, **request timeout**, không tự động follow redirects. Giải thích vì sao DNS thành công không đủ chứng minh endpoint trả 200.

**Bài tập 8 — Threat model.** Thiết kế dịch vụ tải ảnh từ những hostname được quản trị viên khai báo. Xác định policy cho scheme/host/port, giới hạn dung lượng, redirects, IP sau DNS và biện pháp chống DNS rebinding. Giải thích vì sao chỉ dùng **isSiteLocalAddress()** chưa đủ.

## 33. Checklist trước khi xử lý URI và địa chỉ mạng trong Java 27

- [ ] Dùng **URI** như giá trị định danh; không giả định parse URI thực hiện DNS.
- [ ] Phân biệt URI absolute/relative, opaque/hierarchical.
- [ ] Phân tích chính xác scheme, authority, host, port, path, query, fragment.
- [ ] Với HTTP URL, yêu cầu scheme cho phép và host hợp lệ.
- [ ] Không coi **getPort() == -1** là cổng âm; dùng quy tắc giao thức cho default.
- [ ] Dùng constructor theo thành phần hoặc URI builder phù hợp, tránh ghép chuỗi tùy tiện.
- [ ] Không dùng **URLEncoder** cho toàn bộ URI hoặc path.
- [ ] Phân biệt raw/decoded components và tránh double decoding.
- [ ] Sau **resolve** hoặc redirect, kiểm tra lại URI cuối theo chính sách.
- [ ] Không coi **normalize** là bộ lọc path traversal hoàn chỉnh.
- [ ] Viết IPv6 literal trong authority với ngoặc vuông.
- [ ] Dùng **InetAddress.ofLiteral** để parse IP literal mà không lookup DNS.
- [ ] Chỉ dùng **getAllByName** khi cần hostname resolution; chuẩn bị xử lý nhiều IP.
- [ ] Không phụ thuộc thứ tự, số lượng, hoặc địa chỉ cố định của DNS response.
- [ ] Phân biệt phân giải tên, kết nối TCP, TLS validation và HTTP status.
- [ ] Không dùng reverse DNS hoặc isReachable làm bằng chứng danh tính/sức khỏe HTTP.
- [ ] Hiểu cache TTL positive/negative/stale và phạm vi cấu hình runtime.
- [ ] Chỉ dùng **IDN.toASCII** cho hostname Unicode, xem xét rủi ro homograph.
- [ ] Với URI từ người dùng, có chính sách SSRF/egress, DNS rebinding, redirect và giới hạn tài nguyên.
- [ ] Giữ kiểm tra TLS certificate/hostname; không nhúng credentials vào URI.
- [ ] Phân biệt test offline cho URI/IP literal với test tích hợp thực sự dùng mạng.
- [ ] Dùng **HttpClient** hiện hành cho HTTP thay vì phụ thuộc vào constructor URL deprecated.
- [ ] Trả lỗi theo đúng tầng: cú pháp URI, resolver, TCP/TLS hay HTTP ứng dụng.

**Kết luận:** Trong Java 27, URI mô tả **cấu trúc định danh tài nguyên**; InetAddress và các resolver liên quan chuyển hostname thành **địa chỉ IP**; InetSocketAddress kết hợp endpoint với **port**; còn HttpClient thực hiện **giao tiếp HTTP** qua mạng. Khi tách các tầng này rõ ràng, chương trình dễ kiểm thử, dễ chẩn đoán và ít phụ thuộc vào những giả định sai về DNS, IPv4/IPv6 hay cấu trúc URI. Với các URI do bên ngoài kiểm soát, còn cần một chính sách bảo mật áp dụng đến thời điểm kết nối thực tế chứ không chỉ kiểm tra chuỗi đầu vào.

## Tài liệu tham khảo

- [Java SE 27 — URI](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URI.html): thành phần URI, parse, resolve, normalize, raw/decoded và ASCII representation.
- [Java SE 27 — InetAddress](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): hostname resolution, IP literal, IPv4/IPv6, lookup cache và reverse lookup.
- [Java SE 27 — Inet4Address](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/Inet4Address.html), [Inet6Address](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/Inet6Address.html): địa chỉ IPv4/IPv6.
- [Java SE 27 — InetSocketAddress](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetSocketAddress.html): hostname/IP cùng port, resolved và unresolved.
- [Java SE 27 — IDN](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/IDN.html): chuyển tên miền Unicode/ASCII và lưu ý an toàn.
- [Java SE 27 — URLEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URLEncoder.html): form URL encoding theo UTF-8.
- [Java SE 27 — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html), [HttpRequest](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html): giao tiếp HTTP, URI và timeout.
- [Java SE 27 — URL](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URL.html): quan hệ URI/URL và chú ý về URL constructors.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): cấu trúc URI và percent-encoding ở cấp giao thức.
- [RFC 5737 — IPv4 Address Blocks Reserved for Documentation](https://www.rfc-editor.org/rfc/rfc5737): các địa chỉ IPv4 dùng trong ví dụ.
- [RFC 3849 — IPv6 Address Prefix Reserved for Documentation](https://www.rfc-editor.org/rfc/rfc3849): prefix IPv6 dành cho tài liệu.
