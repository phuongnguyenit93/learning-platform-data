# URI, đường dẫn, tham số truy vấn và quy tắc mã hóa trong Spring Web

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt URI, URL, đường dẫn (path), tham số truy vấn (query parameter) và fragment.
- Đọc, thiết kế và ghép URI đúng ranh giới giữa các thành phần.
- Giải thích percent-encoding theo UTF-8, sự khác nhau giữa `%20` và `+`, cũng như ký tự có ý nghĩa cú pháp.
- Nhận dữ liệu path/query bằng Spring MVC và tạo URI an toàn bằng `UriComponentsBuilder`.
- Nhận diện lỗi mã hóa hai lần, giải mã quá sớm, dữ liệu nhập không hợp lệ và sự khác biệt giữa proxy, servlet container, Spring MVC.

## 1. URI là gì? Những thành phần nào tạo nên một địa chỉ web?

**URI (Uniform Resource Identifier)** là chuỗi dùng để định danh một tài nguyên theo một scheme. **URL (Uniform Resource Locator)** là cách gọi thường dùng cho URI cung cấp vị trí/cách truy cập, ví dụ `https://...`. Không phải URI nào cũng là địa chỉ HTTP: `urn:isbn:...` là ví dụ dạng URN.

Cú pháp tổng quát của URI phân cấp theo RFC 3986:

```text
scheme ":" hier-part [ "?" query ] [ "#" fragment ]

https://api.example.com:8443/products/42?q=c%C3%A0%20ph%C3%AA&tag=java#reviews
└─┬─┘   └────────┬────────┘ └─────┬────┘ └───────────┬───────────┘ └──┬──┘
scheme       authority           path                query           fragment
              host + port
```

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | `https` | Quy ước truy cập/định danh; scheme HTTP(S) quyết định ngữ cảnh trao đổi web. |
| Authority | `api.example.com:8443` | Phần quyền hạn; với URL HTTP thường chứa host và port tùy chọn. Có thể có userinfo theo cú pháp URI nhưng không nên đưa thông tin đăng nhập vào URL. |
| Path | `/products/42` | Đường dẫn phân cấp, thường ánh xạ đến tài nguyên hoặc route. |
| Query | `q=c%C3%A0%20ph%C3%AA&tag=java` | Phần sau dấu `?`, dùng truyền tiêu chí/tuỳ chọn theo quy ước ứng dụng. |
| Fragment | `reviews` | Phần sau `#`, chỉ vị trí/tham chiếu bên trong representation phía client. Fragment **không được gửi** trong HTTP request-target tới server. |

Lưu ý: `?` mở đầu query và `#` mở đầu fragment là dấu phân tách URI; `&` và `=` thường phân tách cặp key/value trong *cách diễn giải query của ứng dụng*, không phải cấu trúc bắt buộc cho mọi URI theo RFC 3986. Ví dụ `?filter=status:open` hoàn toàn có thể là một query hợp lệ.

### URI tuyệt đối và tham chiếu tương đối

- URI tuyệt đối: `https://example.com/docs/setup?lang=vi`, có scheme.
- Tham chiếu tương đối: `../setup?lang=vi` hoặc `/docs/setup`, cần base URI để xác định đích.
- Path bắt đầu bằng `/` thường là đường dẫn tuyệt đối trong authority hiện tại; path không bắt đầu bằng `/` thường tương đối với thư mục của URI cơ sở.
- `.` và `..` là dot-segment trong path; chuẩn có quy tắc chuẩn hóa. Đừng tự loại bỏ hoặc giải mã chúng tùy tiện khi xử lý dữ liệu URL chưa tin cậy.

Ví dụ: từ base `https://example.com/docs/java/intro`, tham chiếu `../spring?lang=vi` có thể resolve thành `https://example.com/docs/spring?lang=vi`. Cần phân biệt **resolve relative URI** với thao tác cộng chuỗi; phép cộng chuỗi dễ làm sai dấu `/`, `?` và `#`.

## 2. Path: cách định vị và ánh xạ endpoint

Path là một chuỗi các *segment* được phân tách bằng `/`. Với `/api/v1/products/42`, các segment chính là `api`, `v1`, `products`, `42`. Slash làm dấu phân cấp; chuỗi `42` có thể là route variable, trong khi `products` là segment tĩnh.

