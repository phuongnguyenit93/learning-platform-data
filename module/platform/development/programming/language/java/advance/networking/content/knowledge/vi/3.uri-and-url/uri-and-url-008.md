# IDN và chuyển tên miền quốc tế sang biểu diễn ASCII trong Java

Một URL như `https://bücher.example/sách` có **hostname chứa ký tự Unicode** (`ü`) và đường dẫn tiếng Việt. Con người muốn đọc tên miền tự nhiên, nhưng nhiều giao diện DNS, URI và thư viện mạng yêu cầu hostname ở dạng ASCII. **IDN (Internationalized Domain Name)** đáp ứng nhu cầu đó qua **ASCII-Compatible Encoding (ACE)**. Java có lớp `java.net.IDN` để chuyển đổi tên miền Unicode ↔ ACE.

Bài học này nằm trong chủ đề **URI và URL**, tập trung vào cách chuyển **riêng phần hostname** sang ASCII, phân biệt với percent-encoding của URI, và hiểu giới hạn của API khi xác thực/bảo mật tên miền. Các ví dụ dùng miền `.example` dành cho tài liệu; không cần mạng hoặc DNS để chạy.

Sau bài này, bạn có thể:
- Giải thích IDN, **U-label, A-label, ACE, Punycode** và vì sao DNS cần biểu diễn ASCII.
- Dùng `IDN.toASCII()`, `IDN.toUnicode()` và flags trên Java 17+.
- Kết hợp IDN với `java.net.URI` mà vẫn giữ đúng scheme, port, path, query, fragment.
- Nhận diện khác biệt giữa IDNA2003 của Java và IDNA2008/UTS #46, cũng như nguy cơ homograph.

## 1. Từ hostname Unicode đến A-label

Tên miền gồm nhiều **label** phân tách bằng dấu chấm. Ví dụ `shop.bücher.example` gồm các label `shop`, `bücher`, `example`. Thay vì bắt người dùng gõ tên miền bằng ASCII, IDNA quy định biểu diễn tương thích cho các nhãn quốc tế hóa.

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| IDN | Tên miền quốc tế hóa với một hoặc nhiều nhãn quốc tế hóa | `bücher.example` |
| U-label | Nhãn Unicode hợp lệ theo thuật ngữ IDNA2008 | `bücher` |
| A-label | Biểu diễn ASCII hợp lệ của U-label, bắt đầu bằng `xn--` | `xn--bcher-kva` |
| ACE | Phương thức biểu diễn nhãn quốc tế hóa bằng các ký tự ASCII | `xn--bcher-kva` |
| Punycode | Thuật toán mã hóa dùng để tạo thành phần sau tiền tố ACE | `bcher-kva` |
| LDH label | Nhãn hostname ASCII dùng letter, digit và hyphen | `shop`, `example` |

Quy trình:

~~~text
Unicode hostname:   bücher.example
                        |
                        | IDN.toASCII(...)
                        v
ASCII hostname:     xn--bcher-kva.example
                        |
                        | IDN.toUnicode(...)
                        v
Unicode để hiển thị: bücher.example
~~~

Cần phân biệt:

1. **Punycode mã hóa từng label**, không mã hóa toàn bộ URL; phần `example` thuần ASCII được giữ lại.
2. Không phải mọi chuỗi bắt đầu `xn--` đều là A-label hợp lệ: còn cần giải mã được, tương ứng U-label hợp lệ theo tiêu chuẩn được chọn và tuân thủ quy tắc nhãn.
3. `IDN.toASCII` chỉ thực hiện **chuyển đổi chuỗi tại chỗ**. Nó không hỏi DNS, không chứng minh tên tồn tại, có bản ghi A/AAAA hoặc máy chủ đang mở cổng.
4. `IDN` xử lý tên miền; nó không biết phần `https://`, dấu `:443` hay đường dẫn `/books`.

