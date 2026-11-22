# Mã hóa URI đúng một lần và phân biệt dữ liệu với ký tự phân cách trong Spring MVC

## 1. Mục tiêu học tập

URI là địa chỉ để xác định resource và cũng là một **cấu trúc cú pháp**. Trong cùng một chuỗi URI, các dấu `/`, `?`, `#`, `&`, `=` hoặc `:` có thể đóng vai trò phân cách; chúng cũng có thể xuất hiện như **dữ liệu** trong tên tài liệu, từ khóa tìm kiếm hoặc mã định danh. Một dấu có vai trò ngữ pháp phải được giữ nguyên; cùng dấu đó nếu là dữ liệu trong một thành phần phù hợp thì cần được biểu diễn bằng percent-encoding khi có nguy cơ bị diễn giải thành cú pháp.

Bài này áp dụng cho **Spring Framework 6.x, Spring MVC trên Servlet stack, Spring Boot 3.x và Java 17+**, tập trung vào:

- Nắm cấu trúc URI theo RFC 3986: scheme, authority, path, query và fragment.
- Phân biệt ký tự **reserved**, **unreserved** và `%HH` theo UTF-8.
- Hiểu chính xác “**encode một lần tại ranh giới tạo URI từ giá trị gốc; parse cấu trúc trước rồi decode đúng ngữ cảnh tại ranh giới nhận**”.
- Tránh encode hai lần `%2F → %252F`, decode hai lần `%252E%252E → %2E%2E → ..`, và đổi ý nghĩa của dấu `/`, `?`, `&`, `=`, `+`.
- Sử dụng `UriComponentsBuilder` và URI template variables một cách an toàn, biết khác biệt `UriComponentsBuilder#encode()` và `UriComponents#encode()`.
- Không gọi `URLDecoder` bừa bãi trên `@RequestParam` hoặc `@PathVariable` đã được MVC bind.
- Phân biệt URL query thông thường với quy ước `application/x-www-form-urlencoded`, đặc biệt dấu cộng và dấu cách.
- Biết giới hạn encoded slash trong path ở Servlet container, gateway và Spring Security.
- Xây ví dụ chạy được Java 17+, Spring Boot controller, `curl` và MockMvc; thiết kế URL versioning an toàn.

**Không áp dụng máy móc sang Spring WebFlux**: reactive URL handling và filter stack có thể khác. Các tình huống đặc biệt về URL encoding cần thử qua đúng gateway, Servlet container, Spring Security và Spring MVC của hệ thống đang triển khai.

## 2. URI gồm những phần nào?

Ví dụ:

```text
https://api.example.test:8443/api/v1/items/abc-42?q=a%2Bb%20%26%20c%2Fd#details
|--- scheme --|----- authority ----|---------- path ----------|----- query ------|fragment
```

Để rõ cú pháp tổng quát:

```text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
                  |             |
                  |             +-- path dùng / phân đoạn
                  +-- host và port của ví dụ

Ví dụ:
https://example.test/api/v1/items/42?sort=createdAt&order=desc#top
                    ^ path        ^ query                ^ fragment
```

- **Scheme**: `https` hoặc `http`; không phải dữ liệu tùy ý do client quyết định khi bạn đang tạo URL nội bộ.
- **Authority**: host/port và một số cú pháp liên quan; đặc biệt phải kiểm soát host nếu URL dùng cho redirect, server-side HTTP requests hay callback.
- **Path**: thường gồm các segment cách nhau bằng `/`; với Spring MVC, route `/api/v1/items/{id}` phân biệt dấu slash thật với dữ liệu trong segment.
- **Query**: bắt đầu sau dấu `?`; trên web, nhiều framework nhận convention `name=value&name2=value2`. RFC 3986 mô tả query rộng hơn quy ước key-value này.
- **Fragment**: bắt đầu bằng dấu `#` trong URI người dùng nhìn thấy; **không được gửi trong HTTP request target tới server**. Browser xử lý fragment ở client.

Việc Spring controller chỉ nhìn thấy `/api/v1/items/42` hoặc `?q=...` không có nghĩa nên trộn tất cả các phần này thành một chuỗi chưa được phân tích.

## 3. Reserved, unreserved và percent-encoding

Theo RFC 3986:

```text
unreserved = A-Z a-z 0-9 "-" "." "_" "~"

gen-delims = ":" "/" "?" "#" "[" "]" "@"
sub-delims = "!" "$" "&" "'" "(" ")" "*" "+" "," ";" "="

reserved = gen-delims / sub-delims
```

Một ký tự reserved **có thể** làm dấu phân cách trong ngữ cảnh cụ thể; ở ngữ cảnh khác nó có thể được phép như dữ liệu. Không thể lập một bảng “luôn encode dấu / trong mọi URL” vì `/` là dấu phân đoạn path, nhưng trong từ khóa query `a/b` nó thường là dữ liệu.

**Percent-encoding** thay một *byte* thành `%HH` (hai chữ số hexadecimal). Để mã hóa Unicode, trước tiên lấy bytes UTF-8 rồi biểu diễn các bytes cần escape. Ví dụ:

| Giá trị dữ liệu | Bytes và biểu diễn khi cần encode |
| --- | --- |
| Space | `%20` trong URI percent-encoding |
| `+` | `%2B` nếu phải tránh hiểu như space theo form query |
| `/` | `%2F` khi là dữ liệu segment, không phải phân cách |
| `&` | `%26` nếu là dữ liệu trong parameter value |
| `=` | `%3D` nếu là dữ liệu và có nguy cơ là dấu key/value |
| `#` | `%23` nếu client phải gửi ký tự # làm dữ liệu |
| `%` | `%25` cho dấu percent literal |
| `é` | `%C3%A9` (bytes UTF-8 C3 A9) |
| `?` | `%3F` nếu là data cần tránh bị xem là dấu mở query |

Chữ hex lớn/nhỏ thường tương đương trong escape (`%2f` và `%2F`), nhưng hệ thống nên tạo dạng nhất quán. Percent-encoding dành cho **giá trị trong đúng URI component**, không phải phép biến đổi mù toàn chuỗi. Ví dụ encode dấu `:` và `/` của `https://` như data sẽ phá cấu trúc.

### Tại sao parse trước rồi mới decode?

RFC 3986 nhấn mạnh tách các component và subcomponent theo cú pháp rồi mới giải mã các escape thuộc component đó. Nếu decode raw request target trước khi phân đoạn, `%2F` có thể biến thành dấu `/` điều khiển routing; `%26` có thể biến thành `&` và bị parser query xem là parameter mới. Một số phần như percent-encoded unreserved có thể normalize an toàn hơn, nhưng **không được biến một reserved data byte thành delimiter** tùy tiện.