```text
GET /api/v1/products/42 HTTP/1.1
Host: shop.example.com
```

Trong Spring MVC, route thường được mô tả bằng `@RequestMapping`, `@GetMapping`, `@PostMapping`,… và các placeholder trong path.

```java
@RestController
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping("/{id}")
    Map<String, Object> getOne(@PathVariable long id) {
        return Map.of("id", id, "status", "ok");
    }
}
```

Đây là **đoạn mã trong ứng dụng Spring Web có dependency Spring MVC**, không phải file Java độc lập. Khi client gọi `GET /api/v1/products/42`, Spring ánh xạ `id = 42` (kiểu `long`) và có thể trả JSON chứa `"id": 42`, `"status": "ok"` nếu ứng dụng có message converter JSON. Thứ tự thuộc tính JSON không phải một phần hợp đồng của ví dụ.

Những điểm cần phân biệt:

1. `/products` và `/products/` là hai path khác nhau về mặt cú pháp; redirect/route matching với trailing slash phụ thuộc cấu hình framework và server, không nên mặc định chúng tương đương.
2. Chữ hoa/chữ thường, separator và cách xử lý dấu `;` có thể ảnh hưởng route. Thiết kế endpoint nhất quán, xác định rõ quy ước.
3. `@PathVariable` dành cho giá trị nằm **trong path template**; `@RequestParam` dành cho tham số được Spring trích từ query (và có thể cả dữ liệu form tùy Servlet API).
4. Path segment chứa dấu `/` như dữ liệu, chẳng hạn mã sản phẩm `cup/blue`, là trường hợp khó: nếu mã hóa thành `cup%2Fblue` thì reverse proxy hoặc servlet container có thể từ chối/giải mã trước khi Spring route. Không giả định mã hóa slash sẽ hoạt động giống nhau trên mọi tầng. Cân nhắc ID không chứa slash hoặc truyền chuỗi đặc biệt qua query/body.
5. Path là một phần URI, không tự động là đường dẫn file trong hệ điều hành. Nếu sau đó map sang filesystem, phải kiểm tra việc giải mã, dot-segment và chặn path traversal.

### Thiết kế path và query theo vai trò

| Nhu cầu | Ví dụ | Lý do |
|---|---|---|
| Lấy một tài nguyên theo ID | `GET /products/42` | ID là thành phần định danh tài nguyên. |
| Lọc danh sách | `GET /products?category=book` | Tiêu chí truy vấn quyết định tập kết quả. |
| Phân trang | `GET /products?page=2&size=20` | Tùy chọn xem danh sách. |
| Tìm kiếm | `GET /search?q=spring%20mvc` | Chuỗi tìm kiếm là giá trị query. |
| Chọn tài nguyên con | `GET /products/42/reviews/9` | Cấu trúc lồng nhau thể hiện quan hệ tài nguyên. |

Đây là quy ước REST thường dùng, không phải quy tắc bắt buộc của chuẩn URI. Các tham số query **có thể làm thay đổi tài nguyên được truy xuất hoặc cache key**; không nên coi query chỉ là dữ liệu trang trí.

## 3. Query string: tên, giá trị và tham số lặp

Xem ví dụ:

```text
GET /products?q=c%C3%A0%20ph%C3%AA&tag=java&tag=web&sort=price%3Aasc&page=2 HTTP/1.1
```

Theo cách phân tích phổ biến cho ứng dụng web:

- `q` có giá trị giải mã `cà phê`.
- `tag` xuất hiện **hai lần**: `java` và `web`. Server có thể gom chúng thành danh sách, chọn một, hoặc giữ nhiều giá trị; định nghĩa hành vi trong API contract.
- `sort` có giá trị `price:asc`; ký tự `:` được mã hóa ở vị trí giá trị như `%3A`.
- `page` là văn bản `"2"` trên wire; framework có thể chuyển sang số nguyên nếu controller khai báo kiểu `int`.
- `?flag`, `?flag=` và không có `flag` là những hình thức có thể khác nhau về ngữ nghĩa; ứng dụng cần quyết định rõ.
- Thứ tự query param không nên có ý nghĩa trừ khi giao thức/API định nghĩa; thứ tự của **các giá trị lặp cùng key** có thể quan trọng đối với một số API.

