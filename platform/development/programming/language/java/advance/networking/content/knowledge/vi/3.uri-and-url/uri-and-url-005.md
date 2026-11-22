# `resolve`, `relativize` và `normalize` khi ghép đường dẫn tài nguyên bằng Java URI

Trong ứng dụng Java, đường dẫn của một tài nguyên thường không cố định: tài liệu HTML liên kết tới ảnh, CSS hoặc một tài liệu khác; REST client xây URL từ endpoint gốc; trình tạo site xây liên kết tương đối giữa các trang. Ghép chuỗi kiểu `base + "/" + child` dễ sai khi base đã có hoặc chưa có dấu `/`, khi tham chiếu chứa `../`, hoặc khi đường dẫn bắt đầu bằng `/`, `?`, `#` hay `//`.

`java.net.URI` cung cấp ba phép toán cú pháp quan trọng:

- **`resolve`:** biến URI tham chiếu thành URI kết quả dựa trên một URI gốc.
- **`relativize`:** tìm URI tương đối với một URI gốc nếu hai URI có cấu trúc tương thích.
- **`normalize`:** chuẩn hóa các đoạn `.` và `..` trong *path* của URI phân cấp.

Ba phép toán này **không truy cập mạng, không kiểm tra tài nguyên tồn tại và không tự đảm bảo an toàn khi đầu vào không đáng tin**. Muốn dùng đúng, phải hiểu cấu trúc URI, cách chọn URI gốc và những giới hạn của từng phép toán.

## 1. URI là cấu trúc, không chỉ là một chuỗi có dấu `/`

Một URI phân cấp thường có dạng:

~~~text
scheme://authority/path/to/resource?query#fragment
https://docs.example.test/guide/page.html?lang=vi#examples
│       │                 │              │       │
scheme  authority         path           query   fragment
~~~

Trong Java:

~~~java
URI uri = URI.create("https://docs.example.test/guide/page.html?lang=vi#examples");
System.out.println(uri.getScheme());   // https
System.out.println(uri.getAuthority()); // docs.example.test
System.out.println(uri.getPath());     // /guide/page.html
System.out.println(uri.getQuery());    // lang=vi
System.out.println(uri.getFragment()); // examples
~~~

Đây là **đoạn minh họa** đặt trong phương thức Java có `import java.net.URI;`, không phải chương trình độc lập. `scheme` như `https`, `file`; `authority` có thể gồm userinfo, host, port; `path` dùng dấu `/` phân tách các segment; `query` và `fragment` là các thành phần riêng. Vì vậy không thể xử lý đúng URI bằng thao tác xóa chuỗi bất kỳ có chứa `?` hoặc `#`.

Ba kiểu tham chiếu cần nhận biết:

| Tham chiếu | Ví dụ | Ý nghĩa khi dùng với một HTTP URI gốc |
| --- | --- | --- |
| URI tuyệt đối có scheme | `https://cdn.example.test/a.svg` | Đã có đích riêng, `resolve` giữ nguyên |
| URI tương đối có path | `img/logo.svg`, `../style.css` | Ghép với thư mục của đường dẫn gốc rồi chuẩn hóa |
| Tham chiếu bắt đầu từ root | `/assets/a.svg` | Giữ scheme/authority gốc, thay path từ root |
| Tham chiếu đổi authority | `//cdn.example.test/a.svg` | Thừa hưởng scheme của gốc nhưng thay authority |
| Fragment-only | `#section2` | Giữ đường dẫn và các thành phần khác của gốc, thay fragment theo hợp đồng Java |
| Query-only | `?lang=vi` | Cần kiểm tra hành vi `URI.resolve` cụ thể; Java có trường hợp kết quả khác trực giác browser |

**URI tuyệt đối** được xác định bằng việc có *scheme* (`isAbsolute()`), không phải bằng việc path có ký tự `/` đầu tiên. `mailto:help@example.test` cũng là URI tuyệt đối nhưng là **opaque URI**, khác URI phân cấp; không áp dụng máy móc phép ghép path cho nó. Với `URI.create("mailto:help@example.test")`, `isOpaque()` là `true`.