Ví dụ `bücher` chuyển thành `xn--bcher-kva`. Không nên tự bỏ dấu `ü` hoặc tự thay bằng `u`, vì tên miền thu được có thể **khác** tên mà người dùng định truy cập.

## 2. IDN khác gì percent-encoding và URL-encoding?

Có ba nhóm thao tác khác nhau, cùng liên quan đến ký tự phi ASCII nhưng phục vụ mục đích khác nhau:

| Cần xử lý | Cơ chế | Ví dụ |
| --- | --- | --- |
| Unicode trong **hostname** dùng cho DNS/URI authority | IDNA/ACE qua `IDN.toASCII` | `bücher.example` → `xn--bcher-kva.example` |
| Unicode/khoảng trắng trong **path hoặc query URI** | Percent-encoding (thường với UTF-8) | `/cẩm nang` → `/c%E1%BA%A9m%20nang` |
| Giá trị của form có dạng `application/x-www-form-urlencoded` | `URLEncoder` | Khoảng trắng trong dữ liệu form có thể thành `+` |

Không làm điều này:

~~~java
// SAI mục đích: URLEncoder không tạo A-label cho DNS hostname.
String host = java.net.URLEncoder.encode(
        "bücher.example", java.nio.charset.StandardCharsets.UTF_8);
~~~

Đây là snippet minh họa một cách dùng sai, không phải giải pháp. `URLEncoder` dùng quy tắc encoding của form, còn `IDN.toASCII` dùng IDNA/Punycode. Đồng thời **không** gọi `IDN.toASCII` cho `/cẩm nang` hoặc chuỗi query.

Hình dung toàn bộ địa chỉ:

~~~text
https://bücher.example:8443/cẩm nang?lang=vi#intro
|---|   |------------|     |-------| |-----| |---|
scheme       host      port    path      query fragment

             Vùng cần IDN.toASCII
             |------------|
https://xn--bcher-kva.example:8443/c%E1%BA%A9m%20nang?lang=vi#intro
~~~

Host là một component riêng; port là con số, path/query có quy tắc quote riêng. Trộn mọi thứ vào một phép chuyển đổi gây sai cấu trúc URI.

## 3. Lớp `java.net.IDN` và các cờ xử lý

`java.net.IDN` là utility class có các phương thức tĩnh; API được cung cấp từ Java 6 và dùng được trên Java 17+.

| API | Công dụng | Hành vi đáng chú ý |
| --- | --- | --- |
| `IDN.toASCII(String)` | Unicode hoặc hostname đã ASCII → ACE | Tương đương `toASCII(input, 0)` |
| `IDN.toASCII(String, int flags)` | Chuyển đổi với tùy chọn | Khi không phù hợp quy tắc, ném `IllegalArgumentException` |
| `IDN.toUnicode(String)` | ACE → Unicode để hiển thị | Chuyển không được thì để nguyên dữ liệu tương ứng |
| `IDN.toUnicode(String, int flags)` | Giải mã với cờ | Không phải công cụ chứng nhận domain hợp lệ |
| `IDN.USE_STD3_ASCII_RULES` | Kiểm tra chặt hơn quy tắc hostname ASCII | Ví dụ `bad_name.example` bị từ chối |
| `IDN.ALLOW_UNASSIGNED` | Cho phép các Unicode code point chưa được gán theo Unicode 3.2 của cơ chế này | Không bật mặc định cho dữ liệu người dùng không tin cậy |

Snippet sử dụng trong phương thức (cần `import java.net.IDN;`):

~~~java
String asciiHost = IDN.toASCII(
        unicodeHost, IDN.USE_STD3_ASCII_RULES);
String displayHost = IDN.toUnicode(asciiHost);
~~~

**Lỗi và kiểm tra:** `toASCII` có thể ném `IllegalArgumentException` nếu nhãn không hợp lệ theo RFC 3490 và cờ hiện hành. Bắt ngoại lệ để báo lỗi cho người dùng; không bắt rồi lặng lẽ dùng lại chuỗi chưa chuyển đổi. `toUnicode` theo Java API không thất bại bằng cách ném lỗi chuyển đổi: khi không thể đổi, nội dung có thể được trả nguyên, vì vậy không thể xem việc gọi thành công là bằng chứng tên miền hợp lệ.