```text
Đúng về thứ tự ý tưởng:
raw URI -> parse scheme/authority/path/query/fragment
        -> parse query keys / delimiters ở đúng lớp
        -> decode dữ liệu từng component một lần
        -> validate canonical application value

Sai:
raw URI -> decode mọi %HH trước -> split theo "/" hoặc "&"
                                        (data có thể hóa delimiter)
```

Trong Spring MVC Servlet stack, một phần parsing/decoding đã do container/framework làm. Controller nhận `@RequestParam` và `@PathVariable` **thường đã là giá trị dữ liệu**, không phải raw URL string để decode lại.

## 4. “Mã hóa đúng một lần” thực chất là gì?

Nên phân biệt ba dạng:

1. **Raw logical value**: chuỗi business `"a+b & c/d"`, chưa encode.
2. **Encoded URI component**: `a%2Bb%20%26%20c%2Fd` khi được đưa vào parameter value dưới chính sách strict encoding.
3. **URI hoàn chỉnh**: `/api/v1/search?q=a%2Bb%20%26%20c%2Fd`, trong đó `?`, `=` có ý nghĩa cú pháp.

Quy trình tạo URI đúng:

```text
Raw data:            a+b & c/d
URI template:        /api/v1/search?q={term}
Strict expand:       /api/v1/search?q=a%2Bb%20%26%20c%2Fd
HTTP request:        gửi URI đã tạo (không encode lại nguyên URL)
MVC @RequestParam:   a+b & c/d
```

Nếu raw data của bạn là literal `"%2F"` (ba ký tự percent, 2, F), **mã hóa đúng một lần** có thể tạo `%252F`, vì dấu `%` trong dữ liệu phải escape thành `%25`. Đó **không phải bug double encoding**: nó biểu diễn chính xác nội dung literal mà người dùng muốn tìm.

Ngược lại, nếu `"%2F"` đã là percent-encoded URI component của ký tự `/`, việc đưa nó vào một API mong **raw data** và encode tiếp tạo `"%252F"` sẽ là **double encoding do nhầm trạng thái dữ liệu**.

### Hai tình huống trông giống nhau nhưng khác bản chất

| Giá trị mà nghiệp vụ thực sự muốn | Đầu vào cho URI builder | Wire encoding đúng |
| --- | --- | --- |
| Ký tự slash `/` | Raw `/` ở đúng component | `%2F` nếu là dữ liệu của một path segment |
| Ba ký tự literal `%2F` | Raw `%2F` | `%252F` |
| Ký tự plus `+` trong query form | Raw `+` | `%2B` |
| Một dấu cách trong query | Raw space | `%20` (URI strict); có thể `+` theo form convention |
| Dấu `&` thuộc một search term | Raw `&` | `%26` |
| Dấu `&` ngăn cách hai query params | Cấu trúc URI, không phải giá trị | Giữ `&` thật trong query syntax |

Muốn tránh encode hai lần, **không lưu chung raw logical values và URI đã encoded trong cùng một biến không có contract**. Đặt tên biến `rawTerm`, `encodedUrl`, `URI uri` để người đọc code biết trạng thái.

## 5. Phân biệt dữ liệu với dấu phân cách

### 5.1. Dấu / trong path

```text
/api/v1/items/a/b        -> hai path segments "a" và "b"
/api/v1/items/a%2Fb      -> có ý định chứa "a/b" trong một segment
```

Về lý thuyết percent-encoded slash là cách biểu diễn slash như dữ liệu. **Nhưng trên Servlet stack thực tế**, reverse proxy/Tomcat/Spring Security có thể từ chối `%2F`, chuẩn hóa thành slash trước khi mapping, hoặc áp policy khác. Vì vậy đừng dựa vào encoded slash trong `@PathVariable` như một giải pháp portable.

**Thiết kế thường an toàn hơn:** dùng ID URL-safe như `item_42`, UUID, Base64url *không padding* khi phù hợp và có đánh giá security, hoặc đặt dữ liệu chứa slash vào query param/JSON body, không cố làm “một path variable tự do chứa mọi ký tự”.

### 5.2. Dấu ? và # trong dữ liệu

```text
/api/v1/search?q=what?now
/api/v1/search?q=what%3Fnow
```

RFC 3986 cho phép `?` trong query component, nhưng một số lớp parser/URL builder có cách xử lý URL template khác nhau. Với dữ liệu business opaque, strict URI variable encoding thường dùng `%3F` để không có ambiguity.

Với dấu `#`:

```text
https://example.test/api/v1/search?q=C#section
```

Phần sau `#` là fragment và **không đi tới server**; tham số `q` có thể chỉ nhận `C`. Nếu tìm chuỗi `"C#section"`, encode giá trị thành `C%23section` trước khi tạo URI.

### 5.3. Dấu & và = trong query

```text
?q=a&role=admin             -> thông thường hai params q và role
?q=a%26role%3Dadmin        -> một giá trị q: "a&role=admin"
```

Nếu nối chuỗi:

```java
String url = "/api/v1/search?q=" + userInput;
```

và `userInput="a&role=admin"`, bạn vô tình tạo **query parameter injection**. Không hẳn là SQL injection, nhưng có thể đổi semantics filter, paging hoặc authorization nếu ứng dụng đọc các params mới.

Thay bằng URI builder có **queryParam và opaque template variable**. Nếu application cho phép user xác định tên query parameter động, validate tên riêng; đừng tạo syntax bằng dữ liệu tùy ý.

### 5.4. Dấu ; và matrix/path parameters

Dấu `;` có ý nghĩa riêng trong một số framework/path-segment conventions. Spring MVC hỗ trợ matrix variables trong cấu hình tương ứng, nhưng Spring Security `StrictHttpFirewall` thường từ chối semicolon trong URL path mặc định vì rủi ro bỏ qua quy tắc security.

Không assume dấu `;` trong một `@PathVariable` tự do sẽ giữ nguyên qua mọi proxy/container/firewall. Nếu ứng dụng thực sự dùng matrix params, hãy đánh giá tổng thể routing + authorization + cấu hình firewall, không chỉ đổi một property để “cho phép mọi thứ”.

## 6. Dấu cộng + và dấu cách: khác nhau ở URI và form encoding

Đây là nguồn bug phổ biến nhất với `@RequestParam`.

**Trong RFC 3986 generic URI**, dấu `+` không tự động có nghĩa là space. Nhưng với quy ước **`application/x-www-form-urlencoded`** được các form/parser web sử dụng cho query parameters, `+` thường được diễn giải là dấu cách. Nhiều Servlet parameter parsers áp convention này cho query string.

| URL query gửi | Giá trị `@RequestParam("q")` thường nhận |
| --- | --- |
| `?q=a+b` | `"a b"` |
| `?q=a%2Bb` | `"a+b"` |
| `?q=a%20b` | `"a b"` |
| `?q=a%2Bb%20c` | `"a+b c"` |
| `?q=100%25` | `"100%"` |
| `?q=%252F` | `"%2F"` |
| `?q=%2F` | `"/"` |