`URI` là immutable: mọi phép toán trả một đối tượng `URI`; gọi `uri.normalize();` mà bỏ giá trị trả về sẽ không biến đổi biến `uri`.

## 2. `resolve`: ghép tham chiếu vào URI gốc

Cú pháp:

~~~java
URI result = base.resolve(referenceUri);
URI result2 = base.resolve("images/icon.svg");
~~~

Overload nhận `String` phân tích chuỗi thành `URI` bằng `URI.create(...)` rồi áp dụng `resolve`. Chuỗi sai cú pháp làm phát sinh `IllegalArgumentException`. Với URI tham chiếu đã tuyệt đối, kết quả giữ URI đó. Nếu base là opaque URI, `resolve` cũng trả lại URI tham chiếu theo đặc tả.

### 2.1. Dấu `/` ở cuối base là quyết định quan trọng

Xét ba base:

~~~text
https://docs.example.test/guide/
https://docs.example.test/guide
https://docs.example.test/guide/start.html
~~~

Khi gọi `resolve("img/logo.svg")`:

| Base | Kết quả |
| --- | --- |
| `https://docs.example.test/guide/` | `https://docs.example.test/guide/img/logo.svg` |
| `https://docs.example.test/guide` | `https://docs.example.test/img/logo.svg` |
| `https://docs.example.test/guide/start.html` | `https://docs.example.test/guide/img/logo.svg` |

Giải thích: thuật toán thay **segment cuối** của path gốc khi nối path tương đối. Dấu `/` kết thúc path mang ý nghĩa vị trí tiếp theo nằm trong thư mục `guide/`; còn `/guide` không có slash cuối được xử lý như một segment tài nguyên và bị thay bằng `img/logo.svg`. Path kết thúc bằng `start.html` cũng bị thay segment `start.html`.

Đây là điểm rất dễ gây lỗi trong chương trình nhận `baseUrl` từ file cấu hình. Nếu cấu hình là *thư mục tài nguyên*, hãy chuẩn hóa **ý nghĩa** cấu hình thành base kết thúc bằng `/`, chẳng hạn `https://docs.example.test/guide/`. Không thêm slash mù quáng vào URL của một tài liệu vốn là `.../index.html`, vì điều đó sẽ biến nó thành một đường dẫn khác.

### 2.2. Các loại reference không phải đều ghép thêm vào cuối

Lấy `base = https://docs.example.test/guide/`:

| Reference | Kết quả của `base.resolve(reference)` | Lý do |
| --- | --- | --- |
| `img/logo.svg` | `https://docs.example.test/guide/img/logo.svg` | Path tương đối |
| `../shared/style.css` | `https://docs.example.test/shared/style.css` | `..` quay lên một cấp rồi chuẩn hóa |
| `/public/logo.svg` | `https://docs.example.test/public/logo.svg` | Path tuyệt đối trong cùng origin |
| `//cdn.example.test/x.svg` | `https://cdn.example.test/x.svg` | Authority mới, thừa hưởng scheme `https` |
| `https://other.example.test/x.svg` | `https://other.example.test/x.svg` | Reference đã tuyệt đối |
| `#toc` | `https://docs.example.test/guide/#toc` | Fragment-only, giữ path gốc |

Không viết `URI.create("/public/logo.svg")` rồi cho rằng nó là URI tuyệt đối: nó **không có scheme**. `/public/logo.svg` chỉ có *path tuyệt đối*, vì vậy khi `resolve` nó vẫn lấy scheme/authority từ base.

### 2.3. Trường hợp query-only và chuỗi rỗng trong Java

Với `baseFile = https://docs.example.test/guide/start.html`:

~~~text
baseFile.resolve("#section2")
  => https://docs.example.test/guide/start.html#section2

baseFile.resolve("?lang=vi")
  => https://docs.example.test/guide/?lang=vi

baseFile.resolve("")
  => https://docs.example.test/guide/
~~~