**Dấu chấm và nhãn:** Java nhận diện cả `.` (U+002E), `。` (U+3002), `．` (U+FF0E) và `｡` (U+FF61) làm dấu phân tách nhãn; đầu ra `toASCII` dùng dấu chấm ASCII thông thường. `example.com.` có dấu chấm gốc ở cuối và có thể được giữ như vậy; không tự bỏ nếu ứng dụng cần giữ ý nghĩa tên tuyệt đối. Nhãn rỗng ở giữa, ví dụ `a..example`, không phải hostname bình thường hợp lệ.

**STD-3:** Với `USE_STD3_ASCII_RULES`, Java áp dụng quy tắc ASCII hostname chặt hơn, chẳng hạn chống dấu gạch dưới `_` hoặc dấu gạch nối ở đầu/cuối label. Đây là cờ rất hữu ích nhưng **không thay thế** validation domain theo chính sách sản phẩm, registry, hoặc chống giả mạo tên miền.

## 4. Chương trình hoàn chỉnh: `toASCII` và `toUnicode`

Tạo file **`IdnBasics.java`**, mã hóa UTF-8:

~~~java
import java.net.IDN;

public class IdnBasics {
    public static void main(String[] args) {
        String unicodeHost = "bücher.example";
        String asciiHost =
                IDN.toASCII(unicodeHost, IDN.USE_STD3_ASCII_RULES);

        System.out.println("Unicode: " + unicodeHost);
        System.out.println("ASCII: " + asciiHost);
        System.out.println("Display: " + IDN.toUnicode(asciiHost));
        System.out.println("Mapped: " + IDN.toASCII("faß.example"));

        try {
            IDN.toASCII("bad_name.example", IDN.USE_STD3_ASCII_RULES);
            System.out.println("Accepted bad_name");
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected bad_name");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 IdnBasics.java
java IdnBasics
~~~

Kết quả trên terminal hỗ trợ Unicode:

~~~text
Unicode: bücher.example
ASCII: xn--bcher-kva.example
Display: bücher.example
Mapped: fass.example
Rejected bad_name
~~~

Giải thích:

- Chuỗi `bücher.example` được đổi thành `xn--bcher-kva.example` theo từng nhãn, không truy cập DNS.
- `toUnicode` giải mã A-label thành chuỗi dễ đọc, dùng cho giao diện người dùng khi phù hợp chính sách hiển thị.
- Java xử lý `faß` thành `fass` do **mapping IDNA2003**. Vì vậy không thể khẳng định `toUnicode(toASCII(s)).equals(s)` cho mọi Unicode input.
- `bad_name.example` vi phạm quy tắc ASCII hostname khi bật STD-3; chương trình bắt lỗi và in thông báo ổn định, không phụ thuộc nội dung chuỗi lỗi JDK.

`.example` là tên dành cho tài liệu, không yêu cầu trang web tồn tại. Chương trình trên là ví dụ parsing thuần Java, với stdout xác định.

## 5. Kết hợp IDN với `java.net.URI` và `java.net.URL`

Với URL có hostname quốc tế hóa, hãy xử lý theo đúng ranh giới component:

1. Nhận/kiểm tra **hostname** riêng, ví dụ `bücher.example`. Khi bắt đầu từ URL đầy đủ, cần parser phù hợp cú pháp URI/IRI để lấy các component mà không nhầm `userinfo@`, IPv6 literal, port hoặc dấu phân cách.
2. Chuyển hostname bằng `IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)`.
3. Áp dụng validation và policy cho host kết quả; giữ đúng scheme, port, path, query, fragment.
4. Tạo `URI` bằng constructor nhận các component như `new URI(scheme, userInfo, host, port, path, query, fragment)`. Constructor này quote ký tự cần thiết ở path/query.
5. Khi cần biểu diễn ASCII, dùng `uri.toASCIIString()`; HTTP client có thể tiếp nhận URI đã được xây dựng và thực hiện DNS/TLS theo cấu hình.

**Cạm bẫy quan trọng:** `URI.toASCIIString()` **không chuyển hostname Unicode thành Punycode**. Nó percent-encode ký tự non-ASCII trong biểu diễn URI. Trên Java, `URI.create("https://bücher.example/").getHost()` có thể trả về `null` vì parser không nhận authority Unicode đó thành server-host hợp lệ; `getRawAuthority()` vẫn có thể giữ authority thô. Vì thế không dùng `URI.create` với Unicode authority rồi mặc định Java đã chuẩn hóa DNS IDN.

Không gọi:

~~~java
// SAI: truyền nguyên URI cho API chỉ nhận hostname.
String wrong = java.net.IDN.toASCII(
        "https://bücher.example:8443/cẩm nang");
~~~

Và không tách hostname bằng `split(":")` hay string replacement thủ công. Điều này đặc biệt dễ sai với IPv6 literal `[2001:db8::1]`, userinfo chứa `@`, port, query và fragment. `IDN` xử lý **tên miền**, không xử lý literal IPv4/IPv6.

Lớp `URL` cũng có `getHost()` nhưng không nên coi việc một URL string được parse là bằng chứng hostname đã chuyển đổi, được phân giải hoặc được chứng nhận an toàn. Trong code mới, thường nên xây dựng `URI` từ các component hợp lệ rồi chuyển cho HTTP client.

## 6. Chương trình hoàn chỉnh: hostname IDN và path Unicode trong URI

Tạo file **`IdnUriDemo.java`** bằng UTF-8:

~~~java
import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;

public class IdnUriDemo {
    public static void main(String[] args) throws URISyntaxException {
        String unicodeHost = "bücher.example";
        String asciiHost =
                IDN.toASCII(unicodeHost, IDN.USE_STD3_ASCII_RULES);

        URI uri = new URI(
                "https",        // scheme
                null,           // userInfo
                asciiHost,      // host: đã chuyển sang ACE
                8443,           // port
                "/cẩm nang",    // path Unicode
                "lang=vi",      // query
                null            // fragment
        );

        System.out.println("Host: " + uri.getHost());
        System.out.println("Port: " + uri.getPort());
        System.out.println("Path: " + uri.getPath());
        System.out.println("ASCII URI: " + uri.toASCIIString());

        URI raw = URI.create("https://" + unicodeHost + "/");
        System.out.println("Raw host recognized: " + (raw.getHost() != null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IdnUriDemo.java
java IdnUriDemo
~~~

Kết quả:

~~~text
Host: xn--bcher-kva.example
Port: 8443
Path: /cẩm nang
ASCII URI: https://xn--bcher-kva.example:8443/c%E1%BA%A9m%20nang?lang=vi
Raw host recognized: false
~~~

Hai kiểu chuyển đổi thể hiện rõ:
- `getHost()` có giá trị A-label `xn--bcher-kva.example` và `getPort()` là `8443`.
- `getPath()` trả lại Unicode path. Trong `toASCIIString()`, chữ `ẩ` và khoảng trắng ở path được percent-encode bằng UTF-8; hostname vẫn là A-label.
- Dòng cuối minh họa `URI` parse Unicode authority nhưng không nhận đó thành server-host. Cần chuyển riêng host trước khi dựng `URI`.
- `throws URISyntaxException` chỉ giúp ví dụ ngắn. Code sản phẩm nên bắt/biến đổi lỗi thành kết quả validation rõ ràng; đồng thời nhớ rằng tạo `URI` **không tạo kết nối mạng**.

Khi gửi URI này cho một HTTP client, tên miền dùng để định tuyến vẫn phải trải qua DNS; việc tạo đối tượng thành công chưa đảm bảo DNS, TLS hay HTTP thành công.

## 7. Validate và canonical hóa ở đúng tầng

`IDN.toASCII` là bước chuyển đổi và một số kiểm tra cú pháp, **không** kiểm tra toàn bộ chính sách địa chỉ web.

### Kiểm tra cấu trúc DNS sau khi chuyển sang ACE

- Một DNS label tối đa **63 octet**; một tên DNS trên wire tối đa **255 octet** kể cả octet độ dài của các nhãn và root. Với tên dạng văn bản không có dấu chấm root kết thúc, giới hạn thường áp dụng là **253 ký tự ASCII**.
- **Kiểm tra độ dài sau `toASCII`**. Một chuỗi Unicode trông ngắn có thể nở ra thành A-label dài hơn.
- Với hostname thông thường, các nhãn ASCII theo quy tắc LDH (letter, digit, hyphen) và không để hyphen ở hai đầu. `USE_STD3_ASCII_RULES` hỗ trợ kiểm tra nhiều ràng buộc này.
- DNS nói chung cho phép các loại tên ngoài hostname HTTP. Ví dụ nhãn service trong record chuyên biệt có thể chứa `_`; đừng vô tình áp validator hostname web cho mọi loại DNS name.
- Phân biệt miền có dấu chấm cuối như `example.com.` với `example.com` theo chính sách riêng; không tự động xóa dấu chấm root.

### Canonical hóa để so sánh và lưu trữ

Host ASCII trong DNS so sánh **không phân biệt chữ hoa/thường**. Với một chính sách ứng dụng nhất quán, có thể lưu A-label bằng chữ thường theo `Locale.ROOT` (và thống nhất quy tắc dấu chấm root). Ví dụ snippet:

~~~java
import java.net.IDN;
import java.util.Locale;

String canonicalHost = IDN.toASCII(
        "BÜCHER.example", IDN.USE_STD3_ASCII_RULES
).toLowerCase(Locale.ROOT);
~~~

Đoạn này **không độc lập**; đặt vào class/method khi sử dụng. `Locale.ROOT` dành cho canonical case conversion không phụ thuộc locale thiết bị. Đừng tự “xóa dấu” hoặc dùng `String.toLowerCase()` thay cho thuật toán IDNA.

Nếu cần hiển thị lại chính xác tên người dùng đã nhập, hãy lưu riêng giá trị gốc; **không giả định** `IDN.toUnicode(IDN.toASCII(input))` khôi phục nguyên bản. A-label thích hợp làm khóa canonical theo policy đã chọn, còn chuỗi Unicode ban đầu có thể cần cho UX, audit hoặc troubleshooting.

### Một hostname chuyển thành công vẫn chưa được tin cậy

- `toASCII` không chứng minh TLD cho phép đăng ký nhãn, domain tồn tại hay DNS trả record hợp lệ.
- Không chứng minh certificate TLS đáng tin, site thuộc đúng thương hiệu, hoặc kết nối sẽ thành công.
- Nếu server tự mở URL do người dùng cung cấp, phải kiểm tra scheme/port, redirect, DNS resolution và IP đích theo policy bảo vệ SSRF. IDN canonicalization **không** thay các lớp kiểm tra đó.

## 8. IDNA2003 của Java so với IDNA2008 và UTS #46

Đây là điểm kỹ thuật rất dễ gây lỗi khi hai thư viện hoặc trình duyệt cho ra kết quả khác nhau.

**`java.net.IDN` của Java SE 17/21 được tài liệu hóa theo RFC 3490 (IDNA2003)**, với Nameprep/Punycode và các quy tắc gắn với Unicode 3.2. Hệ sinh thái web còn sử dụng **IDNA2008** (RFC 5890–5895) và **UTS #46** để xử lý mapping/compatibility theo chính sách và phiên bản Unicode khác.

Ví dụ về `ß`:

~~~text
Unicode input:  faß.example

Java IDN / IDNA2003:
    IDN.toASCII(...)   -> fass.example
    IDN.toUnicode(...) -> fass.example

Một luồng IDNA2008 phù hợp có thể giữ chữ ß,
và mã hóa label "faß" thành A-label riêng thay vì "fass".
~~~

Vì có mapping ở bước đầu, round-trip không bảo toàn toàn bộ ký tự gốc:

~~~text
"faß.example" --> toASCII --> "fass.example"
                                 |
                                 v
                               toUnicode
                                 |
                                 v
                            "fass.example"
~~~

Không nên kết luận hai thư viện “sai” khi kết quả khác nhau mà chưa xác định **chuẩn IDNA, Unicode version và mapping mode** của mỗi bên. Nếu cần tương thích tuyệt đối với trình duyệt/registry dùng IDNA2008 hoặc UTS #46, chọn thư viện và quy trình phù hợp, đồng thời kiểm thử các Unicode case cụ thể. `USE_STD3_ASCII_RULES` không thay IDNA2003 thành IDNA2008; `ALLOW_UNASSIGNED` chỉ thay chế độ xử lý code point chưa gán theo cơ chế Java, không phải nút bật “Unicode mới nhất”.

### U-label/A-label và thuật ngữ phiên bản

Trong RFC 5890, **A-label** phải là nhãn ACE **hợp lệ**, không chỉ một chuỗi có tiền tố `xn--`; **U-label** phải hợp lệ theo các quy tắc IDNA2008 liên quan (kể cả normalization/Unicode). Java `IDN` dùng thuật ngữ và thuật toán từ RFC 3490; khi giảng giải hoặc thiết kế API, cần ghi rõ đang dùng chuẩn nào.

## 9. Bảo mật: homograph, confusable, spoofing

Tên miền quốc tế hóa có thể chứa các ký tự **trông giống nhau nhưng khác code point**. Ví dụ ký tự Latin `a` (U+0061) và Cyrillic `а` (U+0430) là hai ký tự khác nhau dù có thể gần như giống nhau trong một số font. Kẻ tấn công có thể lợi dụng sự giống nhau để tạo hostname đánh lừa người dùng.

Những việc `IDN.toASCII` và `IDN.toUnicode` **không làm**:

- Không phát hiện toàn bộ ký tự confusable, mixed scripts hay sự giống nhau với tên tổ chức.
- Không chứng minh hostname thuộc thương hiệu hoặc chứng chỉ HTTPS hợp lệ.
- Không xác nhận chuỗi A-label/Unicode an toàn để hiển thị ở mọi trình duyệt/giao diện.
- Không chặn việc host phân giải thành IP private/loopback khi URL được máy chủ truy cập.
- Không ngăn DNS rebinding hay các redirect nguy hiểm.

Tùy sản phẩm, có thể áp chính sách ký tự/script được phép, kiểm tra confusable theo Unicode UTS #39, hiển thị A-label trong trường hợp đáng ngờ, log cả A-label canonical và tên gốc, đồng thời để TLS/HTTP stack làm xác thực hostname và chứng chỉ. Đối với input dùng để tải URL phía server, cần kiểm soát DNS/IP/redirect độc lập với IDN. Khi log hoặc so sánh hostname, không chỉ so sánh chuỗi Unicode hiển thị vì các ký tự khác nhau có thể rất giống về thị giác.

## 10. Lỗi phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `IDN.toASCII("https://bücher.example/a")` | Truyền cả URI vào API cho hostname | Tách hostname rồi chuyển riêng |
| `URLEncoder.encode(host, UTF_8)` | Đây là form encoding, không phải A-label | Dùng `IDN.toASCII` |
| `URI.toASCIIString()` để làm Punycode | Chỉ percent-encode Unicode trong URI, không chuẩn hóa IDNA host | Chuyển host trước khi xây `URI` |
| Xóa dấu hoặc dịch tên miền sang Latin bằng thuật toán tự viết | Có thể đổi thành tên miền khác | Sử dụng IDNA mapping đúng tiêu chuẩn |
| Mọi nhãn `xn--...` đều được xem là hợp lệ | Có “fake A-label” và các điều kiện IDNA khác | Dùng validation đúng chuẩn và policy |
| `toUnicode(toASCII(s))` phải trả `s` | Mapping có thể thay `ß` bằng `ss` | Lưu input gốc nếu cần tái hiện |
| Xem `toASCII` thành công là host đáng tin | Không kiểm tra DNS, HTTPS, spoofing, policy | Kiểm tra ở tầng network/security |
| Tách host bằng `split(":")` | Nhầm IPv6, port, userinfo | Dùng parser các component đúng ngữ pháp |
| So sánh hostname Unicode raw có phân biệt hoa/thường | Bỏ qua ACE/canonicalization và rule IDNA | Cùng policy IDNA, so sánh trên A-label |
| Không kiểm tra độ dài sau encoding | A-label có thể dài hơn Unicode nhìn thấy | Kiểm tra giới hạn DNS sau khi chuyển |

## 11. Bài tập và đáp án

**1.** `bücher.example` cần chuyển sang hostname ASCII nào? Có phải chuyển cả `https://` và `/path` không?

**Đáp án:** `xn--bcher-kva.example`. Chỉ hostname được chuyển theo IDNA; scheme và path dùng quy tắc riêng.

**2.** Vì sao `toUnicode(toASCII("faß.example"))` trên Java không còn `ß`?

**Đáp án:** Mapping IDNA2003 chuyển `ß` thành `ss`, tạo `fass.example`; chuyển ngược không biết rằng trước đây người dùng gõ `ß`.

**3.** `URI.create("https://bücher.example/").getHost()` có thể ra gì và phải làm sao?

**Đáp án:** Có thể là `null` vì authority Unicode không được parser nhận làm server-host. Chuyển tên miền thành A-label rồi dựng URI từ các component.

**4.** `IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)` chạy thành công đã chứng minh domain an toàn chưa?

**Đáp án:** Chưa. API kiểm tra/chuyển đổi chuỗi, không xác minh DNS, IP, TLS, sự giả mạo hoặc chính sách đăng ký.

**5.** Punycode nên áp dụng cho path `/cẩm nang` hay label `bücher`?

**Đáp án:** Cho label tên miền `bücher`. Với URI ASCII, path sẽ được percent-encode phù hợp (UTF-8), không dùng Punycode.

**6.** DNS label tối đa bao nhiêu octet và đo khi nào?

**Đáp án:** 63 octet; đo **sau** khi chuyển sang ACE, khi đã biết độ dài nhãn ASCII thực dùng với DNS.

**7.** Chỉ cần gọi `toUnicode` là có thể hiển thị mọi nhãn Unicode an toàn không?

**Đáp án:** Không; IDN có nguy cơ homograph/confusable, cần chính sách hiển thị và kiểm tra phù hợp ngữ cảnh.

## Tài liệu tham khảo

- [Java SE 21: java.net.IDN](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/IDN.html) — API, flags, ToASCII/ToUnicode, chuẩn RFC 3490 và các giới hạn của phép chuyển đổi.
- [Java SE 21: java.net.URI](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html) — constructors, phân tích host và percent-encoding.
- [RFC 3490](https://www.rfc-editor.org/rfc/rfc3490), [RFC 3492](https://www.rfc-editor.org/rfc/rfc3492) — IDNA2003 và thuật toán Punycode.
- [RFC 5890](https://www.rfc-editor.org/rfc/rfc5890), [RFC 5891](https://www.rfc-editor.org/rfc/rfc5891) — thuật ngữ U-label/A-label và IDNA2008.
- [Unicode UTS #46](https://www.unicode.org/reports/tr46/) và [UTS #39](https://www.unicode.org/reports/tr39/) — mapping IDNA tương thích và kiểm tra ký tự confusable.