Phân biệt:

- `java.net.URI.getQuery()` percent-decodes query, nhưng **không tự thay mọi literal `+` thành space** theo form convention.
- `java.net.URLDecoder` dành cho `application/x-www-form-urlencoded`, **không phải generic “decode toàn bộ URL”**; nó biến `+` thành space.
- `@RequestParam` trên Servlet MVC thường nhận parameter đã được servlet request parameter parsing decode theo convention.
- Không chạy `URLDecoder.decode(q, UTF_8)` thêm một lần với `q` đã bind: literal `+` có thể thành space, literal `%2F` có thể biến thành slash.

### Khi nào dùng URLEncoder?

`URLEncoder` của Java thực thi **HTML form encoding**. Nó biến space → `+` và plus → `%2B`; thích hợp cho form-urlencoded name/value, không dùng trực tiếp để mã hóa path segment hoặc toàn URL.

Ví dụ Java 17 chạy độc lập:

Tệp `FormEncodingDemo.java`:

```java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class FormEncodingDemo {
    public static void main(String[] args) {
        String raw = "a+b c/d&x=1";

        String encoded =
                URLEncoder.encode(raw, StandardCharsets.UTF_8);
        String decoded =
                URLDecoder.decode(encoded, StandardCharsets.UTF_8);

        System.out.println("form=" + encoded);
        System.out.println("decoded=" + decoded);

        URI uri = URI.create("/api/v1/search?q=a%2Bb");
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("uriQuery=" + uri.getQuery());
    }
}
```

Biên dịch và chạy:

```bash
javac FormEncodingDemo.java
java FormEncodingDemo
```

**Stdout chính xác** trên Java 17:

```text
form=a%2Bb+c%2Fd%26x%3D1
decoded=a+b c/d&x=1
rawQuery=q=a%2Bb
uriQuery=q=a+b
```

Sự khác nhau `getRawQuery()`/`getQuery()` ở `java.net.URI` cho thấy percent-decoding không đồng nghĩa form decoding. Để xây HTTP URI trong Spring, ưu tiên `UriComponentsBuilder`/`UriBuilder` theo component thay vì cố dùng `URLEncoder` cho cả path.

## 7. Spring UriComponentsBuilder: encode ở đúng thời điểm

Theo tài liệu Spring Framework, có **hai phương pháp encode khác nhau**:

1. `UriComponentsBuilder.encode()`: encode URI template, rồi **strictly encode URI variables khi expand**. Đây thường là lựa chọn tốt khi dữ liệu chèn vào template là **opaque data**.
2. `UriComponents.encode()`: expand variables trước rồi encode các ký tự **illegal** trong từng URI component, nhưng **không nhất thiết escape reserved chars vốn hợp lệ trong component** (ví dụ `;` trong path). Khi URI variables chứa dữ liệu có dấu phân cách, semantics có thể khác.

Ví dụ an toàn cho query value:

```java
String term = "a+b & c/d";

String url = UriComponentsBuilder
        .fromPath("/api/v1/search")
        .queryParam("q", "{term}")
        .encode()
        .buildAndExpand(term)
        .toUriString();

System.out.println(url);
```

Trong project Spring Web, output kỳ vọng:

```text
/api/v1/search?q=a%2Bb%20%26%20c%2Fd
```

Đây là snippet Java trong method đã import `org.springframework.web.util.UriComponentsBuilder`, không phải chương trình `javac` độc lập vì cần Spring dependency.

**Điểm then chốt:** `queryParam("q", "{term}")` đặt **URI variable** vào đúng vị trí value, sau đó `encode()` trước `buildAndExpand(...)` khiến value được encode nghiêm ngặt. Không đưa user value vào query string bằng cách tự nối:

```java
// KHÔNG NÊN:
String url = "/api/v1/search?q=" + rawTerm;

// CŨNG DỄ SAI khi rawTerm đã encode:
String encodedOnce = URLEncoder.encode(rawTerm, UTF_8);
String url2 = UriComponentsBuilder
    .fromPath("/api/v1/search")
    .queryParam("q", "{term}")
    .encode()
    .buildAndExpand(encodedOnce) // % bị encode thành %25
    .toUriString();
```

Các snippet anti-pattern chỉ minh họa logic, không phải file biên dịch độc lập. API builder nhận **raw value** khi strict-expanding, không nhận một chuỗi đã percent-encoded.

### Tại sao builder.encode() và components.encode() không giống nhau?

Giả sử path variable chứa `"a;b"`:

```java
String strict = UriComponentsBuilder
        .fromPath("/items/{id}")
        .encode()
        .buildAndExpand("a;b")
        .toUriString();

String componentEncoded = UriComponentsBuilder
        .fromPath("/items/{id}")
        .buildAndExpand("a;b")
        .encode()
        .toUriString();
```

Ví dụ với Spring 6.x:

```text
strict:           /items/a%3Bb
componentEncoded: /items/a;b
```

`;` hợp lệ theo cú pháp path ở mức URI component, nhưng có thể mang nghĩa reserved theo router/matrix params. **Strict URI-variable encoding** thường phù hợp với user input dữ liệu. Với dấu `/` trong một segment, builder strict có thể tạo `%2F`, nhưng **không đồng nghĩa server Servlet chắc chắn chấp nhận request đó**.

### DefaultUriBuilderFactory và HTTP clients

`DefaultUriBuilderFactory.EncodingMode` có các lựa chọn như:

- `TEMPLATE_AND_VALUES`: pre-encode template, strict encode variables.
- `VALUES_ONLY`: strict encode variables nhưng không encode template theo cách trên.
- `URI_COMPONENT`: expand rồi encode URI components, giữ reserved chars hợp lệ ở component.
- `NONE`: không encode.

Các HTTP client versions có default encoding mode khác nhau (ví dụ RestTemplate theo lịch sử có behavior tương thích cũ). Không dựa vào “framework sẽ tự encode” mà bỏ qua kiểm tra output. Đặt policy thống nhất cho HTTP clients và test với `+`, `&`, `/`, `%` và Unicode.

## 8. Query parameters: dùng API cấu trúc thay vì string concatenation

Một query có ba parameter:

```text
/api/v1/search?q=Java%20%26%20Spring&page=2&sort=createdAt
```

Phần `?` phân tách path và query; ký tự `&` **ngoài giá trị encoded** phân tách params; `=` phân tách key/value trong convention.

Xây bằng builder:

```java
String result = UriComponentsBuilder
    .fromPath("/api/v1/search")
    .queryParam("q", "{term}")
    .queryParam("page", "{page}")
    .queryParam("sort", "createdAt")
    .encode()
    .buildAndExpand(
        java.util.Map.of("term", "Java & Spring", "page", 2))
    .toUriString();
```

Kết quả mong đợi:

```text
/api/v1/search?q=Java%20%26%20Spring&page=2&sort=createdAt
```