Spring MVC ví dụ đọc path và query cùng lúc:

```java
@RestController
@RequestMapping("/api")
class SearchController {

    @GetMapping("/products/{category}")
    Map<String, Object> search(
            @PathVariable String category,
            @RequestParam(name = "q", defaultValue = "") String keyword,
            @RequestParam(name = "tag", required = false) List<String> tags,
            @RequestParam(defaultValue = "1") int page) {

        return Map.of(
                "category", category,
                "keyword", keyword,
                "tags", tags == null ? List.of() : tags,
                "page", page);
    }
}
```

Với `GET /api/products/books?q=c%C3%A0%20ph%C3%AA&tag=java&tag=web&page=2`, Spring có thể bind `category = "books"`, `keyword = "cà phê"`, `tags = ["java", "web"]`, `page = 2`. Ví dụ là đoạn controller dùng trong Spring MVC; cần import các annotation/class tương ứng. Binding kiểu số sai hoặc thiếu giá trị bắt buộc thường dẫn đến lỗi phía client (ví dụ HTTP 400, tùy cấu hình exception handling).

Dữ liệu query có thể xuất hiện trong lịch sử trình duyệt, log của server, proxy hoặc công cụ analytics. **Không đặt mật khẩu, access token hay dữ liệu nhạy cảm vào query string** chỉ vì kết nối đang dùng HTTPS.

## 4. Percent-encoding: mã hóa byte bên trong từng thành phần

URI theo RFC 3986 dùng một tập ký tự cho cú pháp. Khi cần biểu diễn byte không phù hợp hoặc một delimiter đóng vai trò *dữ liệu*, dùng percent-encoding: `%` theo sau **hai chữ số hệ 16**. Ví dụ dấu cách có byte ASCII `0x20` nên là `%20`.

### Nhóm ký tự quan trọng

- **Unreserved**: `A-Z a-z 0-9 - . _ ~`. Thông thường giữ nguyên.
- **Reserved**: `:/?#[]@!$&'()*+,;=`. Một ký tự có thể là dấu cú pháp ở thành phần này nhưng được phép là dữ liệu ở thành phần khác.
- **Non-ASCII**: với nội dung Unicode trên web, thường chuyển chuỗi sang byte **UTF-8**, rồi percent-encode những byte cần mã hóa. Ví dụ `à` là byte UTF-8 `C3 A0` nên `%C3%A0`.
- **Dấu `%` là dữ liệu thật**: phải biểu diễn bằng `%25`; chuỗi `%20` là ba ký tự mã hóa cho byte space, không phải nội dung giống chữ `%20` ban đầu.

| Dữ liệu muốn biểu diễn | Biểu diễn thường dùng khi là dữ liệu trong component | Vì sao |
|---|---|---|
| Dấu cách | `%20` | Dấu cách không thuộc tập ký tự URI cho phép. |
| Dấu cộng `+` | `%2B` | Tránh nhầm với quy ước form, nơi `+` biểu diễn space. |
| Dấu `/` trong **một segment** | `%2F` | Không muốn slash trở thành ký tự tách segment. |
| Dấu `?` trong giá trị | `%3F` | Không muốn tạo dấu mở query ngoài ý muốn. |
| Dấu `#` trong giá trị | `%23` | Không muốn tạo fragment ngoài ý muốn. |
| Dấu `&` trong giá trị query kiểu key/value | `%26` | Không muốn chia thêm tham số. |
| Dấu `=` trong giá trị query kiểu key/value | `%3D` | Không muốn bị hiểu là ký tự phân tách key/value. |
| Dấu `%` | `%25` | Không tạo escape sequence sai. |
| Chuỗi `cà phê` trong query | `c%C3%A0%20ph%C3%AA` | Mã hóa hai ký tự có dấu theo UTF-8 và dấu cách. |

**Quy tắc quan trọng: chia thành phần trước, mã hóa dữ liệu của từng thành phần sau.** Không mã hóa nguyên URI bằng một hàm dành cho một chuỗi dữ liệu; làm vậy sẽ biến cả `:`, `/`, `?`, `&` cấu trúc thành dữ liệu. Ngược lại, đừng ghép dữ liệu chưa mã hóa bằng `+` với query hoặc path rồi hy vọng server hiểu đúng.