Hai trường hợp cuối gây bất ngờ nếu người đọc nghĩ rằng chúng nhất thiết tham chiếu đúng `start.html`. Javadoc Java 17 mô tả quy tắc nối path tương đối bằng cách lấy path của base **trừ segment cuối**; fragment-only được xử lý riêng. Hãy chạy ví dụ trên JDK mục tiêu trước khi thiết kế thao tác chỉ sửa query của một tài liệu. Nếu mục tiêu là giữ nguyên path và chỉ thay query, hãy **xây lại URI từ các thành phần đã được phân tích** bằng constructor phù hợp, đồng thời kiểm tra quy tắc escaping; đừng dựa vào giả định `resolve("?x=1")` sẽ giữ path filename.

### 2.4. Quy tắc thao tác

Khi build đường dẫn từ một thư mục, cấu trúc hợp lý là:

~~~text
baseDirectoryUri (kết thúc /)
         │
         ├── resolve(relativeResource)
         │           │
         │           └── xử lý ., .. theo quy tắc URI
         │
         └── URI kết quả
~~~

Tránh nối chuỗi `base.toString() + resource`. Nó sẽ tạo `...guideimg/logo.svg` khi thiếu slash, hoặc `...guide//img/logo.svg` khi dư slash, hoặc giữ lại các `..` sai kỳ vọng. Ngoài ra `resolve` đã có bước chuẩn hóa path đối với phép nối tham chiếu tương đối; gọi `normalize()` tường minh khi cần thể hiện một chính sách canonical path cho những đầu vào/URI khác.

## 3. `normalize`: rút gọn `.` và `..` trong path

`URI.normalize()` áp dụng cho **hierarchical URI**:

1. Xóa các segment đúng bằng `.`.
2. Nếu `..` có segment trước đó không phải `..`, xóa cặp segment ấy và tiếp tục.
3. Với path tương đối mà segment đầu có dấu hai chấm, có thể thêm `.` ở đầu để tránh đọc nhầm đó là scheme khi parse lại.

Ví dụ:

~~~text
https://docs.example.test/a/b/../c/./d
         normalize()
https://docs.example.test/a/c/d
~~~

Đây là phép rút gọn **theo cú pháp URI**, không phải thao tác trên file thực hay hệ thống thư mục. Nó không tra DNS, không biết symlink, không giải quyết quyền truy cập và không xác nhận rằng các path có cùng tài nguyên phía server.

| Đầu vào | Kết quả/điều cần nhớ |
| --- | --- |
| `/a/b/../c` | `/a/c` |
| `/a/./b` | `/a/b` |
| `../up/./a` | `../up/a` — giữ `..` đầu chuỗi khi không có segment trước để triệt tiêu |
| `https://x.test/a/%2E%2E/b` | Vẫn có `%2E%2E` — `normalize` **không** giải mã percent-escape trước khi xử lý segment |
| `https://x.test/a/../b?x=./y#./z` | Chỉ path đổi; `?x=./y` và `#./z` không phải segment path |
| `mailto:team@example.test` | Opaque URI, `normalize` không thay đổi |

Trong phần bảng minh họa path, các chuỗi như `/a/c` biểu diễn thành phần path, không yêu cầu có scheme. Với URI có trailing slash, hãy kiểm tra đúng semantics directory/file; `normalize` không có nhiệm vụ tự quyết định tài nguyên là thư mục hay file.

Cần phân biệt ba khái niệm thường bị gọi chung là “normalize”:

- **Path syntax normalization:** `URI.normalize()` xử lý `.` / `..` theo cú pháp URI.
- **Encoding/decoding:** `%2E`, `%2F`, `%20` và các ký tự UTF-8 thuộc về biểu diễn octet; `normalize` không tự biến chúng thành ký tự để tiếp tục canonicalize. `getRawPath()` giữ escaping, `getPath()` trả path đã giải mã.
- **Resource canonicalization:** host, route, filesystem, symlink, redirect, URL rewrite, query ordering và chính sách server có thể làm hai URI trỏ tới cùng resource hoặc khác resource; `URI.normalize()` không thể xác nhận điều này.

Ví dụ bảo mật quan trọng:

~~~java
URI input = URI.create("https://files.example.test/public/%2e%2e/private.txt");
System.out.println(input.normalize());
System.out.println(input.getRawPath());
System.out.println(input.getPath());
~~~