Đây là code snippet có Spring dependency. `Map.of` không cho null, nên hãy xử lý nullable/optional params trước khi expand. Đừng cố đưa nguyên một chuỗi `"q=a&role=admin"` vào `queryParam` như một parameter name; API phải phân biệt **tên param** và **giá trị param**.

### Tên param cũng là dữ liệu nhập?

Nếu chương trình cho phép client chọn tên parameter tùy ý, một tên như `q&role` có thể gây ambiguity nếu ghép chuỗi. Thông thường các **tên query param là code constants** do server/client developer định nghĩa; nếu cần dynamic name, hãy validate theo allowlist và dùng component-aware API. Không “sanitize” bằng cách xóa một số dấu rồi giả vờ input đã an toàn trong mọi ngữ cảnh.

### Repeated parameters

```text
?tag=java&tag=spring
```

Spring MVC có thể bind repeated values bằng `@RequestParam List<String> tag` hoặc `MultiValueMap<String,String>`. Không dùng `Map<String,String>` nếu contract cần giữ mọi giá trị. Nếu API yêu cầu một giá trị duy nhất, quy định xử lý duplicates và validate rõ để tránh HTTP parameter pollution giữa gateway/security và ứng dụng.

## 9. Path segment, @PathVariable và API versioning

Một API versioned thường có route:

```java
@GetMapping("/api/v1/items/{id}")
public ItemResponse one(@PathVariable String id) {
    return new ItemResponse(id);
}
```

Ở đây `/api/v1/items/` là **cấu trúc path cố định**, còn `{id}` là **giá trị một segment**. Nếu ID thật chứa slash, việc encode thành `%2F` **có thể bị từ chối ở proxy/container/StrictHttpFirewall**, và Spring path matching/servlet request URI handling khác nhau theo cấu hình.

Khuyến nghị:

- Thiết kế ID dùng ký tự URL-safe như `A–Z`, `a–z`, `0–9`, `_`, `-` và khi phù hợp `~`.
- Dùng UUID hay opaque server-generated ID khi có thể; không dùng raw filesystem path làm ID trong route.
- Nếu dữ liệu tự do như “folder/a/b” là search term, đặt trong query param đã encode hoặc JSON body thay vì ép vào `@PathVariable` một segment.
- Nếu API versioning bằng `/api/v1`, hãy giữ `v1` là **cấu trúc route**, không chèn một string chứa `v1/users` như một biến ID rồi mong nó tạo route mới.
- Khi dùng ID từ user, kiểm tra business-format ở controller/service sau bind; đừng nghĩ URL encoding thay thế input validation hoặc authorization.

### URI encoding không phải file path escaping

Nếu `id` là `"../../secret"` hoặc một chuỗi đã decode từ `%2e%2e%2f`, **không** dùng nó làm filesystem path. Không thể kết luận path traversal đã được chặn chỉ vì URI được encode. Lấy server-owned key → tra metadata/authorized mapping → truy cập storage an toàn; validate canonical path tại nơi thực sự thao tác filesystem.

## 10. Encoded slash, percent và Spring Security

Spring Security `StrictHttpFirewall` được thiết kế để chặn nhiều request target đáng ngờ. Mặc định nó hạn chế nhiều trường hợp như:

- Encoded slash `%2F` và encoded double slash ở **URL path**.
- Encoded percent `%25` ở path (liên quan double decode bypass).
- Semicolon `;`, backslash, encoded period và một số ký tự đáng ngờ tùy phiên bản.
- URL chưa normalize, ví dụ dot segments có thể làm các lớp hiểu khác nhau.

Lý do: Servlet API, reverse proxy và firewall đôi khi không đồng ý về việc một path đã được decoded hay normalized. Nếu security rule xét một đường dẫn nhưng dispatcher xét đường dẫn khác, có nguy cơ **authorization bypass**.

**Đừng vô hiệu hóa StrictHttpFirewall hoặc bật mọi `setAllowUrlEncodedSlash(true)` chỉ vì một test `/items/a%2Fb` thất bại.** Chọn ID an toàn hoặc endpoint query/body phù hợp, rồi test trọn đường đi. Với trường hợp thực sự cần một escape reserved trong path, phải audit config container/proxy/security + MVC mapping + logging/canonicalization, không chỉ một property.

### Những trạng thái dữ liệu dễ gây bypass

```text
Raw URI             /assets/%252e%252e%252fsecret
Decode lần 1        /assets/%2e%2e%2fsecret
Decode lần 2        /assets/../secret
Normalize path      /secret   (tùy hệ thống)
```

Một tầng security chặn `../` trong chuỗi còn encoded, tầng ứng dụng decode thêm rồi mở file có thể tạo đường vượt thư mục. Đối với security decisions, các tầng phải thống nhất một canonical interpretation và tránh decode bổ sung không kiểm soát.

## 11. Ngăn double-encoding và double-decoding

### 11.1. Encode hai lần

```text
Dữ liệu muốn biểu diễn: "/"       (ký tự slash)
Encode component:     "%2F"
Encode lại string:    "%252F"
Server decode một lần: "%2F"      (literal, không còn là slash)
```

Nếu nghiệp vụ thật sự muốn literal `"%2F"`, kết quả sau decode một lần là đúng. Lỗi nằm ở **không xác định input đã encode hay chưa**.

Các dấu hiệu bug:

- Giao diện hiển thị `%20` thay vì space.
- Server nhận `%2F` thay vì slash user nhập.
- Redirect có `%252F` dù client chỉ gửi dấu slash.
- URL có chuỗi `%252525` do nhiều lớp encode nối tiếp.

### 11.2. Decode hai lần

```text
Raw query:            ?q=%252F
Servlet parameter:    "%2F"
Sai: URLDecoder(q):   "/"
```

Nếu user tìm đúng ba ký tự `"%2F"`, decode thêm biến thành slash và thay đổi dữ liệu. Nếu chuỗi trở thành đường dẫn/file name sau đó, bug có thể thành lỗ hổng bảo mật.

Không viết:

```java
@GetMapping("/search")
public String bad(@RequestParam String q) {
    return java.net.URLDecoder.decode(
        q, java.nio.charset.StandardCharsets.UTF_8);
}
```

Đây là anti-pattern trong Spring MVC Servlet: `q` đã được bind/decoded theo request parameter handling. Tương tự, đừng decode `@PathVariable` lần hai khi framework đã tạo logical value, và đừng lấy `getRequestURI()` rồi gọi `URLDecoder` toàn chuỗi trước khi route/authorize.

### 11.3. Nên log dạng nào?

Cho mục đích debug, có thể log **URI path/route đã chuẩn hóa và các tên tham số được phép**, có mask/redaction. Không tự log toàn raw URI khi query có token, password, email/PII; URL cũng xuất hiện ở reverse proxy, browser history và metrics. Nếu cần nghiên cứu một lỗi encoding trong môi trường test, log raw target và bound value riêng nhưng trên dữ liệu giả, để so sánh đúng một lần decode.