### Ví dụ từng bước với UTF-8

Chuỗi tìm kiếm `cà phê & trà` được chuyển sang byte UTF-8. Khi là **một giá trị query**, dạng percent-encoding được chọn ở đây là:

```text
Dữ liệu:      cà phê & trà
Query value:  c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
URI:          /search?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
Server nhận:  q = "cà phê & trà"
```

Nếu ghi thẳng `/search?q=cà phê & trà` thì dấu `&` có nguy cơ bị tách thành một query param mới trong parser key/value. Dấu cách và ký tự Unicode chưa được biểu diễn theo URI ASCII chuẩn; browser có thể tự sửa nhưng hành vi của các thư viện không nhất thiết giống nhau.

### Vì sao đôi lúc space là `+` chứ không phải `%20`?

`application/x-www-form-urlencoded` là **quy ước mã hóa dữ liệu biểu mẫu**: dấu cách biến thành `+`; dấu `+` thật phải thành `%2B`. Trong quy ước này:

```text
Dữ liệu:                  cà phê + C++
Form-encoded value:       c%C3%A0+ph%C3%AA+%2B+C%2B%2B
Percent-encoded spaces:   c%C3%A0%20ph%C3%AA%20%2B%20C%2B%2B
```

Hai kết quả biểu diễn cùng dữ liệu khi được giải mã bằng **đúng cơ chế tương ứng**. Trong URI syntax thuần túy, `+` không mặc nhiên có nghĩa là space. Các bộ giải mã query theo quy ước form thường diễn giải `+` là dấu cách; vì vậy ký tự cộng thật trong search term như `C++` cần được encode thành `C%2B%2B`.

## 5. Java 17+: phân tích URI và phân biệt bộ mã hóa form

Java chuẩn có `java.net.URI` để phân tích URI và `java.net.URLEncoder` cho quy ước `application/x-www-form-urlencoded`. Chúng phục vụ hai nhu cầu khác nhau.

Tệp độc lập `UriBasics.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriBasics {
    public static void main(String[] args) {
        URI uri = URI.create(
            "https://api.example.com:8443/items/42?q=c%C3%A0%20ph%C3%AA&tag=C%2B%2B#info");

        System.out.println(uri.getScheme());
        System.out.println(uri.getAuthority());
        System.out.println(uri.getRawPath());
        System.out.println(uri.getRawQuery());
        System.out.println(uri.getQuery());
        System.out.println(uri.getFragment());

        String formValue = URLEncoder.encode(
            "cà phê + C++", StandardCharsets.UTF_8);
        System.out.println(formValue);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 UriBasics.java
java UriBasics
```

Stdout chính xác:

```text
https
api.example.com:8443
/items/42
q=c%C3%A0%20ph%C3%AA&tag=C%2B%2B
q=cà phê&tag=C++
info
c%C3%A0+ph%C3%AA+%2B+C%2B%2B
```

Giải thích:

- `getRawQuery()` trả phần query còn escape sequence; `getQuery()` trả dạng percent-decoded.
- `getRawPath()` giúp xem chuỗi path chưa percent-decode; `getPath()` trả path đã percent-decode. Sự khác biệt quan trọng nếu có `%2F`, `%2E` hoặc dữ liệu đòi hỏi kiểm tra an toàn.
- `URI` không phải HTTP client; tạo `URI` không đồng nghĩa gửi request.
- `URLEncoder` **không phải bộ mã hóa đường dẫn URI tổng quát**. Nó phục vụ nội dung form: dấu cách thành `+`; slash có thể bị mã hóa thành `%2F` kể cả khi bạn muốn nó đóng vai trò ngăn cách segment.
- `URLDecoder` cũng theo quy ước form; không áp nó lên toàn URI/path rồi coi kết quả là URI hợp lệ.

Khi cần ghép đường dẫn và query phức tạp trong ứng dụng Spring, ưu tiên builder theo từng thành phần thay vì `String.format()`/nối chuỗi/`URLEncoder` cho cả URI.

## 6. Tạo URI trong Spring Web với `UriComponentsBuilder`

`UriComponentsBuilder` thuộc `spring-web`, giúp ghép path/query và mã hóa theo ngữ cảnh.

