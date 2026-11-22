# URI tuyệt đối, tương đối, phân cấp và opaque trong Java

**Chủ đề:** Java Advance - networking  
**Nhóm kiến thức:** URI và URL

Một URI (**Uniform Resource Identifier**) là chuỗi dùng để **định danh** một tài nguyên hoặc đối tượng theo một scheme. URI có thể mô tả vị trí để truy cập (ví dụ một HTTP endpoint), một tên không gắn trực tiếp với vị trí mạng (ví dụ URN), hoặc một tham chiếu được hiểu dựa trên URI nền (base URI). Trong Java, **java.net.URI** giúp phân tích, xây dựng, chuẩn hóa và kết hợp các URI theo cú pháp; chỉ việc tạo hoặc phân tích URI **không** tự thực hiện DNS, mở socket hay gửi HTTP request.

Bốn từ **tuyệt đối (absolute)**, **tương đối (relative)**, **phân cấp (hierarchical)** và **opaque** mô tả **hai trục phân loại khác nhau** trong API Java, không phải bốn loại loại trừ nhau. Hiểu đúng hai trục này là nền tảng để gọi **URI.resolve(...)**, **URI.relativize(...)**, **URI.normalize(...)**, xử lý path, query, fragment và tránh nhầm lẫn khi kết hợp URL từ dữ liệu người dùng.

## 1. URI là gì? Phân biệt định danh với truy cập mạng

Các chuỗi sau đều có thể được biểu diễn bằng **java.net.URI**:

~~~text
https://example.org/docs/guide.html?lang=vi#syntax
mailto:hello@example.org
urn:isbn:9780134685991
../images/logo.svg
/help
//cdn.example.org/assets/app.js
#overview
~~~

- **https://...** có scheme chỉ giao thức truy cập phổ biến, authority (máy chủ), path, query và fragment.
- **mailto:...** định danh một địa chỉ thư theo scheme mailto; không có nghĩa mọi URI đều là HTTP URL.
- **urn:...** định danh bằng URN, thường không mang cấu trúc host/path HTTP.
- Các chuỗi **../images/logo.svg**, **/help**, **//cdn.example.org/...** và **#overview** không có scheme; chúng là tham chiếu tương đối, phải có ngữ cảnh/base URI để xác định đích đầy đủ khi cần.

**URI** là khái niệm nhận diện tài nguyên và cú pháp tham chiếu. **URL** là cách chỉ một tài nguyên theo cơ chế định vị/truy cập. Trong Java, **URI** là đối tượng cú pháp bất biến, còn **URL** gắn với những cơ chế xử lý giao thức. **URI.toURL()** chỉ thích hợp khi URI là tuyệt đối và scheme có thể được xử lý thành URL. Một **urn:isbn:...** hoàn toàn hợp lệ như URI nhưng không nhất thiết có cách mở trực tiếp qua network bằng URL handler. Việc gọi **URL.openConnection()** hay HTTP client mới có thể bắt đầu hoạt động I/O theo API và cấu hình.

## 2. Hai trục phân loại độc lập trong java.net.URI

### Trục A: tuyệt đối hay tương đối?

Trong **java.net.URI**, **isAbsolute() == true** khi và chỉ khi URI có **scheme** (như **https:**, **file:**, **mailto:**, **urn:**). Nếu không có scheme thì **isAbsolute() == false**, Java gọi đó là URI tương đối. Mọi URI opaque đều tuyệt đối; mọi URI tương đối đều phân cấp theo cách Java phân loại.

**Đừng nhầm dấu /** với tính tuyệt đối. Chuỗi **/docs/api** có path bắt đầu ở gốc của một authority nhưng **không có scheme**, nên Java vẫn báo **isAbsolute() == false**. Tương tự **//cdn.example.org/a.js** có authority nhưng thiếu scheme nên vẫn là tương đối.

### Trục B: phân cấp hay opaque?