## 12. UTF-8, Unicode và normalization

URI percent-encoding làm việc với **bytes**. Khi chuỗi là Unicode, nên dùng UTF-8 thống nhất giữa client/server. Ví dụ chữ `é` mã hóa UTF-8 thành bytes `C3 A9`, URI representation có thể là `%C3%A9`. Tiếng Việt có nhiều ký tự multi-byte, nên không thể lấy mỗi Java UTF-16 `char` rồi viết thành một `%HH`.

Bên cạnh encoding, Unicode còn có thể có nhiều dạng chuẩn hóa, ví dụ ký tự có dấu dạng precomposed và dạng base letter + combining mark. Hai chuỗi nhìn giống nhau có thể khác dãy code points. URI encoding **không tự** quyết định quy tắc normalize Unicode. Nếu ID/search/filename cần so sánh nhất quán:

1. Xác định nhu cầu và quy tắc normalization (ví dụ NFC) theo nghiệp vụ.
2. Áp dụng normalization **trên raw logical value** ở tầng phù hợp, không decode đi decode lại trên URI wire string.
3. Không normalize thay đổi bất ngờ các secret/password/signatures; có những protocol yêu cầu byte identity.
4. Với ID case-insensitive, định nghĩa case folding và locale rõ ràng (tránh `toLowerCase()` thiếu chính sách).
5. Test Unicode tiếng Việt, emoji surrogate pairs, combining marks và ký tự ngoài ASCII.

Không dùng URI canonicalization như một phép “khử mọi ký tự nguy hiểm” thay cho validation. Khả năng cho phép dữ liệu như `/` hoặc `&` phụ thuộc đúng context; nó có thể hợp lệ trong tên tìm kiếm nhưng không hợp lệ trong path key nội bộ.

## 13. HTTP client, browser, HTML form và URL query

### Browser form GET

```html
<form action="/api/v1/search" method="get">
  <input name="q" value="a+b c/d">
  <button type="submit">Search</button>
</form>
```

Khi browser submit GET form, nó tạo query theo form rules, thường dạng `q=a%2Bb+c%2Fd` hoặc phép escape tương đương, rồi Spring MVC nhận `"a+b c/d"`. Không lấy chuỗi query gửi từ HTML form rồi encode nguyên chuỗi lần nữa.

### Browser fetch/JavaScript

JavaScript `URLSearchParams` thường dùng quy tắc form-style cho query params (space là `+`); `encodeURIComponent` dùng quy tắc percent-encoding khác và nên chỉ encode **một value**, không phải toàn URL. Dù khác wire spelling, nếu client và Servlet parser tuân thủ cùng convention, business value vẫn khớp.

Không mix các encoder tùy tiện:

- URL được xây bằng một component-aware builder rồi coi là encoded, không chạy `URLEncoder.encode(entireUrl,...)`.
- Form body `application/x-www-form-urlencoded` có serializer riêng, không nhầm nó với JSON body.
- Đừng gọi `decodeURIComponent` hai lần ở frontend hoặc `URLDecoder.decode` hai lần ở backend để “chắc chắn giải mã”.
- Nếu URL đã có query, dùng API thêm params có cấu trúc thay vì nối `?`/`&` thủ công khi không chắc URL state.

### Những dạng input đáng kiểm thử

| Logical value | Vì sao quan trọng |
| --- | --- |
| `a+b` | Plus literal khác space trong form decoder |
| `a b` | Space có thể thành `%20` hoặc `+` |
| `a&b=c` | Dễ bị biến thành params khác |
| `a/b` | Slash hợp lệ trong query, nhạy cảm trong path segment |
| `100%` | Percent literal cần `%25` |
| `%2F` | Bộc lộ bug double encode/decode |
| `C#` | Fragment delimiter phải được encode nếu là data |
| `a?b` | Dấu mở query dễ bị nối sai |
| `Tôi học Java` | UTF-8, Unicode |
| `../secret` | Không để URI decode biến thành file traversal |
| `a;b` | Matrix params/semicolon firewall |
| `"emoji 🚀"` | UTF-8 nhiều byte và UTF-16 surrogate |

## 14. Ứng dụng Spring Boot 3 Java 17+: URL builder và MVC binding

Ứng dụng demo có ba endpoints:

- `GET /api/v1/search?q=...`: nhận query đã bind; trả lại logical value để học (echo input chỉ dành cho demo).
- `GET /api/v1/items/{id}`: nhận ID path segment URL-safe.
- `POST /api/v1/links`: nhận JSON chứa **raw** `term` và `id`, xây URL bằng `UriComponentsBuilder.encode().buildAndExpand(...)`.

Để chạy, tạo project Maven Spring Initializr **Java 17+, Spring Boot 3.x**, chọn dependencies: **Spring Web**, **Validation**, **Spring Boot Test**. Package tất cả file Java là `com.example.demo`.

### 14.1. DemoApplication.java

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 14.2. UriDemoController.java

Tệp `src/main/java/com/example/demo/UriDemoController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/v1")
public class UriDemoController {

    @GetMapping(path = "/search",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public SearchResponse search(@RequestParam("q") String q) {
        // q là giá trị ĐÃ được request parameter binder xử lý.
        // KHÔNG gọi URLDecoder.decode(q, ...) một lần nữa.
        return new SearchResponse(q);
    }

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse item(@PathVariable("id") String id) {
        // Demo chỉ dự kiến ID URL-safe, ví dụ "item_42".
        // Ứng dụng thật phải tìm resource và authorize.
        return new ItemResponse(id);
    }

    @PostMapping(path = "/links",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<LinkResponse> makeLink(
            @Valid @RequestBody LinkRequest input) {

        // input.term() là RAW logical data từ JSON, chưa encode URI.
        String url = UriComponentsBuilder
                .fromPath("/api/v1/items/{id}")
                .queryParam("q", "{term}")
                .encode()
                .buildAndExpand(Map.of(
                    "id", input.id(),
                    "term", input.term()))
                .toUriString();

        return ResponseEntity.ok(new LinkResponse(url));
    }

    public record SearchResponse(String q) {}

    public record ItemResponse(String id) {}

    public record LinkResponse(String url) {}

    public record LinkRequest(
            @NotBlank
            @Pattern(
                regexp = "[A-Za-z0-9_-]+",
                message = "id must use URL-safe characters")
            String id,

            @NotBlank
            @Size(max = 200)
            String term) {}
}
```

**Vì sao dùng @Pattern cho ID?** API demo quyết định `id` là một segment “opaque URL-safe token”, không phải path tự do. Input như `"a/b"` bị Bean Validation từ chối ở endpoint tạo link thay vì sinh một URL path chứa encoded slash mà container có thể không chấp nhận. Việc giới hạn character set còn giúp giảm ambiguity giữa URL routing, authorization và logging. Production có thể chọn UUID hoặc scheme ID khác.