Output (khi chạy trong một phương thức Java hợp lệ):

~~~text
https://files.example.test/public/%2e%2e/private.txt
/public/%2e%2e/private.txt
/public/../private.txt
~~~

Kết quả cho thấy `normalize()` **không** phải cơ chế chặn path traversal: tầng xử lý phía sau có thể decode `%2e%2e` thành `..`. Nếu dùng URI để kiểm soát phạm vi tài nguyên, phải kiểm tra và giới hạn đầu vào **trước** khi ghép; hiểu cơ chế decode của web server và không cho phép thay authority/scheme/path tùy ý.

## 4. `relativize`: lấy đường dẫn tương đối khi có cùng gốc

Cú pháp:

~~~java
URI relative = base.relativize(target);
~~~

Với hai URI phân cấp, nếu scheme và authority tương thích, và path của base là **tiền tố** của path target, `relativize` bỏ tiền tố path của base để tạo URI tương đối, giữ query và fragment của target nếu có. Nếu **không đáp ứng**, nó trả lại chính URI target thay vì tự dựng đường dẫn `../...`.

~~~text
base   = https://docs.example.test/guide/
target = https://docs.example.test/guide/img/logo.svg
result = img/logo.svg
~~~

Nhưng:

~~~text
base   = https://docs.example.test/guide/
target = https://docs.example.test/shared/site.css
result = https://docs.example.test/shared/site.css
~~~

Không nên nói `relativize` là thuật toán tìm đường đi tương đối ngắn nhất giữa hai thư mục. Nó **không tự phát sinh** chuỗi `../shared/site.css` trong trường hợp thứ hai. Muốn dựng link tương đối giữa các vị trí không có quan hệ tiền tố, cần chọn đúng base cha chung hoặc giải quyết theo quy tắc định tuyến ứng dụng; đừng mong `relativize` tự tính cây.

Để logic nhất quán, thực hành thường dùng là chuẩn hóa **cả base và target** khi so sánh các path đã biết hợp lệ:

~~~java
URI normalizedBase = base.normalize();
URI normalizedTarget = target.normalize();
URI relative = normalizedBase.relativize(normalizedTarget);
~~~

Khi quan hệ prefix phù hợp và các URI đã chuẩn hóa, có thể kiểm tra phép round-trip:

~~~java
URI restored = normalizedBase.resolve(relative);
System.out.println(restored.equals(normalizedTarget));
~~~

Nếu `relativize` trả lại URI tuyệt đối do khác origin/path prefix, phép `resolve` sau đó vẫn có thể trả target, nhưng lúc ấy **không có một link tương đối**. Hãy kiểm tra `relative.isAbsolute()` (và khi cần authority) nếu hợp đồng ứng dụng yêu cầu phải xuất được URI tương đối.

**Không dùng `relativize` để chứng minh quyền truy cập.** Nó xử lý cấu trúc cú pháp và có thể chịu ảnh hưởng khác biệt biểu diễn path (encoding, dấu slash, chữ hoa thường). Với kiểm soát an ninh cần policy riêng và hiểu URL server sẽ thực sự xử lý.

## 5. Chương trình Java 17+ chạy được: quan sát cả ba phép toán

Tạo file **`UriOperationsDemo.java`**:

~~~java
import java.net.URI;