Ví dụ Java trong project có dependency Spring Web (đây là đoạn sử dụng thư viện Spring, không biên dịch bằng JDK đơn thuần):

```java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

public class SpringUriExample {
    public static void main(String[] args) {
        URI uri = UriComponentsBuilder
            .fromUriString("https://api.example.com")
            .pathSegment("products", "{sku}")
            .queryParam("q", "{keyword}")
            .queryParam("tag", "{tag}")
            .encode()
            .buildAndExpand(Map.of(
                "sku", "cup/blue",
                "keyword", "cà phê & trà",
                "tag", "C++"))
            .toUri();

        System.out.println(uri);
    }
}
```

Kết quả URI mong đợi khi dùng quy tắc **strictly encode URI variables** của builder:

```text
https://api.example.com/products/cup%2Fblue?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0&tag=C%2B%2B
```

Ở đây `.pathSegment(...)` biểu thị các segment, `.queryParam(...)` biểu thị key/value. `{sku}`, `{keyword}` và `{tag}` là *URI template variables*. Gọi `.encode()` trên **builder trước khi expand** giúp mã hóa cả ký tự reserved trong biến, như `/`, `&`, `+`, khi chúng đóng vai trò dữ liệu. Việc tạo ra URI với `%2F` vẫn chưa bảo đảm phía server chấp nhận encoded slash như một path variable; đó là ràng buộc xử lý request riêng.

### Hai kiểu encode trong Spring không tương đương

| Phương thức | Cơ chế | Khi nào dùng |
|---|---|---|
| `UriComponentsBuilder.encode()` rồi expand biến | Encode template, sau đó **strict encode** giá trị biến, kể cả reserved có ý nghĩa cú pháp. | Mặc định nên chọn khi biến là dữ liệu opaque của người dùng. |
| `UriComponents.encode()` sau expand | Encode ký tự không hợp lệ trong từng component nhưng có thể giữ reserved hợp lệ trong component. | Khi bạn cố ý muốn reserved character của biến mang ngữ nghĩa bên trong component, và hiểu hệ quả. |

Đối với mã hóa path và query, không có **một** hàm encode chuỗi tùy ý dùng đúng cho mọi vị trí. Hãy giữ dấu phân tách do builder quản lý, đưa dữ liệu vào path segment hoặc query value, và chỉ mã hóa một lần.

## 7. Luồng request thực tế: client, server, Spring

```text
Giá trị người dùng: "cà phê & trà"
        |
        v
Client dựng URI theo component và UTF-8 percent-encoding
        |
        v
GET /search?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0 HTTP/1.1
        |
        v
Reverse proxy / HTTP server / servlet container xử lý request-target
        |
        v
Spring MVC chọn handler, bind @RequestParam q = "cà phê & trà"
        |
        v
Controller kiểm tra dữ liệu theo hợp đồng nghiệp vụ -> response
```

Đây là luồng khái niệm; các tầng có thể có quy tắc riêng đối với `%2F`, `%25`, chuỗi escape sai, dấu chấm kép, dấu chấm phẩy, ký tự điều khiển và path normalization. Vì vậy:

- **Không tự percent-decode lại** chuỗi `@RequestParam`/`@PathVariable` đã được framework bind nếu không có lý do chính xác. Decode thêm có thể làm biến đổi giá trị hoặc tạo lỗ hổng.
- Kiểm tra đầu vào **sau khi biết rõ API/framework trả dữ liệu dạng raw hay decoded**; không đoán bằng mắt nhìn request trên trình duyệt.
- Nếu proxy và ứng dụng diễn giải URI khác nhau, routing, authentication hoặc cache có thể bị bypass; cần test end-to-end cùng cấu hình triển khai thực tế.
- Percent-encoding là **cơ chế biểu diễn dữ liệu**, không có chức năng mã hóa bảo mật, xác thực, phân quyền hay chống SQL injection/XSS.

### Khi dùng log, chữ ký request và cache

URI có thể là một phần của cache key, canonical request hoặc chữ ký HMAC. Nếu những hệ thống liên quan chuẩn hóa khác nhau (thứ tự query, viết hoa/chữ thường hex, `%2F` vs `/`, double-encoding, thông số lặp), chữ ký hay cache có thể sai. Phải thống nhất **một quy tắc canonicalization được công bố rõ**, thay vì tự decode/re-encode một URI tùy ý. Những quy tắc cụ thể phụ thuộc giao thức/API.