**Vì sao không gọi URLEncoder?** `UriComponentsBuilder` đã nhận raw term và strict-encode khi expand. Nếu client gửi literal `"%2F"` như term, URL tạo ra sẽ chứa `%252F` ở query, đúng vì nó giữ nguyên ba ký tự literal sau khi Servlet parameter decoding.

**Vì sao GET item vẫn phải kiểm tra quyền?** Encoding chỉ giúp tạo URL đúng cú pháp; một user biết hoặc đoán ID `item_42` không có nghĩa được đọc resource đó. Controller demo echo ID mà không truy vấn DB chỉ nhằm dạy binding, không phải triển khai authorization.

### 14.3. Chạy ứng dụng

Maven wrapper trên macOS/Linux:

```bash
./mvnw spring-boot:run
```

PowerShell Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Các file Spring Boot cần dependency classpath; không thể biên dịch `UriDemoController.java` độc lập bằng `javac` nếu không có Spring libraries. Sau khi startup, cổng mặc định thường là 8080 trừ khi `server.port` được cấu hình khác.

## 15. curl thực hành: so sánh dữ liệu và delimiters

### 15.1. Plus literal khác space

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a+b'
```

Trên một Servlet request parameter parser theo quy ước form query, output JSON dự kiến:

```json
{"q":"a b"}
```

Tiếp theo:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a%2Bb'
```

JSON dự kiến:

```json
{"q":"a+b"}
```

Cùng một ký tự cộng trong raw business value nhưng nếu client gửi `+` trần vào form-style query, server có thể nhận space. Client muốn plus literal phải encode thành `%2B`.

### 15.2. Dấu & và = là một giá trị hay nhiều params?

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a&role=admin'
```

Kỳ vọng endpoint nhận `q="a"`, còn `role` trở thành parameter khác (controller demo không dùng). Nếu muốn tìm đúng chuỗi `"a&role=admin"`:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a%26role%3Dadmin'
```

JSON dự kiến:

```json
{"q":"a&role=admin"}
```

Đây là ví dụ tại sao **không nối input raw vào query string**.

### 15.3. Percent literal và encoded slash trong query

```bash
curl -s 'http://localhost:8080/api/v1/search?q=%2F'
```

Output:

```json
{"q":"/"}
```

Trong khi:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=%252F'
```

Output:

```json
{"q":"%2F"}
```

Không chạy `URLDecoder.decode(q)` thêm một lần ở controller, vì khi đó trường hợp thứ hai bị biến thành `"/"`. Lưu ý các URL này mã hóa slash trong **query value**, không yêu cầu container hỗ trợ encoded slash trong **path**.

### 15.4. Curl để tự mã hóa tham số

Cách tránh tự đếm `%HH` khi test nhiều ký tự:

```bash
curl -sG 'http://localhost:8080/api/v1/search' \
  --data-urlencode 'q=a+b & c/d'
```

Curl tạo query value theo encoding phù hợp cho form-style parameter; JSON response mong đợi:

```json
{"q":"a+b & c/d"}
```

Không tự gắn sẵn percent-encoded value vào `--data-urlencode` nếu bạn muốn bắt đầu từ raw logical value, vì có thể khiến dấu `%` bị encode lần nữa.

### 15.5. Tạo URL bằng Spring UriComponentsBuilder

```bash
curl -s -X POST 'http://localhost:8080/api/v1/links' \
  -H 'Content-Type: application/json' \
  -d '{"id":"item_42","term":"a+b & c/d"}'