Theo **java.net.URI**, một URI **opaque** là URI **tuyệt đối** mà **scheme-specific part** (phần sau **scheme:**, trước fragment) **không bắt đầu bằng /**. Java không tách phần này thành authority/path/query theo cấu trúc phân cấp; muốn diễn giải phải hiểu scheme cụ thể.

URI **phân cấp** là URI tương đối, hoặc URI tuyệt đối có scheme-specific part bắt đầu bằng **/**. Nó có thể được tách thành các thành phần **authority**, **path**, **query**, **fragment** và có các thao tác path phù hợp.

| Ví dụ | isAbsolute() | isOpaque() | Cách hiểu trong Java |
| --- | --- | --- | --- |
| **https://example.org/a** | true | false | Tuyệt đối, phân cấp |
| **file:/tmp/data.txt** | true | false | Tuyệt đối, phân cấp |
| **mailto:hello@example.org** | true | true | Tuyệt đối, opaque |
| **urn:isbn:9780134685991** | true | true | Tuyệt đối, opaque |
| **https:report** | true | true | Tuyệt đối, opaque **theo Java**, dù đây không phải địa chỉ HTTPS thông thường |
| **docs/page.html** | false | false | Tương đối, phân cấp |
| **../img/logo.svg** | false | false | Tương đối, phân cấp |
| **/help** | false | false | Tương đối, phân cấp; path bắt đầu bằng /** |
| **//cdn.example.org/app.js** | false | false | Tương đối, phân cấp; có authority, chưa có scheme |
| **?page=2** hoặc **#part** | false | false | Tương đối, phân cấp; tham chiếu chỉ thay query/fragment tùy phép resolve |

**Không tồn tại URI vừa relative vừa opaque theo định nghĩa Java.** “Absolute” nói về **có scheme hay không**; “hierarchical/opaque” nói về **cách parse phần đặc thù của scheme**. Vì vậy không thể nói đơn giản “URI tuyệt đối là hierarchical” hoặc “opaque là relative”.

**Ghi chú về thuật ngữ chuẩn:** **RFC 3986** có cú pháp **absolute-URI** riêng không bao gồm fragment, trong khi method Java **URI.isAbsolute()** chỉ kiểm tra có scheme và vẫn trả **true** cho **https://example.org/a#part**. Khi đối chiếu văn bản tiêu chuẩn với Java API, hãy xác định đang nói về grammar RFC hay predicate của Java.

## 3. Cấu trúc URI phân cấp

Một dạng dễ nhận diện là:

~~~text
[scheme:][//authority]path[?query][#fragment]

https://user@example.org:8443/docs/a.html?lang=vi#part
└scheme┘└──────authority──────┘└──path───┘└query┘└fragment┘
~~~

Ở dạng có authority, **authority** có thể bao gồm **userinfo@host:port**. Các thành phần thường được truy xuất bằng API:

| Thành phần | Ví dụ | API |
| --- | --- | --- |
| Scheme | **https** | **getScheme()** |
| Authority | **user@example.org:8443** | **getAuthority()**, **getRawAuthority()** |
| Userinfo | **user** | **getUserInfo()** |
| Host | **example.org** | **getHost()** |
| Port | **8443** | **getPort()**, trả **-1** nếu không xác định |
| Path | **/docs/a.html** | **getPath()**, **getRawPath()** |
| Query | **lang=vi** | **getQuery()**, **getRawQuery()** |
| Fragment | **part** | **getFragment()**, **getRawFragment()** |

Trong URI **https://example.org/docs/a.html?lang=vi#part**, dấu **?** mở đầu query và **#** mở đầu fragment. Fragment dùng để chỉ một phần trong biểu diễn tài nguyên; nó thường **không được gửi trong HTTP request-target**. Query thuộc URI, nhưng không phải mọi scheme đều dùng query theo cách HTTP dùng. **getHost()** có thể trả **null** dù chuỗi có authority nếu authority không parse được như server-based authority; khi cần yêu cầu host/port chuẩn, xem **parseServerAuthority()** hoặc xác thực cấu trúc rõ ràng.

Phải phân biệt **raw** với **decoded**:

~~~java
URI uri = URI.create("https://example.org/a%20b?q=x%2Fy");
// uri.getRawPath()  -> "/a%20b"
// uri.getPath()     -> "/a b"
// uri.getRawQuery() -> "q=x%2Fy"
// uri.getQuery()    -> "q=x/y"
~~~

Đoạn trên là các biểu thức minh họa, không phải chương trình Java độc lập. **getRawPath()** giữ percent-encoding của phần path; **getPath()** trả phần đã decode. Đừng ghép trực tiếp dữ liệu decoded trở lại chuỗi URI nếu chưa encode và phân tích đúng từng thành phần.

Một số điểm dễ bỏ sót:

- **Host** có thể là tên miền, IPv4 hoặc IPv6 trong dấu ngoặc vuông (ví dụ **https://[2001:db8::1]:8443/a**).
- **Authority** không phải lúc nào cũng có; URI tuyệt đối phân cấp **file:/tmp/a** có path nhưng không cần host.
- **Path bắt đầu bằng /** và **URI có scheme** là hai điều khác nhau.
- Dấu **:** trong đoạn đầu tiên của relative path có thể bị hiểu thành scheme. **notes:today.txt** được Java coi là absolute/opaque với scheme **notes**; dùng **./notes:today.txt** nếu thực sự muốn một đường dẫn tương đối có dấu hai chấm.
- **URI** chỉ parse cú pháp; **InetAddress**, DNS và kết nối mạng thuộc những hoạt động khác.

## 4. URI opaque: phần sau scheme không phải path phân cấp

Ví dụ:

~~~text
mailto:hello@example.org?subject=Welcome
urn:isbn:9780134685991
news:comp.lang.java
~~~

Trong Java, **URI.create("mailto:hello@example.org?subject=Welcome")** có:

- **getScheme()** là **mailto**.
- **isAbsolute()** là **true** và **isOpaque()** là **true**.
- **getSchemeSpecificPart()** là **hello@example.org?subject=Welcome**.
- **getPath()**, **getQuery()** và **getHost()** là **null** vì Java không phân tích opaque URI thành các thành phần phân cấp, dù bản thân scheme mailto có quy tắc riêng để diễn giải dấu **?**.

Cần dùng **getSchemeSpecificPart()** hoặc **getRawSchemeSpecificPart()** để lấy phần đặc thù, rồi xử lý theo quy tắc của scheme; **không** tìm địa chỉ mail bằng **getHost()**, **không** cho rằng dấu **?** trong opaque URI sẽ xuất hiện trong **getQuery()**.

Các phép biến đổi dùng đường dẫn không có cùng ý nghĩa với opaque URI: **normalize()** không thay đổi nội dung opaque; nếu gọi **opaqueBase.resolve(relativeReference)**, Java trả về reference được truyền vào, thay vì tự suy ra cây thư mục cho địa chỉ mail/URN. Đặc tính opaque là **quy tắc phân tích của java.net.URI**, không phải tuyên bố rằng mọi scheme đều không có cấu trúc nội bộ. Ví dụ scheme **mailto** vẫn có cấu trúc riêng, chỉ không phải cấu trúc authority/path/query generic của API Java.

## 5. URI tương đối và phép resolve với base

Tham chiếu tương đối chỉ đủ ý nghĩa khi biết **base URI**. Ví dụ tài liệu hiện tại là:

~~~text
https://example.org/docs/guide/index.html?old=1
~~~

Đường dẫn tương đối không dấu **/** ở đầu thường được nối vào **thư mục chứa** tài liệu base, thay vì nối thêm vào cuối tên tệp. Với **java.net.URI.resolve(...)**, các trường hợp sau cho kết quả:

| Reference | base.resolve(reference) | Ý nghĩa |
| --- | --- | --- |
| **chapter.html** | **https://example.org/docs/guide/chapter.html** | Cùng thư mục base |
| **../img/logo.svg** | **https://example.org/docs/img/logo.svg** | Lùi một cấp thư mục |
| **/help** | **https://example.org/help** | Root-path của cùng authority |
| **//cdn.example.org/app.js** | **https://cdn.example.org/app.js** | Thay authority, giữ scheme **https** |
| **#intro** | **https://example.org/docs/guide/index.html?old=1#intro** | Thay fragment, giữ path và query base |
| **https://other.example/a** | **https://other.example/a** | URI đã tuyệt đối; không ghép với base |
| **?page=2** | **https://example.org/docs/guide/?page=2** | Kết quả riêng của **java.net.URI.resolve** đối với query-only reference trong ví dụ này |

**Chú ý trường hợp query-only:** Java **URI.resolve("?page=2")** theo cách triển khai và tài liệu **java.net.URI** có thể khác kết quả mà trình duyệt hoặc thuật toán resolve của **RFC 3986** cho cùng base. Với base có tên tệp **index.html**, Java trả đường dẫn thư mục **/docs/guide/** trong ví dụ trên. Không suy đoán từ quy tắc của browser; hãy kiểm thử chính API và JDK được dùng. Tương tự, một relative reference rỗng (**""**) không nên được mặc định là phép thay query đúng ý định của ứng dụng.

Phép resolve chỉ **tính ra một URI mới**, không truy vấn mạng hoặc kiểm tra đích có tồn tại. **base.resolve("https://other.example/a")** trả nguyên tham chiếu tuyệt đối dù khác host. Nếu dữ liệu tham chiếu do người dùng cung cấp, điều này có thể làm thay đổi domain đích và tạo lỗ hổng điều hướng/SSRF nếu chương trình sử dụng kết quả để mở kết nối mà không kiểm tra.

### Các tên gọi dễ nhầm trong relative reference

- **Relative-path reference**: **assets/app.js**, **../img.png**, **./notes.txt** — phụ thuộc thư mục của base.
- **Absolute-path reference**: **/api/users** — path tính từ gốc authority, **không** mang scheme nên URI vẫn relative.
- **Network-path reference**: **//cdn.example.org/app.js** — chỉ định authority, kế thừa scheme.
- **Query-only/fragment-only reference**: **?lang=vi**, **#summary** — tác động lên thành phần tương ứng theo quy tắc resolver.

“Absolute-path” là thuật ngữ nói về **path**, không đồng nghĩa với **absolute URI**.

## 6. normalize() và relativize(): khác resolve() ở đâu?

**normalize()** xử lý các segment đường dẫn **.** và **..** trong URI phân cấp, ví dụ:

~~~text
https://example.org/a/./b/../c
                    ↓ normalize()
https://example.org/a/c
~~~

**normalize()** không truy vấn server, không kiểm tra file tồn tại, không giải quyết redirect, không tự cung cấp HTTPS, không tự loại bỏ toàn bộ khác biệt percent-encoding và không phải công cụ ngăn path traversal hoàn chỉnh. Với opaque URI, normalization không thay đổi scheme-specific part theo cây path. Đừng tin rằng normalize một chuỗi không đáng tin cậy là đủ để cấp quyền truy cập file hoặc chọn một origin an toàn.

**relativize(target)** cố rút gọn một URI đích thành tham chiếu tương đối so với base. Java chỉ làm việc này khi điều kiện phù hợp, đặc biệt khi **cùng scheme và authority** và path của base là prefix phù hợp của path đích. Ví dụ:

~~~text
base:    https://example.org/docs/
target:  https://example.org/docs/api/start.html
result:  api/start.html
~~~

Nếu không đáp ứng điều kiện, **relativize(...)** có thể trả nguyên target. Nó **không** phải thuật toán tổng quát luôn tạo chuỗi **../...** ngắn nhất. Đặc biệt, nên chuẩn hóa có chủ đích rồi kiểm tra kết quả, không dùng relativize như một phép kiểm tra quyền truy cập hay cách bảo đảm hai URI trỏ đến cùng tài nguyên.

Phân biệt nhanh:

| Method | Đầu vào và vai trò | Ví dụ |
| --- | --- | --- |
| **isAbsolute()** | Kiểm tra có scheme | **https://x/a** → true |
| **isOpaque()** | Kiểm tra Java opaque classification | **mailto:a@b** → true |
| **resolve(ref)** | Kết hợp base và reference | **https://x/dir/** + **a** → **https://x/dir/a** |
| **normalize()** | Rút gọn dot-segments ở path phân cấp | **/a/./b/../c** → **/a/c** |
| **relativize(target)** | Rút phần prefix phù hợp so với base | **https://x/dir/** → **https://x/dir/a** thành **a** |

## 7. Chương trình Java 17+ minh họa đầy đủ

Tạo tệp **UriKindsDemo.java**:

~~~java
import java.net.URI;

public class UriKindsDemo {
    public static void main(String[] args) {
        URI absolute = URI.create("https://example.org/docs/guide.html?lang=vi#intro");
        URI relative = URI.create("../img/logo.svg");
        URI opaque = URI.create("mailto:hello@example.org?subject=Hi");
        URI base = URI.create("https://example.org/docs/guide/index.html?old=1");

        describe("HTTP", absolute);
        describe("Relative", relative);
        describe("Mail", opaque);

        System.out.println("Resolve file: " + base.resolve("../img/logo.svg"));
        System.out.println("Resolve root: " + base.resolve("/help"));
        System.out.println("Resolve authority: " + base.resolve("//cdn.example.org/app.js"));
        System.out.println("Resolve fragment: " + base.resolve("#intro"));
        System.out.println("Resolve query-only: " + base.resolve("?page=2"));
        System.out.println("Normalize: " +
                URI.create("https://example.org/a/./b/../c").normalize());
        System.out.println("Relativize: " +
                URI.create("https://example.org/docs/")
                        .relativize(URI.create("https://example.org/docs/api/start.html")));
    }

    private static void describe(String label, URI uri) {
        System.out.printf("%s: absolute=%s, opaque=%s, scheme=%s, path=%s, query=%s%n",
                label, uri.isAbsolute(), uri.isOpaque(), uri.getScheme(),
                uri.getPath(), uri.getQuery());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 UriKindsDemo.java
java UriKindsDemo
~~~

**Stdout dự kiến, đã đối chiếu bằng JShell trên JDK 24:**

~~~text
HTTP: absolute=true, opaque=false, scheme=https, path=/docs/guide.html, query=lang=vi
Relative: absolute=false, opaque=false, scheme=null, path=../img/logo.svg, query=null
Mail: absolute=true, opaque=true, scheme=mailto, path=null, query=null
Resolve file: https://example.org/docs/img/logo.svg
Resolve root: https://example.org/help
Resolve authority: https://cdn.example.org/app.js
Resolve fragment: https://example.org/docs/guide/index.html?old=1#intro
Resolve query-only: https://example.org/docs/guide/?page=2
Normalize: https://example.org/a/c
Relativize: api/start.html
~~~

**Giải thích điểm quan trọng của output:**

1. **HTTP** có scheme **https**, phần scheme-specific bắt đầu bằng **/** nên absolute/hierarchical; **getPath()** và **getQuery()** hoạt động bình thường.
2. **Relative** không có scheme, nhưng vẫn là hierarchical; path có **..** vẫn là dữ liệu path chưa resolve.
3. **Mail** là absolute/opaque; **getPath()** và **getQuery()** trả **null**, dù ký tự **?** có trong scheme-specific part của mailto.
4. **Resolve file/root/authority** thể hiện lần lượt thay một đoạn path theo base, lấy path từ root, và dùng authority mới với scheme cũ.
5. **Resolve query-only** cho thấy một sắc thái riêng của API Java cần chú ý khi làm việc với reference có query rỗng path.
6. **Normalize** chỉ xử lý dot-segments; **Relativize** rút prefix phù hợp và trả **api/start.html**.

Các giá trị trong demo chỉ được phân tích và ghép **trong bộ nhớ**, hoàn toàn không tạo socket, không gửi HTTP và không truy vấn DNS.

## 8. Tạo URI và percent-encoding đúng cách

**URI.create(String)** phù hợp với một chuỗi URI đã có cú pháp hợp lệ; nếu sai cú pháp sẽ ném **IllegalArgumentException** (nguyên nhân thường là **URISyntaxException**). Khi xử lý dữ liệu đầu vào cần kiểm soát lỗi cú pháp, có thể dùng **new URI(String)** và bắt **URISyntaxException**. Ví dụ **https://example.org/a b** chứa khoảng trắng thô nên không hợp lệ như chuỗi URI và cần encode.

Các phương thức constructor nhiều tham số của **URI** hỗ trợ escape ký tự trong từng thành phần. Ví dụ minh họa (đặt trong method có khai báo **throws URISyntaxException** hoặc xử lý exception):

~~~java
URI search = new URI("https", null, "example.org", -1,
        "/search", "q=a b", null);
System.out.println(search); // https://example.org/search?q=a%20b
~~~

Đoạn trên là **snippet**, chưa phải chương trình độc lập. Khi đã có chuỗi URI percent-encoded sẵn, không tự động encode lại toàn bộ vì dễ gây double encoding (ví dụ **%20** bị thành **%2520**). **URLEncoder** phục vụ định dạng **application/x-www-form-urlencoded** (thường cho form/query parameter), không phải API để encode nguyên một URL/URI gồm scheme, dấu slash, host, query và fragment.

Phân biệt các thao tác:

- **getRawPath() / getRawQuery()**: giữ percent escapes từ URI.
- **getPath() / getQuery()**: lấy thành phần sau khi decode theo cách API định nghĩa.
- **toString()**: biểu diễn URI dạng text; có thể giữ ký tự Unicode nguyên dạng tùy URI.
- **toASCIIString()**: biểu diễn bằng ký tự ASCII, percent-encode ký tự non-ASCII cần thiết.

Không dùng thao tác nối chuỗi thủ công để lắp ghép các thành phần không đáng tin cậy, ví dụ **"https://" + host + "/" + path**. Cấu trúc đúng cần xử lý riêng scheme, authority, path, query và fragment.

## 9. Dùng URI trong Java networking mà không mở sai đích

Một URI parse được **không có nghĩa URI đó được phép truy cập**. Trong ứng dụng nhận URI do người dùng cung cấp và sẽ dùng để gọi HTTP, chuyển hướng hoặc đọc tài nguyên, nên phân biệt ba tầng:

1. **Cú pháp**: Chuỗi hợp lệ với **new URI(...)** hay **URI.create(...)** chưa?
2. **Chính sách**: Scheme có được phép không (thường **https**), có đúng host/port cho phép không, có **userinfo** bất thường, authority hay opaque form đáng ngờ không?
3. **Truy cập thật**: DNS, địa chỉ IP đích, proxy, redirect, TLS, firewall và HTTP response có đúng kỳ vọng không?

Một mẫu kiểm tra đầu vào hợp lý khi yêu cầu HTTP URL tuyệt đối là: **isAbsolute() == true**, **isOpaque() == false**, scheme nằm trong allowlist được định nghĩa, **getHost() != null**, và áp dụng thêm chính sách host/port, credentials, redirect và network destination. Kiểm tra chỉ có **isAbsolute()** là sai: **mailto:x@y** hoặc **https:report** cũng absolute. Kiểm tra chỉ có **getAuthority()** cũng chưa bảo đảm đã parse được host server-based.

Với URI tham chiếu tương đối, **URI.resolve(...)** có thể trả URI ở **host khác** nếu reference là absolute hoặc bắt đầu bằng **//**. Ví dụ một base HTTPS nội bộ ghép với **//untrusted.example/path** sẽ thành HTTPS URI ở host untrusted. Vì vậy hãy **kiểm tra lại kết quả cuối cùng sau resolve**, và kiểm tra mọi redirect trước khi thực sự kết nối. Nếu có yêu cầu chặn SSRF, kiểm tra scheme/host chỉ là bước đầu; còn cần xử lý DNS/IP nội bộ, redirect và proxy theo threat model ứng dụng.

**Không sử dụng URI.normalize() làm bộ lọc path traversal.** Percent-encoding, filesystem path rules, normalization ở server/proxy và decoding ở các tầng khác nhau có thể tạo các cách biểu diễn tương đương hoặc nguy hiểm. Cần xác thực và giới hạn quyền truy cập trên đường dẫn đích thực tế, theo API của hệ thống lưu trữ/file hoặc routing framework đang dùng.

## 10. Lỗi phổ biến và cách tự kiểm tra

| Nhầm lẫn | Thực tế trong Java |
| --- | --- |
| **/api** là URI tuyệt đối | Sai: path absolute, nhưng thiếu scheme nên **isAbsolute() == false** |
| **//host/path** có scheme | Sai: authority có thể có, scheme chưa có |
| Mọi URI có scheme đều hierarchical | Sai: **mailto:...**, **urn:...**, **https:report** đều opaque theo **java.net.URI** |
| **getQuery()** luôn thấy đoạn sau dấu **?** | Sai với opaque URI: phần đó thuộc scheme-specific part |
| **URI.resolve()** lúc nào cũng thêm reference sau base | Sai: có thể thay path, thay authority, trả nguyên absolute reference hoặc có hành vi riêng với query-only |
| **normalize()** kiểm tra URI có tồn tại hoặc an toàn | Sai: chỉ biến đổi cú pháp path phân cấp; không phải network/security validation |
| **relativize()** luôn tạo được **../...** | Sai: nếu path/prefix, scheme hoặc authority không phù hợp, có thể trả nguyên target |
| **URI.create(...)** mở kết nối | Sai: chỉ parse trong bộ nhớ |
| **URL** và **URI** luôn chuyển qua lại được | Sai: không phải scheme URI nào cũng có URL handler thích hợp |
| Percent-encode cả URI bằng **URLEncoder** | Sai: có thể biến dấu phân cách của scheme/path thành dữ liệu |

**Bài tập ngắn tự kiểm tra:**

1. Java phân loại **/docs/v1**, **https://example.org/docs**, **mailto:x@y** và **https:notes** ra sao theo hai trục **isAbsolute/isOpaque**?
2. Base **https://example.org/a/b/index.html** resolve **../img.png**, **/support**, **//cdn.example.org/js/app.js** thành URI nào?
3. Nếu muốn nhận một URL HTTPS cho HTTP client, tại sao chỉ kiểm tra **isAbsolute()** là chưa đủ?
4. Vì sao **mailto:x@y?subject=Hello** có dấu **?** mà **getQuery()** vẫn trả **null**?
5. Khi URI dùng để chuyển hướng tới host chỉ định, tại sao phải kiểm tra kết quả **sau** khi resolve?

**Ghi nhớ:**  
- **Absolute/relative** trả lời “**có scheme không?**”.  
- **Hierarchical/opaque** trả lời “**Java có parse được cấu trúc authority/path/query generic không?**”.  
- **resolve** kết hợp tham chiếu với base; **normalize** xử lý dot-segments; **relativize** rút gọn một path-prefix phù hợp.  
- **URI là cú pháp/định danh**; kiểm tra an toàn và thực thi network I/O là trách nhiệm riêng.

**Tài liệu chuẩn để đối chiếu:** [java.net.URI (Java SE 21 Javadoc)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html) và [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986). Khi hai nguồn khác nhau về một chi tiết resolution, hãy ưu tiên kiểm tra behavior của **java.net.URI** nếu code đang sử dụng chính API này.