## 8. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `"/search?q=" + keyword` với `keyword = "a&b"` | Dấu `&` có thể bị phân tích thành tham số mới. | Dùng builder `.queryParam("q", "{q}").encode()` và expand dữ liệu. |
| Dùng `URLEncoder` để mã hóa toàn URI | Dấu `:`, `/`, `?` trở thành dữ liệu; URI sai. | Tách scheme, path, query rồi encode đúng component. |
| Cho `C++` vào query nhưng quên encode dấu `+` | Bộ giải mã kiểu form có thể đọc thành `C  `. | Mã hóa cộng thật thành `%2B`. |
| Mã hóa chuỗi `%20` lần nữa | Thành `%2520`; server có thể nhận literal `%20` thay vì space. | Xác định dữ liệu đang raw hay đã encoded; một nguồn chịu trách nhiệm encode. |
| Decode toàn URI trước khi tách component | `%26`, `%2F`, `%3F` có thể trở thành delimiter. | Parse cấu trúc trước, decode theo component đúng một lần. |
| Coi `#fragment` là tham số server | Backend không nhận fragment qua HTTP request-target. | Nếu backend cần dữ liệu, gửi qua path/query/body có thiết kế rõ. |
| Tin rằng `%2F` luôn là ký tự bên trong path variable | Proxy/container có thể từ chối hoặc giải mã slash. | Dùng ID không chứa slash; kiểm thử route qua toàn bộ hạ tầng. |
| Ghép URL tùy ý từ input người dùng cho HTTP outbound | Có thể truy cập host không mong muốn (SSRF) hoặc redirect sai. | Kiểm tra scheme/host/port theo allowlist, chỉ ghép các component được phép. |

### Checklist khi phát triển một endpoint mới

1. Xác định rõ tài nguyên (path segment) và tùy chọn tìm/lọc (query); mô tả tham số lặp, rỗng, mặc định và kiểu dữ liệu.
2. Khi sinh URI, truyền dữ liệu vào **component đúng** qua builder; dùng UTF-8 và strict encoding cho template variables từ input.
3. Khi nhận request, kiểm tra giá trị đã bind trong Spring; validate format, kích thước, miền giá trị và quyền truy cập tài nguyên.
4. Thử với space, `+`, `&`, `#`, `%`, Unicode, dấu `/` trong ID, query lặp, query trống và input escape sai.
5. Kiểm tra trên cùng proxy/container và thiết lập routing của môi trường chạy thật, đặc biệt với encoded slash và normalization.

## 9. Câu hỏi tự kiểm tra

**1. `/items/12?lang=vi#section-2`: server nhận những phần nào?** HTTP request tới origin có path `/items/12` và query `lang=vi`; fragment `section-2` được client giữ và không chuyển trong request-target.

**2. Khi người dùng tìm kiếm `C++ & Java`, có thể nối nguyên văn vào `?q=...` không?** Không. Trong giá trị query kiểu key/value, cần encode `+` và `&` thành dữ liệu thay vì dấu cú pháp, ví dụ `q=C%2B%2B%20%26%20Java` theo percent-encoding.

**3. `/files/a%2Fb` có chắc tương đương một route variable là `a/b` không?** Không. Dù `%2F` biểu diễn slash ở mức byte, tầng proxy/container/framework có thể chặn hoặc diễn giải khác. Chọn ID phù hợp, và kiểm tra cấu hình thực tế.

**4. Nên dùng `URLEncoder` hay `UriComponentsBuilder` để tạo URL của Spring API?** Với URI nhiều thành phần, ưu tiên `UriComponentsBuilder` và mã hóa biến đúng vị trí. `URLEncoder` dùng cho dữ liệu theo quy ước `application/x-www-form-urlencoded`, nhất là form value; không mã hóa nguyên một URI.

## Nguồn tham khảo

- RFC 3986 — *Uniform Resource Identifier (URI): Generic Syntax*: https://www.rfc-editor.org/rfc/rfc3986
- Spring Framework Reference — *URI Links / URI Encoding*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
- Java SE — `java.net.URI` và `java.net.URLEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