```

Body JSON expected:

```json
{"url":"/api/v1/items/item_42?q=a%2Bb%20%26%20c%2Fd"}
```

Query giữ được một logical value chứa `+`, space, `&` và slash. Path vẫn giữ `/api/v1/items/` như delimiters, còn ID được validate là URL-safe. Nếu tạo link với `term="%2F"`, JSON output sẽ chứa `q=%252F` (đúng khi term là literal percent-2-F).

### 15.6. Fragment không đến server

```bash
curl -s 'http://localhost:8080/api/v1/search?q=C#section'
```

Theo cách xây URI và semantics HTTP, phần `#section` là fragment và không được gửi trong request target; query `q` chỉ là `C`. Muốn server nhận `C#section`:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=C%23section'
```

Expected:

```json
{"q":"C#section"}
```

### 15.7. Encoded slash trong path không portable

Thử `GET /api/v1/items/a%2Fb` có thể gặp HTTP 400, request bị firewall từ chối, hoặc path được diễn giải khác, tùy gateway/Servlet/Spring Security. **Không cam kết status/JSON cho phép thử này**. Endpoint dùng `item_42` an toàn hơn. Nếu ID logic phải chứa slash, cân nhắc query/body, không bật unrestricted encoded slash như một cách sửa nhanh.

## 16. Kiểm thử MockMvc (Spring Boot 3)

`MockMvc` cho phép test controller binding và URL builder. Nhưng **MockMvc không chứng minh đầy đủ percent-decoding/normalization của Servlet container thực**. Đặc biệt, `.param("q", raw)` cung cấp parameter value trực tiếp trong mock request; đừng kết luận từ đó rằng raw URI `?q=a+b` sẽ decode theo đúng parser Tomcat.

Tệp `src/test/java/com/example/demo/UriDemoControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UriDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void binderPassesRawLogicalQueryValueToController()
            throws Exception {
        mvc.perform(get("/api/v1/search")
                .param("q", "a+b & c/d"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.q").value("a+b & c/d"));
    }

    @Test
    void builderStrictlyEncodesOpaqueQueryVariable()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                  "{\"id\":\"item_42\",\"term\":\"a+b & c/d\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.url").value(
                "/api/v1/items/item_42?q=a%2Bb%20%26%20c%2Fd"));
    }

    @Test
    void percentSequenceLiteralMustRemainLiteral()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"id\":\"x\",\"term\":\"%2F\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.url").value(
                "/api/v1/items/x?q=%252F"));
    }

    @Test
    void rejectsSlashInOpaquePathIdentifier()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"id\":\"a/b\",\"term\":\"java\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void ordinarySafePathVariableIsReadable()
            throws Exception {
        mvc.perform(get("/api/v1/items/item_42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("item_42"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là **mẫu code kiểm thử** dành cho dự án Spring Boot 3 có dependency tương ứng; không phải kết quả đã chạy trong repository cụ thể. Nếu bật Spring Security, test POST có thể cần `spring-security-test`, mock identity và `csrf()`; request chưa có CSRF token có thể nhận 403 **trước** controller.

### Test nào cần HTTP thật?

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`/HTTP client hoặc `curl` qua embedded Tomcat và proxy để xác minh:

- Raw `?q=a+b` so với `?q=a%2Bb`.
- `?q=%252F` còn literal percent sequence sau parameter binding.
- Path có `%2F`, `%25`, `%2E`, `;` bị xử lý như thế nào qua firewall/container.
- Path normalization trước/sau authorization không lệch nhau.
- Unicode non-ASCII, percent triplets sai (`%ZZ`), slash/backslash và double encode.
- Reverse proxy có normalize lại URL hoặc thay header/redirect Location hay không.

MockMvc không đi qua mọi chi tiết connector/Servlet request parser thật, vì vậy unit test build URI **và** integration test HTTP wire nên bổ sung cho nhau.

## 17. URI đã encoded sẵn: khi nào dùng build(true)?

`UriComponentsBuilder.build(true)` báo cho builder rằng các components được truyền vào đã được **percent-encoded hợp lệ**. Nó không phải cách “hãy encode giúp tôi một lần” hoặc nút khắc phục double-encoding cho dữ liệu chưa xác định.

Hai tình huống:

- **Raw user data:** dùng template variables, `.encode().buildAndExpand(raw)`.
- **URI components đã encoded, có provenance và validation rõ:** chỉ khi bạn thật sự biết các components đã encode đúng ngữ cảnh thì mới dùng các APIs “already encoded” như `build(true)`, tránh encode lại.

Không dùng `build(true)` để đưa raw `"a&role=admin"` vào query rồi mong Spring tự bảo vệ delimiter. Nếu có sẵn một URI hoàn chỉnh đã được encoded từ nguồn đáng tin, giữ nó dưới kiểu `URI` hoặc dùng API parsing phù hợp; đừng biến một URL encoded hoàn chỉnh thành “raw variable” rồi encode thêm.

### Khi cần thay query trên một URL đã có sẵn

Nếu URL ban đầu đã chứa query và fragment, dùng `UriComponentsBuilder.fromUri(...)` với input URI đã parse đúng và các phương thức thay query có cấu trúc, thay vì nối `"?q=" + value`. Tùy builder state, URI từ `URI` vốn có encoded components: hãy kiểm tra docs cho cách thêm raw values/encoded components và encoding mode, test URL cuối thực tế. Không gọi encode một lần nữa lên chuỗi đã percent-encoded nếu API nhận “already encoded URI”.

## 18. Redirect, Location và open redirect

Endpoint có thể tạo `Location` header hoặc trả redirect:

```java
URI location = UriComponentsBuilder
        .fromPath("/api/v1/items/{id}")
        .encode()
        .buildAndExpand("item_42")
        .toUri();
```

Snippet này an toàn với một ID URL-safe. Với Spring MVC, controller có thể trả `ResponseEntity.created(location)...` cho POST tạo resource. Nếu URL public nằm sau proxy, cần cấu hình forwarded headers đáng tin thay vì tự suy host từ header client.

**Không nhận toàn bộ URL redirect từ untrusted input rồi redirect trực tiếp**. URI encoding không thay validation scheme/host/path của URL redirect; user có thể cung cấp URL trỏ tới trang phishing hoặc `javascript:`/protocol không hợp lệ trong một ngữ cảnh nguy hiểm.

Nếu server làm HTTP fetch đến URL do client gửi, có thể phát sinh **SSRF**; component-aware encoding chỉ xử lý cú pháp, không ngăn truy cập nội bộ, DNS rebinding hoặc chặn scheme/host. Với redirect/callback/fetch hãy dùng allowlist hosts/schemes và policy mạng phù hợp.

## 19. URI, form body, JSON và HTML output là những context khác nhau

| Context | Encoder/decoder đúng lớp | Điều cần tránh |
| --- | --- | --- |
| URI path variable | URI template + strict variable encoding | Nối raw `/`, rely encoded slash |
| URI query parameter value | `queryParam` + strict variable encoding | Nối raw `&`, `=` hoặc `#` |
| HTML form query/body | Form serializer/`URLEncoder` | Dùng làm generic whole-URL encoder |
| JSON request body | JSON serializer/Jackson | Tự URL encode JSON string không có lý do |
| HTML text/attribute | HTML escaping/template engine | Cho rằng URI encoding chống XSS |
| SQL parameter | Prepared statements/bind variables | Cho rằng percent-encoding chống SQL injection |
| Filesystem path | Server-generated key/canonical path policy | Cho rằng `%2E%2E` đã “safe” |
| HTTP redirect target | URI creation + allowlist schemes/hosts | Open redirect/SSRF vì tin raw URL |

**Một chuỗi có thể đi qua nhiều context khác nhau**, nhưng mỗi context đòi một loại escaping riêng. “Encode exactly once” là quy tắc chống encode/decode lặp **ở cùng ranh giới URI**, không phải lý do để bỏ HTML escaping khi hiển thị dữ liệu từ URI trên web page.

## 20. Những lỗi triển khai thường gặp

1. **Dùng `URLEncoder.encode(wholeUrl)`**: làm hỏng scheme, slash, dấu hỏi và dấu phân cách.
2. **Nối raw search term sau `?q=`**: dấu `&` có thể tạo thêm parameter.
3. **Không encode literal plus `+` trong form query**: server nhận space.
4. **Decode lại `@RequestParam` bằng URLDecoder**: mất literal plus/percent sequence.
5. **Decode raw path trước khi tách segments**: encoded slash hóa delimiter.
6. **Đưa percent-encoded value vào strict URI variable builder**: encode `%` thành `%25` lần nữa.
7. **Coi literal `%2F` luôn là một dấu slash**: có thể client thực sự muốn ba ký tự.
8. **Dùng `UriComponents#encode()` như strict encoding của arbitrary user data**: reserved chars hợp lệ trong component có thể không bị escape.
9. **Cho rằng encoded slash trong @PathVariable luôn được container nhận**: tùy connector/firewall/path matching.
10. **Tắt StrictHttpFirewall để encoded slash chạy** mà không xem authorization bypass.
11. **Không nhất quán normalize path giữa proxy và ứng dụng**: security và routing nhìn hai resource khác nhau.
12. **Nhầm `#fragment` là dữ liệu gửi tới server**: fragment không có trong HTTP request target.
13. **Dùng path value làm filename**: URI escaping không ngăn path traversal sau decode.
14. **Coi JSON/HTML/SQL đều cần URL encoding**: context-sensitive escaping khác nhau.
15. **Lưu raw URI cả token vào access logs**: lộ credential/PII.
16. **Dùng URL query chứa secret**: dễ lộ qua history/log/referrer, nên dùng transport phù hợp.
17. **Không giới hạn ID shape**: URL versioning/path routing khó dự đoán khi có slash/semicolon/period encoded.
18. **Tin chữ hex hoa/thường khác giá trị**: `%2f` và `%2F` cùng byte, nhưng policy normalizer phải nhất quán.
19. **Giải mã URI nhiều lần để “sửa” input**: biến dữ liệu thành ký tự cú pháp ngoài ý muốn.
20. **Dùng UTF-16 Java char làm từng percent-escape**: non-ASCII cần UTF-8 bytes.
21. **Đổi URL đã encoded qua một framework client có encoding mode khác**: xuất hiện `%2520` hoặc reserved char biến mất.
22. **MockMvc.param chứng minh wire encoding đúng**: mock parameter đã là giá trị; cần test HTTP thật.
23. **Tin @PathVariable chứa decoded user input nên khỏi validate**: encoding không thay authz/format validation.
24. **Không kiểm tra duplicate query parameters**: gateway và app có thể chọn các giá trị khác nhau.
25. **Cho phép untrusted full URL trong Location hoặc HTTP fetch**: encoding không chống open redirect/SSRF.
26. **Tạo raw URL bằng string formatting ở nhiều nơi**: cùng data qua các encoder khác nhau; nên gom URI construction vào API rõ.
27. **Không kiểm tra Unicode normalization**: ID có thể trông giống nhau nhưng khác bytes/code points.
28. **Không kiểm thử proxies/CDNs**: edge có thể decode/normalize/rewrite URL trước Spring.

## 21. Checklist code review và kiểm thử

### Tạo URI

- [ ] Đã biết raw logical value nào là data, literal nào là delimiter?
- [ ] URI được xây theo components/templates thay vì nối string raw?
- [ ] URI variables chứa dữ liệu opaque được strict-encode **khi expand**, không encode trước rồi lại encode?
- [ ] Percent `%` trong raw value được giữ đúng: literal `%2F` → wire `%252F`?
- [ ] Query param values chứa `+`, `&`, `=`, `#`, `/` có test?
- [ ] Nếu URL đã encoded sẵn, có contract rõ và không encode nó như raw variable?
- [ ] API path ID là URL-safe và độc lập với filesystem path?
- [ ] URI public/Location sau proxy dùng scheme/host đáng tin?

### Nhận URI

- [ ] Spring MVC @RequestParam/@PathVariable đã được framework decode; không gọi URLDecoder lần hai?
- [ ] Không parse raw URI bằng split/double-decode trước khi xác định components?
- [ ] Container, Spring Security và gateway nhất quán về encoded slash/period/percent?
- [ ] Query repeated/unknown params được xử lý theo API contract?
- [ ] Dữ liệu từ URI vẫn được validate, authorize và escape theo HTML/SQL/filesystem context khác?

### Test

- [ ] Java unit test chứng minh form encoding và URI raw/decoded query khác nhau?
- [ ] URI builder output được assert với plus, space, ampersand, slash và percent literal?
- [ ] MockMvc test giá trị bound và generated URL đúng?
- [ ] HTTP thật test `?q=a+b` khác `?q=a%2Bb`?
- [ ] HTTP thật test `%252F` không bị backend double-decode?
- [ ] Test path firewall với `%2F`, `%25`, `%2E` và `;` ở môi trường thực?
- [ ] Thử Unicode tiếng Việt/emoji và hình thức canonicalization cần thiết?
- [ ] Review redirects/external URL for SSRF/open redirect và không lộ secret trong query/logs?

## 22. Tự kiểm tra kiến thức

**1.** Trong `/items/a/b`, dấu slash thứ hai là gì?

**Đáp án:** Dấu phân cách path segments. Nếu một ID thực sự chứa slash, cần encoding theo component nhưng trên Servlet stack encoded slash có thể bị reject; nên ưu tiên ID URL-safe hoặc query/body.

**2.** Vì sao `?q=a&role=admin` khác `?q=a%26role%3Dadmin`?

**Đáp án:** Dạng thứ nhất có thể là hai params; dạng sau chứa một giá trị q với literal `&` và `=` sau binding.

**3.** Trong form-style query, `?q=a+b` và `?q=a%2Bb` cho kết quả gì?

**Đáp án:** Thường là `"a b"` và `"a+b"` tương ứng. Literal plus cần `%2B`.

**4.** Nếu giá trị nghiệp vụ literal `"%2F"`, tại sao builder sinh `"%252F"`?

**Đáp án:** Dấu percent là dữ liệu phải encode thành `%25`; sau một lần decode, backend nhận đúng literal `%2F`. Không được tùy tiện decode thêm.

**5.** Khác biệt chính giữa `UriComponentsBuilder.encode()` và `UriComponents.encode()`?

**Đáp án:** Builder encode template trước và strict-encode expanded variable values; components encode sau expand, giữ một số reserved chars hợp lệ trong component.

**6.** `@RequestParam q` đã là logical value; có nên gọi `URLDecoder.decode(q)` không?

**Đáp án:** Không. Có thể double-decode percent sequences và biến plus literal thành space.

**7.** URL fragment `#section` có đến Spring MVC controller không?

**Đáp án:** Không. Nếu muốn dữ liệu chứa # trong query, dùng `%23`.

**8.** Tại sao không nên bật firewall allow encoded slash tùy tiện?

**Đáp án:** Proxy/container/security/MVC có thể diễn giải đường dẫn khác nhau, gây bypass route authorization.

**9.** URI encoding có thay thế HTML escaping hoặc prepared SQL không?

**Đáp án:** Không. Mỗi output context có luật escaping riêng, URL encoding giải quyết cấu trúc URI.

**10.** Vì sao MockMvc `.param("q","a+b")` không chứng minh hành vi raw URL `?q=a+b`?

**Đáp án:** `.param` đặt logical parameter value trực tiếp cho mock request. Muốn kiểm raw URI decoding phải gửi HTTP thực qua Servlet container.

**11.** Khi API versioning dạng `/api/v1`, v1 thuộc raw business value hay path structure?

**Đáp án:** Nó là cấu trúc route có chủ đích; không encode cả `/api/v1` như một variable.

**12.** Vì sao cần biết dữ liệu đã percent-encoded hay chưa trước khi gọi builder?

**Đáp án:** Raw logical value và encoded component có contract khác nhau. Encode encoded-string thêm lần nữa gây double encoding, còn bỏ encode raw string có thể biến data thành delimiters.

## 23. Nguồn tham khảo

- RFC 3986 — URI Generic Syntax, percent-encoding, reserved/unreserved, parse before decode: https://www.rfc-editor.org/rfc/rfc3986.html
- RFC 3987 — Internationalized Resource Identifiers: https://www.rfc-editor.org/rfc/rfc3987.html
- WHATWG URL Standard — URL parsing/form-urlencoded conventions: https://url.spec.whatwg.org/
- Spring Framework — URI Links và encoding modes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
- Spring Framework — `UriComponentsBuilder` API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html
- Spring Framework — `UriUtils` API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/util/UriUtils.html
- Spring Framework — Spring MVC Path Matching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Security — StrictHttpFirewall and request matching: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Java 17 — `java.net.URI`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java 17 — `java.net.URLEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java 17 — `java.net.URLDecoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html
- RFC 9110 — HTTP Semantics and request targets: https://www.rfc-editor.org/rfc/rfc9110.html