public class UriOperationsDemo {
    public static void main(String[] args) {
        URI baseFile = URI.create(
                "https://docs.example.test/guide/start.html");
        URI baseDir = URI.create(
                "https://docs.example.test/guide/");
        URI baseWithoutSlash = URI.create(
                "https://docs.example.test/guide");

        URI target = baseDir.resolve("img/../css/site.css").normalize();

        System.out.println("file: "
                + baseFile.resolve("img/logo.svg"));
        System.out.println("dir: "
                + baseDir.resolve("img/logo.svg"));
        System.out.println("no slash: "
                + baseWithoutSlash.resolve("img/logo.svg"));
        System.out.println("up: "
                + baseDir.resolve("../shared/style.css"));
        System.out.println("root: "
                + baseDir.resolve("/public/logo.svg"));
        System.out.println("new authority: "
                + baseDir.resolve("//cdn.example.test/x.svg"));
        System.out.println("normalized: " + target);
        System.out.println("relative: " + baseDir.relativize(target));
        System.out.println("different tree: " + baseDir.relativize(
                URI.create("https://docs.example.test/shared/site.css")));
        System.out.println("query only: "
                + baseFile.resolve("?lang=vi"));
        System.out.println("fragment: "
                + baseFile.resolve("#section2"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 UriOperationsDemo.java
java UriOperationsDemo
~~~

Stdout chính xác:

~~~text
file: https://docs.example.test/guide/img/logo.svg
dir: https://docs.example.test/guide/img/logo.svg
no slash: https://docs.example.test/img/logo.svg
up: https://docs.example.test/shared/style.css
root: https://docs.example.test/public/logo.svg
new authority: https://cdn.example.test/x.svg
normalized: https://docs.example.test/guide/css/site.css
relative: css/site.css
different tree: https://docs.example.test/shared/site.css
query only: https://docs.example.test/guide/?lang=vi
fragment: https://docs.example.test/guide/start.html#section2
~~~

Toàn bộ ví dụ chỉ phân tích và biến đổi URI **trong bộ nhớ**, không gửi HTTP request; các host `example.test` là dữ liệu minh họa, không phải endpoint cần truy cập. Các kết quả cho thấy:

- `baseDir` và `baseFile` cho cùng link `img/logo.svg` vì chúng có cùng thư mục cha.
- `baseWithoutSlash` cho khác kết quả vì `guide` bị coi là segment cuối cần thay.
- `../` quay lên một cấp; `/public/...` đặt path từ root; `//cdn...` thay authority.
- `normalize` làm `img/../css` thành `css`.
- `relativize` chỉ rút gọn được khi path target nằm dưới tiền tố của base; target ở `shared` giữ nguyên URI tuyệt đối.
- `?lang=vi` và `#section2` có hành vi khác nhau với `baseFile`.

Có thể dùng ví dụ này như regression test khi nâng cấp JDK hoặc thay đổi quy ước base URL trong hệ thống.

## 6. Chọn phép toán cho từng tình huống thực tế

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Từ thư mục tài liệu tạo link ảnh/CSS tương đối | Base **kết thúc `/`**, gọi `base.resolve(relativeRef)` |
| Từ trang HTML tạo link tới trang/ảnh khác | Dùng URI đầy đủ của trang làm base; nhớ segment cuối của file sẽ bị thay |
| Rút gọn `a/./b/../c` | `URI.normalize()`, hiểu rằng nó chỉ chuẩn hóa path cú pháp |
| Tạo link tương đối từ thư mục tới tài nguyên bên dưới | `base.normalize().relativize(target.normalize())`, kiểm tra kết quả có thực sự tương đối |
| Thay schema/authority | Dùng URI có schema/authority mục tiêu hoặc constructor được thiết kế cho các component; đừng giả định reference luôn thuộc cùng host |
| Thêm hoặc thay query parameter | Dùng component-aware URI builder/constructor; không ghép chuỗi `?` hoặc áp `resolve("?x=1")` theo trực giác |
| Làm việc với file trên đĩa | Dùng `java.nio.file.Path.resolve` / `Path.normalize`; chuyển đổi `Path.toUri()` / `Path.of(fileUri)` khi thật sự cần file URI |
| Bảo vệ thư mục tài nguyên hoặc outbound HTTP origin | Xác thực input, policy scheme/host/port/path và cách downstream decode; `normalize` không phải biện pháp an ninh độc lập |

### 6.1. URI và `Path` không đồng nhất

`URI.resolve` là thao tác trên các thành phần URI, theo quy tắc phân giải URI; `Path.resolve` là thao tác trên filesystem path theo provider/OS. Với file thực, đoạn Java sau thích hợp hơn việc ghép một `file:` URL từ `Path.toString()`:

~~~java
import java.nio.file.Path;

Path root = Path.of("docs", "guide");
Path file = root.resolve("images").resolve("logo.svg").normalize();
System.out.println(file);
~~~

Đây là **đoạn minh họa**, không công bố stdout cố định vì dấu phân cách đường dẫn và thư mục làm việc phụ thuộc OS. Khi cần file URI, dùng `file.toAbsolutePath().toUri()`; khi cần tạo `Path` từ một file URI phù hợp, dùng `Path.of(fileUri)`. Đừng dùng `URI.create(path.toString())` để tự suy ra file URI từ đường dẫn OS, nhất là Windows có ký tự ổ đĩa và dấu `\`. `Path.normalize` cũng chỉ là chuẩn hóa cú pháp, **không** tự xử lý symlink; nếu kiểm tra containment cho file thực, phải cân nhắc `toRealPath()`, quyền, sự thay đổi filesystem và race conditions.

### 6.2. Escape ký tự: `getRawPath()` khác `getPath()`

Lấy URI chứa ký tự được encode:

~~~java
URI uri = URI.create("https://docs.example.test/assets/a%2Fb.svg");
System.out.println(uri.getRawPath()); // /assets/a%2Fb.svg
System.out.println(uri.getPath());    // /assets/a/b.svg
~~~

`getRawPath()` giữ chuỗi percent-escape; `getPath()` giải mã chúng. Nếu cần bảo toàn ranh giới segment hoặc kiểm tra chuỗi raw, không được thay `getRawPath` bằng `getPath` một cách vô thức. Bên nhận có thể giải mã thêm lần nữa, dẫn tới khác biệt routing và an ninh.

`URI.create("https://docs.example.test/my report.pdf")` là **sai cú pháp** vì chứa khoảng trắng chưa escape, gây `IllegalArgumentException`. Constructor từ component có thể quote ký tự không hợp lệ:

~~~java
URI uri = new URI(
        "https", "docs.example.test", "/my report.pdf", null, null);
System.out.println(uri); // https://docs.example.test/my%20report.pdf
~~~

Đoạn này đòi hỏi ngữ cảnh có `throws java.net.URISyntaxException` hoặc bắt ngoại lệ. Constructor thành phần có thể escape dấu `%` sẵn có; đừng đưa đường dẫn đã percent-encode vào constructor theo cách làm nó bị encode hai lần. Đối với **giá trị từng query parameter**, constructor URI không tự hiểu “đây là một value riêng”: dấu `&`, `=` có nghĩa phân tách tham số. Hãy dùng thư viện builder có khái niệm query parameter, hoặc encode đúng theo giao thức đích. `URLEncoder` dành cho form encoding (`application/x-www-form-urlencoded`), không phải công cụ encode toàn bộ URL hoặc path.

## 7. Ví dụ ghép URI tài nguyên với input bị giới hạn

`resolve` có thể thay scheme/host khi reference là URI tuyệt đối hoặc bắt đầu bằng `//`, và `../` có thể đi ra khỏi path gốc. Vì thế khi nhận tên tài nguyên từ input người dùng, **đừng cho phép một reference URI tùy ý** rồi dựa vào `normalize` để “làm sạch”.

Tình huống đơn giản: server chỉ cho phép tên ảnh gồm chữ Latin, chữ số, `_`, `-` và phần mở rộng `.png` hoặc `.svg`, không chấp nhận dấu `/`, `%`, `?`, `#`, dấu cách hay `..`. Đặt một chính sách tên rõ ràng, sau đó `resolve` và kiểm tra lại scope.

Tạo file **`AssetUriBuilder.java`**:

~~~java
import java.net.URI;

public class AssetUriBuilder {
    private static final URI ROOT =
            URI.create("https://static.example.test/media/");

    public static URI assetUri(String fileName) {
        if (fileName == null
                || !fileName.matches("[A-Za-z0-9_-]+\\.(?:png|svg)")) {
            throw new IllegalArgumentException("Invalid asset file name");
        }

        URI result = ROOT.resolve(fileName).normalize();

        if (!"https".equalsIgnoreCase(result.getScheme())
                || !"static.example.test".equalsIgnoreCase(result.getHost())
                || result.getPort() != -1
                || result.getRawUserInfo() != null
                || !result.getRawPath().startsWith(ROOT.getRawPath())) {
            throw new IllegalArgumentException("Asset outside allowed root");
        }

        return result;
    }

    public static void main(String[] args) {
        System.out.println(assetUri("logo.svg"));
        System.out.println(assetUri("chart_2026.png"));

        for (String candidate : new String[] {
                "../secret.svg",
                "//evil.example.test/logo.svg",
                "team logo.svg"
        }) {
            try {
                assetUri(candidate);
            } catch (IllegalArgumentException ex) {
                System.out.println("Rejected: " + candidate);
            }
        }
    }
}
~~~

~~~bash
javac --release 17 AssetUriBuilder.java
java AssetUriBuilder
~~~

Stdout chính xác:

~~~text
https://static.example.test/media/logo.svg
https://static.example.test/media/chart_2026.png
Rejected: ../secret.svg
Rejected: //evil.example.test/logo.svg
Rejected: team logo.svg
~~~

Điều đáng học ở đây là **whitelist chặt cho một filename đơn lẻ**: không cho đối tượng nhập toàn bộ URI, path gồm nhiều segment hay chuỗi đã encode; thêm kiểm tra scope là một phòng tuyến bổ sung. Đây **không phải hàm sanitizer URI tổng quát**. Nếu bài toán yêu cầu Unicode, thư mục con, percent-escape, query động hoặc user-controlled URL đầy đủ, phải xây chính sách khác, encode theo từng thành phần và xác minh cùng cách decode/redirect mà tầng sử dụng cuối cùng sẽ thực hiện. Khi HTTP client tự follow redirect, đích sau redirect cũng cần policy tương ứng nếu đang hạn chế kết nối ra ngoài.

Trong ứng dụng nội bộ tạo URL tĩnh từ tên tài nguyên tin cậy, có thể đơn giản hơn: chỉ `ROOT.resolve("logo.svg")` là đủ. Đừng thêm code phòng vệ không liên quan nếu đầu vào hoàn toàn do source code kiểm soát.

## 8. Những lỗi thường gặp và cách sửa

**Lỗi 1 — Quên slash cuối của thư mục base.** `URI.create("https://x.test/api").resolve("users")` tạo `https://x.test/users`. Nếu muốn `/api/users`, đổi base thành `https://x.test/api/`.

**Lỗi 2 — Nghĩ `resolve` chỉ nối path.** Tham chiếu `/users` xóa path base; `//other.test/users` đổi authority; `https://other.test/users` mang toàn bộ URI mới. Đừng dùng input tùy ý trong client có chính sách chỉ gọi một host.

**Lỗi 3 — Hiểu `relativize` sẽ luôn trả URI tương đối.** Khi khác origin hoặc đường dẫn không có quan hệ prefix, nó có thể trả URI target nguyên vẹn. Kiểm tra kết quả thay vì dùng trực tiếp làm đường dẫn tương đối bắt buộc.

**Lỗi 4 — Dùng `normalize` làm path traversal defense.** `%2e%2e`, symlink, path decoding ở proxy/server và URL redirect không nằm trong nhiệm vụ của `URI.normalize`. Kiểm tra đầu vào, origin và semantics downstream.

**Lỗi 5 — Quên query và fragment là hai thành phần riêng.** Dùng `resolve("?lang=vi")` tưởng luôn giữ file base hoặc nối chuỗi không encode giá trị query dẫn tới URL sai. Phân tách path, query, fragment và dựng lại đúng contract.

**Lỗi 6 — Dùng `Path` như URI hoặc ngược lại.** `Path.resolve` tuân theo filesystem; `URI.resolve` theo URI hierarchy. Đường dẫn OS không phải chuỗi URI hợp lệ một cách tự động.

**Lỗi 7 — Gọi phương thức mà bỏ kết quả.** `base.resolve(ref)`, `base.normalize()` và `base.relativize(target)` đều trả `URI` mới; gán kết quả khi muốn sử dụng.

**Lỗi 8 — Nhầm encoded và decoded path.** `getPath()` có thể chứa thêm `/` từ `%2F`; `getRawPath()` giữ nguyên escape. Không dùng chúng thay thế cho nhau khi phân loại segment hoặc xác thực input.

## 9. Bài tập tự kiểm tra

**Bài 1.** `base = https://docs.example.test/a/b/`. Kết quả của `base.resolve("../c.svg")`?  
**Đáp án:** `https://docs.example.test/a/c.svg`.

**Bài 2.** Vì sao `URI.create("https://x.test/a").resolve("b")` khác `URI.create("https://x.test/a/").resolve("b")`?  
**Đáp án:** base `/a` xem `a` là segment cuối cần thay → `https://x.test/b`; base `/a/` coi vị trí thêm bên trong path thư mục → `https://x.test/a/b`.

**Bài 3.** `URI.create("https://x.test/a/b/../c").normalize()` cho gì?  
**Đáp án:** `https://x.test/a/c`. Chỉ path dot-segment được rút gọn.

**Bài 4.** `URI.create("https://x.test/a/").relativize(URI.create("https://x.test/b/y"))` cho gì?  
**Đáp án:** URI target nguyên vẹn `https://x.test/b/y`, không tự sinh `../b/y`.

**Bài 5.** `base.resolve("//other.test/img.svg")` giữ nguyên host không?  
**Đáp án:** Không. Nó dùng authority `other.test`, thừa hưởng scheme từ base.

**Bài 6.** `URI.create("https://x.test/public/%2e%2e/admin").normalize()` có chặn thoát thư mục `public` không?  
**Đáp án:** Không. Percent-encoded dot segments chưa được giải mã; đây không phải bằng chứng containment.

**Bài 7.** Muốn sửa query của `https://x.test/a/page.html` mà giữ nguyên `/a/page.html`, có nên mặc định dùng `resolve("?x=1")`?  
**Đáp án:** Không. Trên Java `URI`, phép đó có thể trả `https://x.test/a/?x=1`. Cần xây URI từ các thành phần để giữ path theo yêu cầu.

## 10. Checklist khi thiết kế ghép đường dẫn tài nguyên

1. **Xác định loại gốc:** URI trỏ tới *directory* hay *file*? Nếu là directory, base phải mang đúng trailing `/`.
2. **Phân loại đầu vào:** relative path, absolute path, authority-relative hay absolute URI? Có cho phép thay scheme/host không?
3. **Chọn phép toán:** `resolve` để tạo đích; `normalize` để bỏ dot-segment path; `relativize` để rút gọn path theo prefix khi có thể.
4. **Giữ component chính xác:** path, query, fragment, raw/decoded encoding; đừng nối chuỗi khi component có ý nghĩa cú pháp.
5. **Kiểm tra đầu ra:** origin, port, allowed path, điều kiện prefix; không coi syntactic normalization là validation bảo mật.
6. **Thử edge cases:** có/không trailing slash, `../`, `/`, `//`, `#`, `?`, percent-escape và đích khác origin.
7. **Phân biệt I/O:** `URI` chỉ biến đổi cú pháp; việc tải tài nguyên xảy ra ở HTTP client, URL handler hoặc filesystem API riêng.

## Tài liệu chính thức

- [Java SE 17 — `java.net.URI`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): mục **Operations on URI instances**, **normalize**, **resolve**, **relativize**, escaping và URI versus URL. Đây là hợp đồng chính để đối chiếu các ví dụ.
- [Java SE 21 — `java.net.URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): dùng khi dự án chạy JDK 21 và muốn so sánh contract với Java 17.
- [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): phân biệt file path local với URI hierarchy; `resolve`, `normalize`, `toUri` và `toRealPath`.
- [RFC 3986 — Reference Resolution](https://www.rfc-editor.org/rfc/rfc3986#section-5.2): cơ sở để hiểu resolution của URI trong các hệ thống web hiện đại. **Lưu ý:** Javadoc `java.net.URI` mô tả thuật toán dựa trên RFC 2396 và các sai khác do Java quy định; khi cần kết luận hành vi Java, ưu tiên đúng Javadoc và kiểm thử trên JDK mục tiêu.

Tư duy cốt lõi: **định nghĩa rõ URI gốc và cấu trúc từng component, dùng đúng phép toán cho mục đích của nó, rồi xác nhận đầu ra đúng scope của ứng dụng.**
