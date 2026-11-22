# UriComponentsBuilder: ghép đường dẫn, tham số và URI template trong Spring MVC

## 1. Bài toán: vì sao không nên nối URL bằng chuỗi?

Một ứng dụng Spring MVC thường cần dựng URI cho nhiều việc:

- Trả header `Location` khi `POST` tạo thành công resource mới.
- Sinh liên kết phân trang, tìm kiếm, lọc, sắp xếp và các tham số lặp.
- Điền `{id}`, `{slug}`, `{version}` vào URI template.
- Tạo liên kết phản ánh đúng scheme, host, port và context path khi ứng dụng đứng sau reverse proxy.
- Encode dữ liệu có tiếng Việt, dấu cách, dấu `+`, `&`, `/` hay `#` đúng ngữ cảnh.
- Di chuyển từ `/api/v1` sang `/api/v2` mà không lặp logic ghép URL ở hàng chục controller.

Nếu ghép chuỗi:

```java
// PHẢN VÍ DỤ: input chưa encode và có thể phá cấu trúc URI.
String url = "https://api.example.test/search?q=" + keyword
        + "&page=" + page;
```

với `keyword="C++ & Spring"`, kết quả chứa dấu `&` khiến query bị tách thành các tham số khác ngoài ý muốn. Với keyword chứa dấu `#`, phần sau dấu đó có thể bị hiểu thành URI fragment và không gửi đến server. Nếu dùng input bất kỳ để ghép path hoặc host, hậu quả còn nghiêm trọng hơn (path manipulation, open redirect, SSRF, nhầm authorization boundary).

Spring cung cấp `org.springframework.web.util.UriComponentsBuilder`: builder có cấu trúc, biết scheme, authority, path, path segments, query parameters, fragment và **URI template variables**. Thay vì nối trực tiếp, hãy mô hình hóa từng thành phần, chọn chiến lược encode nhất quán và chỉ mở quyền quyết định host/path cho input đáng tin cậy.

**Phạm vi:** Spring Framework Web 6.1.x, Spring MVC Servlet stack, Java 17 và Spring Boot 3.3.5. Bài này thuộc nhóm **URI và phiên bản API**. Các ví dụ trình bày API/syntax tương thích nhánh Spring 6.1; khác biệt của WebFlux hoặc Spring 7 cần được xem riêng.

### Mục tiêu học

1. Nắm cấu trúc URI, absolute/relative URI và ý nghĩa reserved characters.
2. Biết dùng `newInstance()`, `fromUriString()`, `fromPath()` và `fromUri()`.
3. Phân biệt `path()` và `pathSegment()`, append so với replace.
4. Dùng `queryParam()`, `queryParams()`, `replaceQueryParam()` và `queryParamIfPresent()`.
5. Nắm thời điểm dùng `encode()`, `build()`, `buildAndExpand()`, `toUri()` và `toUriString()`.
6. Dùng `ServletUriComponentsBuilder` cho header `Location` trong Spring MVC.
7. Tự kiểm thử bytes/percent-encoding, URI templates và bảo mật host/query inputs.

## 2. URI gồm những thành phần gì?

Xét URI minh họa:

```text
https://api.example.test:8443/api/v1/books/42?lang=vi&page=2#reviews
└─┬─┘ └────────┬────────┘└───────┬───────┘└───────┬─────┘└─┬───┘
scheme       authority           path             query     fragment
```

- **Scheme**: `https` xác định giao thức URI.
- **Authority**: host `api.example.test` và port `8443`. Trong một số URI còn có user-info, nhưng tuyệt đối không để credential trong URL.
- **Path**: chuỗi phân cấp `/api/v1/books/42`. Dấu `/` phân biệt segments.
- **Query**: `lang=vi&page=2`, có thể chứa nhiều values cùng một key.
- **Fragment**: `reviews`; trong HTTP thông thường fragment **không được gửi trong request target** tới server. Trình duyệt dùng fragment cho việc điều hướng phía client.

Một URI **absolute** có scheme (ví dụ `https://api.example.test/api/v1/books/42`); URI **relative reference** như `/api/v1/books/42` không có scheme/host và được resolve tương đối với base URI. Chọn dạng phù hợp contract: `Location` có thể là URI reference hợp lệ, còn link trong tài liệu API có thể cần absolute URL để client gọi trực tiếp.

**URI không nhất thiết là URL trên Internet.** URI có thể dùng scheme khác (ví dụ `mailto:`); ở đây tập trung HTTP/HTTPS và đường dẫn REST. Thư viện dựng URI không xác thực rằng endpoint thật tồn tại hoặc người dùng có quyền truy cập.

### Reserved và percent encoding

Một số ký tự có vai trò cấu trúc:

| Ký tự | Vai trò có thể có | Rủi ro nếu ghép dữ liệu thẳng |
| --- | --- | --- |
| `/` | Phân chia path segments | Một ID `a/b` bị hiểu thành hai segments |
| `?` | Bắt đầu query | Data có thể bị coi là query |
| `&` | Thường phân tách query parameters | Term tìm kiếm bị tách param |
| `=` | Thường phân tách tên và giá trị query | Query cấu trúc không như dự định |
| `#` | Bắt đầu fragment | Phần query/path sau `#` có thể không đến server |
| `+` | Hợp lệ trong query theo URI nhưng thường bị form decoder hiểu thành space | `C++` có thể biến thành `C  ` |
| `%` | Mở đầu percent-encoded octet | Dễ double encoding nếu encode nhiều lần |
| `;` | Reserved, có ý nghĩa ở một số path contexts | Biến template có thể thay đổi semantics |

**Percent encoding** biểu diễn bytes bằng `%HH`, ví dụ dấu cách → `%20`, `&` trong một query value được encode chặt → `%26`, và `+` → `%2B`. Với văn bản Unicode, đầu tiên encode UTF-8 rồi percent-encode các bytes tương ứng. Đừng dùng `URLEncoder` cho cả URL: API đó phục vụ `application/x-www-form-urlencoded` nên dấu cách thường thành `+`, không phải cách dựng toàn URI nhiều components.

## 3. UriComponentsBuilder là gì?

Class trung tâm là `org.springframework.web.util.UriComponentsBuilder`, tạo một builder **mutable**. Bạn khởi tạo, thay đổi từng component, sau đó build URI.

Các factory tiêu biểu:

```java
UriComponentsBuilder.newInstance();
UriComponentsBuilder.fromUriString("https://api.example.test");
UriComponentsBuilder.fromPath("/api/v1/books");
UriComponentsBuilder.fromUri(URI.create(
        "https://api.example.test/api/v1/books"));
```

Đây là **snippets** cần imports `org.springframework.web.util.UriComponentsBuilder` và `java.net.URI`. Builder có các methods:

```java
scheme("https")
host("api.example.test")
port(8443)
path("/api/v1/books")
pathSegment("api", "v1", "books", "{id}")
queryParam("lang", "vi")
replaceQueryParam("page", 2)
fragment("reviews")
encode()
build()
buildAndExpand(...)
toUriString()
```

Danh sách trên là **tên method gọi trên builder**, không phải một chương trình Java độc lập và không phải tất cả cùng gọi tuần tự trong một URL thực tế. `build()` trả `UriComponents`; `toUriString()` trả một chuỗi; `toUri()` của `UriComponents` trả `java.net.URI` để dùng với `ResponseEntity.location(...)`.

### Ví dụ cấu trúc thay vì nối chuỗi

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "v1", "books", "{id}")
        .queryParam("lang", "vi")
        .encode()
        .buildAndExpand(Map.of("id", 42L))
        .toUri();
```

Imports:

```java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;
```

URI kết quả:

```text
https://api.example.test/api/v1/books/42?lang=vi
```

`{id}` là placeholder; `buildAndExpand(Map.of("id",42))` điền giá trị trước khi sinh URI. Khi người viết muốn link cho các resources khác nhau, chỉ đổi dữ liệu, không đổi template literal.

**`Map.of(...)` cần Java 9+**, ví dụ bài dùng Java 17 nên hợp lệ.

## 4. path() và pathSegment(): khác biệt quan trọng nhất

### 4.1. path(): nối phần path đã mang cấu trúc

`path(String)` **append** chuỗi vào path hiện có. Nó không tự thêm dấu `/` giữa mọi lần gọi:

```java
String path = UriComponentsBuilder
        .fromPath("/api")
        .path("/v1")
        .path("/books")
        .build()
        .toUriString();
```

Kết quả:

```text
/api/v1/books
```

Nếu viết `.path("v1")` ngay sau `"/api"`, các chuỗi có thể nối thành `/apiv1`, khác với ý định. Vì vậy với những phần path rõ ràng, người viết phải chủ động giữ dấu `/`.

Spring có bước chuẩn hóa một số dấu slash lặp trong full path, nhưng không nên dựa vào đó để tự sửa URL sai cấu trúc từ nguồn không đáng tin.

### 4.2. pathSegment(): thêm từng segment có dấu phân cách

`pathSegment(String...)` append các segments và tự đưa dấu `/` phù hợp:

```java
String path = UriComponentsBuilder
        .newInstance()
        .pathSegment("api", "v1", "books", "42")
        .build()
        .toUriString();
```

Kết quả:

```text
/api/v1/books/42
```

Empty segments có thể được bỏ qua. Khi giá trị **thực sự là một segment duy nhất**, `pathSegment` mô hình hóa đúng mong muốn hơn `path`.

### 4.3. Dữ liệu chứa slash

Một identifier có nội dung `a/b` có thể mang nghĩa **một ID**, không phải hai cấp path. Dùng template variable được encode chặt:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "v1", "files", "{key}")
        .encode()
        .buildAndExpand(Map.of("key", "a/b"))
        .toUri();
```

Kết quả thường là:

```text
https://api.example.test/api/v1/files/a%2Fb
```

Dấu `/` trong **giá trị biến** được percent-encode thành `%2F`, không mở thêm một path segment. Trong các cấu hình HTTP thực, reverse proxy, Servlet container hoặc firewall có thể **từ chối/giải mã encoded slash** khác nhau; việc tạo URI chứa `%2F` không bảo đảm endpoint nhận ID `a/b` nguyên vẹn trong mọi hạ tầng. Nếu opaque ID thường chứa slash, cân nhắc mã định danh URL-safe hoặc đưa nó vào query/body theo contract.

Một `pathSegment("a/b")` tĩnh cũng có semantics encode dấu slash trong segment khi builder encode. **Không xem percent-encoding là input validation hay authorization**: path segments vẫn cần kiểm tra business rules và security.

### 4.4. replacePath() thay vì path()

`path("/v2")` **append** vào path đang có; `replacePath("/v2")` **thay toàn bộ path**.

```java
String replaced = UriComponentsBuilder
        .fromUriString("https://api.example.test/old/path")
        .replacePath("/api/v2/books")
        .build()
        .toUriString();
```

Kết quả:

```text
https://api.example.test/api/v2/books
```

Điều này đặc biệt hữu ích khi giữ host/scheme của một URI đáng tin nhưng cần điều hướng tới path đã xác định. Dù vậy, nếu URI gốc có query hoặc fragment không mong muốn, thay path **không tự xóa** query/fragment; hãy dùng `replaceQuery(null)` và `fragment(null)` khi cần một target sạch.

## 5. Query parameters: thêm, thay thế, xóa và giá trị lặp

### 5.1. queryParam() thêm tham số

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/api/v1/books")
        .queryParam("page", 2)
        .queryParam("size", 20)
        .queryParam("sort", "createdAt,desc")
        .encode()
        .build()
        .toUri();
```

URI dự kiến:

```text
https://api.example.test/api/v1/books?page=2&size=20&sort=createdAt,desc
```

Dấu phẩy là ký tự được phép trong một số query contexts; việc giữ nguyên hay percent-encode dấu reserved hợp lệ khác nhau theo lựa chọn encoding. Không hardcode raw text mong đợi cho mọi reserved character mà chưa xác định chiến lược. Phần số `page=2`/`size=20` có semantics rõ.

**Quan trọng:** `queryParam("page",2)` thêm một value. Nếu builder đã có `page=1`, thêm `page=2` có thể tạo **hai** params `page=1&page=2` thay vì override; dùng `replaceQueryParam()` để thay.

### 5.2. replaceQueryParam() và remove

```java
String result = UriComponentsBuilder
        .fromUriString("https://api.example.test/books?page=1&legacy=true")
        .replaceQueryParam("page", 3)
        .replaceQueryParam("legacy")
        .build()
        .toUriString();
```

Kết quả:

```text
https://api.example.test/books?page=3
```

- `replaceQueryParam("page",3)` thay các values cũ của cùng key.
- `replaceQueryParam("legacy")` với không value **xóa key đó**.
- `replaceQuery(String)` thay **toàn bộ query**, còn `replaceQuery(null)` xóa query; `query(String)` append/parse query text.
- `replaceQueryParams(MultiValueMap<String,String>)` có thể thay toàn bộ set query params.

### 5.3. Một tham số có nhiều giá trị

HTTP query có thể lặp key:

```text
?tag=java&tag=spring
```

Trong builder:

```java
List<String> tags = List.of("java", "spring");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/books")
        .queryParam("tag", tags)
        .encode()
        .build()
        .toUri();
```

Kết quả:

```text
https://api.example.test/books?tag=java&tag=spring
```

Đây là snippet với import `java.util.List` và `java.net.URI`. Overload `queryParam(String, Collection<?>)` giúp truyền nhiều values cùng tên. Khi Spring MVC controller nhận, có thể dùng `@RequestParam List<String> tag`, nhưng server cần có contract rõ với duplicate values và thứ tự nếu việc lọc phụ thuộc chúng.

### 5.4. queryParamIfPresent() cho Optional

```java
Optional<String> language = Optional.of("vi");

String uri = UriComponentsBuilder
        .fromPath("/api/v1/books")
        .queryParamIfPresent("lang", language)
        .build()
        .toUriString();
```

Kết quả:

```text
/api/v1/books?lang=vi
```

Nếu Optional rỗng, `lang` không được thêm. Có thể có null/empty semantics khác nhau giữa không có param, `?lang` và `?lang=`; chọn theo contract API, không tự coi chúng giống nhau. `queryParam("flag")` không có values tạo tham số có tên mà không có dấu bằng.

### 5.5. queryParams() với MultiValueMap

Khi có sẵn nhiều keys/values trong Java:

```java
MultiValueMap<String, String> params =
        new LinkedMultiValueMap<>();
params.add("tag", "java");
params.add("tag", "spring");
params.add("page", "2");

URI uri = UriComponentsBuilder
        .fromPath("/api/v1/books")
        .queryParams(params)
        .encode()
        .build()
        .toUri();
```

Imports:

```java
import java.net.URI;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.util.UriComponentsBuilder;
```

URI mô tả:

```text
/api/v1/books?tag=java&tag=spring&page=2
```

`MultiValueMap` khác `Map<String,String>`: một key có thể có nhiều values. Với API phân trang, nếu page/sort do server kiểm soát, đừng nhận và forward **mọi** user query params từ request cũ một cách tự động; lọc allowlist để tránh lặp token/filter không mong muốn.

## 6. URI template: đặt chỗ và expand dữ liệu

### 6.1. Template variables trong path

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/api/{version}/books/{id}")
        .encode()
        .buildAndExpand(Map.of(
                "version", "v1",
                "id", 42))
        .toUri();
```

Kết quả:

```text
https://api.example.test/api/v1/books/42
```

Trong `buildAndExpand(Map)`, tên biến phải khớp tên trong template. Thiếu biến có thể dẫn tới exception khi expand. `buildAndExpand(Object...)` còn có dạng positional: values được dùng theo thứ tự biến xuất hiện. Khi template có nhiều biến, **Map giúp tránh nhầm thứ tự**.

Một biến có thể xuất hiện nhiều lần:

```java
URI uri = UriComponentsBuilder
        .fromPath("/api/{version}/reports/{version}")
        .encode()
        .buildAndExpand(Map.of("version", "v2"))
        .toUri();
```

Kết quả:

```text
/api/v2/reports/v2
```

### 6.2. Template variables trong query

**Cách khuyến nghị cho dữ liệu người dùng có reserved characters:** đặt **giá trị query thành template variable**, bật `builder.encode()`, rồi expand. Ví dụ:

```java
String term = "C++ & Spring";

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/api/v1/books")
        .queryParam("q", "{q}")
        .queryParam("page", 2)
        .encode()
        .buildAndExpand(Map.of("q", term))
        .toUri();
```

Kết quả:

```text
https://api.example.test/api/v1/books?q=C%2B%2B%20%26%20Spring&page=2
```

Ở đây:
- `C++` → `C%2B%2B`.
- Space → `%20`.
- `&` nằm trong search term → `%26`, **không** phân tách thành query parameter.
- Dấu `&` giữa `q` và `page` vẫn được giữ nguyên là **dấu phân cách do template/builder tạo ra**.

### 6.3. Vì sao queryParam("q", term).encode() có thể khác?

Ví dụ:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/search")
        .queryParam("q", "C++")
        .encode()
        .build()
        .toUri();
```

Điều đáng chú ý là `+` **được phép trong URI query component** nên phương pháp encode thông thường của builder không nhất thiết thay dấu `+` literal bằng `%2B`. Trong nhiều server frameworks, query/form decoders có thể giải `+` thành space. Để tránh biến `C++` thành `C  `, hãy dùng template variable `"{q}"` và `builder.encode().buildAndExpand(...)` để strict-encode dữ liệu động.

**Không khẳng định `queryParam()` tự xử lý mọi dấu reserved như plain text**. Nó tổ chức components; chiến lược encoding quyết định bytes cuối. Đây là điểm quan trọng nhất khi gửi query người dùng, đặc biệt dấu `+`, `&`, `=`, `;`.

### 6.4. encode() trước build và encode() sau build

Spring có hai đường encoding:

1. `UriComponentsBuilder.encode()`: pre-encode **URI template** và **strictly encode URI variables khi expand**. Đặc biệt, các ký tự reserved mang ý nghĩa trong **giá trị biến** cũng được percent-encode.
2. `UriComponents.encode()`: encode **các components sau khi variables đã được expand**; nó chủ yếu encode ký tự không hợp lệ/non-ASCII nhưng có thể giữ reserved characters hợp lệ trong vị trí component.

Ví dụ ý tưởng:

```java
URI strict = UriComponentsBuilder
        .fromPath("/books/{key}")
        .encode()
        .buildAndExpand("a;b")
        .toUri();

URI componentOnly = UriComponentsBuilder
        .fromPath("/books/{key}")
        .buildAndExpand("a;b")
        .encode()
        .toUri();
```

Với đường encode chặt, dấu `;` trong biến có thể thành `%3B`; với component-level encoding, dấu `;` hợp lệ trong path có thể được giữ. Quy tắc này được tài liệu URI Encoding của Spring giải thích. **Ưu tiên builder-level encode khi values là dữ liệu opaque**; chọn component-level khi bạn có chủ đích cho reserved characters mang ý nghĩa cấu trúc.

### 6.5. Tránh double encoding

Nếu `id` đã là `"a%2Fb"` nhưng bạn coi đó là **raw data** rồi strict-encode, dấu `%` có thể thành `%25`, tạo `"a%252Fb"`. Khi client/server decode, có thể nhận giá trị khác với ý định.

Đặt một quy tắc rõ:
- Đối với user input bình thường, lưu **dữ liệu chưa percent-encode**, rồi encode đúng một lần lúc xây URI.
- Đối với URI **đã encode hoàn chỉnh**, dùng API dành cho encoded/raw components theo đúng contract, tránh encode lần hai.
- Không dùng việc decode-reencode tùy tiện với URL do người dùng đưa vào làm cơ chế bảo mật; có thể mở đường bypass nhiều lớp encoding.

## 7. build(), build(true), toUri() và toUriString()

### 7.1. Các bước thường gặp

```java
UriComponentsBuilder builder =
        UriComponentsBuilder.fromPath("/api/v1/books/{id}");

UriComponents components = builder
        .encode()
        .buildAndExpand(42);

URI uri = components.toUri();
String text = components.toUriString();
```

Imports:

```java
import java.net.URI;
import org.springframework.web.util.UriComponents;
import org.springframework.web.util.UriComponentsBuilder;
```

Cả `uri` và `text` đại diện URI `/api/v1/books/42`. Khi đưa URI vào `ResponseEntity.location(URI)`, dùng object `URI` thay vì tự ghép header `Location` bằng String.

`toUriString()` của builder có thể build/encode theo path nội bộ khác khi URI template variables đã/đang được khai báo; nên **chọn một pipeline rõ ràng và kiểm thử các ký tự khó** thay vì xen lẫn nhiều lần encode/build.

### 7.2. build(true) không phải chế độ bảo mật

`build(true)` báo với Spring rằng các components đã được encoded. Nó thích hợp khi builder được khởi tạo từ một URI đã ở dạng raw/encoded:

```java
URI original = URI.create(
        "https://api.example.test/search?q=C%2B%2B");

URI copied = UriComponentsBuilder
        .fromUri(original)
        .build(true)
        .toUri();
```

Kết quả logic vẫn là:

```text
https://api.example.test/search?q=C%2B%2B
```

**Cảnh báo từ Javadoc Spring 6.1:** `fromUri(URI)` nhận các components ở **fully encoded/raw form**. Nếu sửa builder này, các giá trị thêm cũng cần tuân thủ tình trạng encoded đó (ví dụ dùng `UriUtils` với component tương ứng). Đừng thêm string chưa encode vào builder raw rồi gọi `build(true)` hoặc lại encode toàn bộ lần nữa một cách mù quáng. Nếu muốn dựng URI **mới từ dữ liệu raw**, khởi tạo từ template đã biết rồi strict-encode variables thường dễ đúng hơn.

### 7.3. toUri() so với toASCIIString()

`URI.toString()` thể hiện URI dưới dạng Java String; `URI.toASCIIString()` có thể escape các ký tự non-ASCII khi cần ASCII representation. Khi tạo HTTP `Location`, Spring/HTTP layer sẽ sử dụng URI object và encoding phù hợp; đừng cố “decode để URI nhìn đẹp” trước khi gửi. Trong tests, `URI.getRawPath()` và `URI.getRawQuery()` có ích để khẳng định percent encoding; `getPath()`/`getQuery()` có thể giải mã, phù hợp cho kiểm tra logic nhưng không phát hiện double encoding bằng raw string một cách trực tiếp.

## 8. Fragment và query không nằm cùng tầng xử lý

Thêm fragment:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://docs.example.test/guide")
        .queryParam("lang", "vi")
        .fragment("examples")
        .encode()
        .build()
        .toUri();
```

URI:

```text
https://docs.example.test/guide?lang=vi#examples
```

Khi browser truy cập, phần `#examples` thường xử lý ở client, **không được gửi tới Spring MVC server** trong HTTP request target. Vì vậy không xây routing hoặc security dựa vào việc server nhận URL fragment. Server phải dùng path/query/headers/body để nhận các thông tin cần thiết.

Nếu fragment do client cung cấp và có thể chứa reserved characters, cũng cần encode/validate tương ứng. Fragment hữu ích cho deep links trong tài liệu/SPA, không dùng để gửi password/token an toàn: nó vẫn hiện trong browser history, logs phía client, extensions hoặc chia sẻ URL.

## 9. ServletUriComponentsBuilder: xây Location đúng context path

`UriComponentsBuilder` nhận base do code cung cấp; còn `org.springframework.web.servlet.support.ServletUriComponentsBuilder` có thể lấy scheme, host, port, path và query từ **HttpServletRequest** đang xử lý.

Các factory Spring MVC 6.1 đáng nhớ:

| Factory | Lấy thông tin nào? | Dùng khi |
| --- | --- | --- |
| `fromCurrentContextPath()` | Scheme, host, port, **context path** | Xây URI cho resource khác trong cùng application |
| `fromCurrentServletMapping()` | Context path và servlet mapping nếu có | App có DispatcherServlet mapping đặc thù |
| `fromCurrentRequestUri()` | Scheme, host, port, **request URI path**, không query | Thêm segment con của resource hiện tại |
| `fromCurrentRequest()` | Giống trên nhưng **bao gồm query string** | Muốn giữ query hiện tại và sửa/thêm param |
| `fromRequestUri(request)` | Từ HttpServletRequest, không query | Khi có request object tường minh |
| `fromContextPath(request)` | Từ request object, chỉ context root | Tạo link tuyệt đối khác endpoint |

Ví dụ tại request `POST https://example.test/app/api/v1/books?draft=true`:

- `fromCurrentContextPath()` bắt đầu từ `https://example.test/app`.
- `fromCurrentRequestUri()` bắt đầu từ `https://example.test/app/api/v1/books` (không giữ `draft=true`).
- `fromCurrentRequest()` còn có `?draft=true`; nếu append path `/{id}` mà không thay query, `draft` vẫn còn — có thể không đúng URI tài nguyên vừa tạo.

Vì vậy để xây `Location` cho resource mới, `fromCurrentContextPath().pathSegment("api","v1","books","{id}")` thường tường minh nhất, hoặc dùng `fromCurrentRequestUri().path("/{id}")` khi mapping phù hợp. **Không tự gắn raw `Host` header hay URL gốc do client cung cấp làm absolute redirect** mà thiếu trust boundary.

### Vì sao quan trọng với server.servlet.context-path?

Nếu ứng dụng chạy ở `/catalog` thay vì `/`, một URI hardcode `http://localhost:8080/api/v1/books/42` sẽ bỏ mất prefix `/catalog`. `ServletUriComponentsBuilder.fromCurrentContextPath()` lấy context path của request để tạo `http://localhost:8080/catalog/api/v1/books/42` khi ứng dụng nhận request đúng bối cảnh đó.

Trong môi trường gateway/reverse proxy, public path có thể lại là `/public-api`; khi đó cần cấu hình xử lý forwarded headers đúng, không chỉ context path nội bộ.

## 10. Ví dụ Maven Spring Boot 3.3.5 đầy đủ chạy được

Ứng dụng này cung cấp:

- `POST /api/v1/books`: tạo sách trong bộ nhớ, trả `201 Created` và `Location` trỏ tới sách.
- `GET /api/v1/books/{id}`: đọc sách vừa tạo.
- `GET /api/v1/links/search?q=...`: tạo URL search chứa template query value được encode chặt.
- `GET /api/v1/links/category?value=a/b`: một category ID chứa slash phải thành `a%2Fb` trong một path segment.
- `GET /api/v1/links/tags?tag=java&tag=spring`: tạo URI với duplicate query keys.
- `GET /api/v1/links/page`: thay query param hiện có bằng `replaceQueryParam`.

Data được giữ trong bộ nhớ; restart server làm mất dữ liệu. Không có database, Spring Security hoặc tích hợp reverse proxy; mục đích là kiểm chứng URI construction.

### 10.1. Cây dự án

```text
uri-builder-demo/
├── pom.xml
└── src/
    ├── main/java/demo/uri/
    │   ├── UriBuilderApplication.java
    │   └── BookController.java
    └── test/java/demo/uri/
        └── BookControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>uri-builder-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/uri/UriBuilderApplication.java`**

```java
package demo.uri;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UriBuilderApplication {
    public static void main(String[] args) {
        SpringApplication.run(UriBuilderApplication.class, args);
    }
}
```

### 10.2. Controller với URI templates, query params và Location

**`src/main/java/demo/uri/BookController.java`**

```java
package demo.uri;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/v1")
public class BookController {

    public record CreateBookRequest(String title) {}
    public record Book(long id, String title) {}
    public record LinkResponse(String url) {}

    private final AtomicLong ids = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    @PostMapping("/books")
    public ResponseEntity<Book> create(
            @RequestBody CreateBookRequest input) {

        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title is required");
        }

        Book book = new Book(
                ids.incrementAndGet(), input.title().strip());
        books.put(book.id(), book);

        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .pathSegment("api", "v1", "books", "{id}")
                .encode()
                .buildAndExpand(Map.of("id", book.id()))
                .toUri();

        return ResponseEntity.created(location).body(book);
    }

    @GetMapping("/books/{id}")
    public Book find(@PathVariable long id) {
        Book book = books.get(id);
        if (book == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return book;
    }

    @GetMapping("/links/search")
    public LinkResponse search(@RequestParam String q) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "books")
                .queryParam("q", "{q}")
                .queryParam("page", 2)
                .encode()
                .buildAndExpand(Map.of("q", q))
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/category")
    public LinkResponse category(@RequestParam String value) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "categories", "{category}")
                .encode()
                .buildAndExpand(Map.of("category", value))
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/tags")
    public LinkResponse tags(@RequestParam List<String> tag) {
        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("api", "v1", "books")
                .queryParam("tag", tag)
                .encode()
                .build()
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }

    @GetMapping("/links/page")
    public LinkResponse changePage() {
        URI uri = UriComponentsBuilder
                .fromUriString(
                        "https://api.example.test/books?page=1&legacy=true")
                .replaceQueryParam("page", 3)
                .replaceQueryParam("legacy")
                .build()
                .toUri();

        return new LinkResponse(uri.toASCIIString());
    }
}
```

**Các điểm cần hiểu:**

1. `@RestController` trả JSON; vì vậy `LinkResponse` là object có field `url`, không phải view name hoặc redirect.
2. `create()` ghi một `Book` trong `ConcurrentHashMap`; `AtomicLong` chỉ để sinh ID trong demo, không phải persistent ID strategy.
3. `ResponseEntity.created(location)` tạo HTTP `201 Created` + `Location`. Không cần tự nối string vào header và không dùng 302 cho contract tạo REST resource.
4. `ServletUriComponentsBuilder.fromCurrentContextPath()` lấy scheme/host/port/context path của request khi chạy trong Spring MVC, nên đúng hơn hardcode origin `localhost` ở endpoint tạo sách.
5. `search` sử dụng `queryParam("q","{q}")` và `encode()` **trước khi expand**, nên `C++ & Spring` được đưa vào **một query value** đúng.
6. `category` cho thấy `a/b` nằm trong một path segment như `a%2Fb`; ví dụ trả link string, không yêu cầu Servlet container phải nhận/route encoded-slash ở path để chạy demo.
7. `tags` minh họa query key lặp. Với nhiều values, `queryParam(String, Collection)` không phải tự gắn `tag=java,spring`.
8. `changePage` cho thấy `replaceQueryParam` thay `page` và xóa `legacy`. Không dùng `queryParam("page",3)` ở đây vì nó sẽ append duplicate.
9. Domain `api.example.test` được dùng cho links **minh họa, không phải endpoint Internet thực**. Client không nên cố fetch nó trong demo; app chạy ở localhost chỉ trả strings để kiểm thử.
10. Những URL động trong API hiện chỉ nhận input để tạo text, không fetch hay redirect tới host ngoài. Nếu đổi sang thực hiện HTTP call, phải thêm SSRF allowlist/network policy; encode đơn thuần không đủ.

### 10.3. Chạy và quan sát

Tại thư mục `uri-builder-demo` chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Đây là hai lệnh chạy **tuần tự**. Với cấu hình mặc định, ứng dụng lắng nghe trên `localhost:8080`.

**Tạo sách:**

```bash
curl -i -X POST 'http://localhost:8080/api/v1/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring Web"}'
```

Response đầu tiên khi server vừa khởi động và chưa có sách:

```http
HTTP/1.1 201
Location: http://localhost:8080/api/v1/books/1
Content-Type: application/json

{"id":1,"title":"Spring Web"}
```

`Location` có thể phản ánh origin/context path thực của HTTP request; nếu ở reverse proxy, public scheme/host phụ thuộc chính sách forwarded headers. Với server mới khởi động, ID đầu là 1; sau đó 2, 3... (không reset trong cùng JVM).

**Đọc sách vừa tạo:**

```bash
curl -i 'http://localhost:8080/api/v1/books/1'
```

Dự kiến body:

```json
{"id":1,"title":"Spring Web"}
```

**Tìm kiếm có reserved characters:**

```bash
curl -G -i 'http://localhost:8080/api/v1/links/search' \
  --data-urlencode 'q=C++ & Spring'
```

Body JSON dự kiến:

```json
{
  "url": "https://api.example.test/api/v1/books?q=C%2B%2B%20%26%20Spring&page=2"
}
```

`curl -G --data-urlencode` encode request gửi tới localhost, còn nội dung trả về là URI được server xây **lần nữa** cho host minh họa. Đừng cộng chuỗi URL query bằng cách viết `?q=C++ & Spring` ở client, vì dấu `+` và `&` sẽ bị hiểu sai.

**Path segment chứa slash:**

```bash
curl -G -i 'http://localhost:8080/api/v1/links/category' \
  --data-urlencode 'value=a/b'
```

Body:

```json
{
  "url": "https://api.example.test/api/v1/categories/a%2Fb"
}
```

**Tags lặp:**

```bash
curl -i 'http://localhost:8080/api/v1/links/tags?tag=java&tag=spring'
```

Body:

```json
{
  "url": "https://api.example.test/api/v1/books?tag=java&tag=spring"
}
```

**Replace query param:**

```bash
curl -i 'http://localhost:8080/api/v1/links/page'
```

Body:

```json
{
  "url": "https://api.example.test/books?page=3"
}
```

Output minh họa trình bày JSON đẹp để dễ đọc; Jackson có thể trả một dòng và không bảo đảm thứ tự fields trong các DTO lớn. Code demo ở đây có mỗi `url` nên dễ kiểm chứng.

### 10.4. Test bằng MockMvc

**`src/test/java/demo/uri/BookControllerTest.java`**

```java
package demo.uri;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void searchQueryEncodesPlusAmpersandAndSpaces() throws Exception {
        mvc.perform(get("/api/v1/links/search")
                    .param("q", "C++ & Spring"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/books"
                + "?q=C%2B%2B%20%26%20Spring&page=2"));
    }

    @Test
    void categoryIsExactlyOneEncodedPathSegment()
            throws Exception {
        mvc.perform(get("/api/v1/links/category")
                    .param("value", "a/b"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/categories/a%2Fb"));
    }

    @Test
    void repeatedQueryValuesRemainRepeated()
            throws Exception {
        mvc.perform(get("/api/v1/links/tags")
                    .param("tag", "java", "spring"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/api/v1/books"
                + "?tag=java&tag=spring"));
    }

    @Test
    void replaceQueryParamDoesNotAppendDuplicate()
            throws Exception {
        mvc.perform(get("/api/v1/links/page"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.url").value(
                "https://api.example.test/books?page=3"));
    }

    @Test
    void createdBookHasLocationPointingToGetResource()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/v1/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring Web\"}"))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.title").value("Spring Web"))
           .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI uri = URI.create(location);
        assertTrue(uri.getRawPath().matches(
                "/api/v1/books/[1-9][0-9]*"));

        mvc.perform(get(uri.getRawPath()))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Spring Web"));
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/v1/books/99999999"))
           .andExpect(status().isNotFound());
    }

    @Test
    void invalidTitleReturns400() throws Exception {
        mvc.perform(post("/api/v1/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }
}
```

Chạy:

```bash
mvn test
```

Class có **7 test methods**. Nếu toàn bộ pass, Maven exit code `0` với summary tương tự `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`. Tests xác minh percent encoding, repeated query, replace query và `Location`. Chúng dùng `MockMvc` và không có TCP server thật; không kiểm tra ngữ nghĩa forwarded headers khi qua CDN/reverse proxy.

**Điểm thiết kế test:** Test tạo sách không hardcode ID 1 vì trạng thái in-memory có thể thay đổi khi các tests được chạy theo thứ tự bất kỳ. Nó đọc `Location` thực, xác nhận path bắt đầu bằng `/api/v1/books/` với ID dạng số rồi gọi GET của path ấy. Như vậy test bảo vệ hợp đồng mà không phụ thuộc ordering.

## 11. MvcUriComponentsBuilder: liên kết dựa trên controller mappings

Khi một ứng dụng có nhiều controllers, viết string `"/api/v1/books/{id}"` ở nhiều nơi dễ bị lệch nếu refactor `@RequestMapping`. Spring còn có `MvcUriComponentsBuilder` để xây URI từ thông tin `@RequestMapping` của controller/method.

Ví dụ **snippet ý tưởng**:

```java
UriComponentsBuilder builder =
        MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "find", 42L);
URI uri = builder.build().toUri();
```

Đây **không phải code thêm vào project demo mà không cần test**: imports `MvcUriComponentsBuilder` và quy tắc mapping/request context phải phù hợp; name/parameters của method có thể bị thay khi refactor. Trong dự án có controller type-level mapping, phương án từ method/call có thể giúp giảm hardcode, nhưng vẫn phải kiểm tra context path, encode và forwarded headers. Tùy API của `MvcUriComponentsBuilder`, có thể dùng `fromMethodCall(on(...))` khi muốn link theo method proxy, chứ không chỉ theo method name.

**Không dùng `MvcUriComponentsBuilder` như một cách bỏ qua authorization**: nó chỉ giúp tạo link, không đảm bảo người được cung cấp link có quyền đọc resource.

## 12. UriComponentsBuilder và versioning API

URI của REST API có thể mang version ở path như `/api/v1/books` và `/api/v2/books`, hoặc qua header/media type theo policy khác. Khi dùng path versioning:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("api", "{version}", "books", "{id}")
        .encode()
        .buildAndExpand(Map.of("version", "v2", "id", 42))
        .toUri();
```

Kết quả:

```text
https://api.example.test/api/v2/books/42
```

Đừng lấy version/path prefix trực tiếp từ client rồi nối làm host hoặc redirect đích không qua validation. Hệ thống thường có tập version cố định, ví dụ `v1`/`v2`, cần giới hạn theo supported versions. Encoding không ngăn client chọn một version **không tồn tại**, không giới hạn data exposure và không tự chuyển đổi schema.

### Phân biệt base URL, API root và resource route

Một mẫu tách trách nhiệm:

- **Base origin**: `https://api.example.test`, do deployment config/trusted request metadata quyết định.
- **API root**: `/api/v1`, do routing policy/versioning định nghĩa.
- **Resource route**: `/books/{id}`, do controller định nghĩa.
- **Query**: `?include=author&lang=vi`, do contract và inputs đã validate quyết định.

Khi port/context path thay đổi giữa dev, staging, production, những phần này không nên bị nối lẫn trong business logic. Nhưng cũng không nên đưa base origin chưa validate vào `UriComponentsBuilder.fromUriString(input)` vì dễ tạo phishing/SSRF link.

## 13. Reverse proxy, forwarded headers và host-header security

Ứng dụng chạy phía sau load balancer:

```text
Client:
https://api.example.test/catalog/api/v1/books

Proxy forwards internally:
http://127.0.0.1:8080/app/api/v1/books
```

Nếu server lấy thẳng scheme/host/port từ request nội bộ, `Location` có thể thành:

```text
http://127.0.0.1:8080/app/api/v1/books/42
```

thay vì public URL mong muốn:

```text
https://api.example.test/catalog/api/v1/books/42
```

Spring có hỗ trợ `Forwarded` (RFC 7239), `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port` và `X-Forwarded-Prefix` để tái dựng URL gốc; với Servlet stack có `ForwardedHeaderFilter` và với Spring Boot có chính sách `server.forward-headers-strategy` (chọn theo topology/hosting).

**Điểm bảo mật cực kỳ quan trọng:** Những headers này **có thể bị client giả mạo**. Reverse proxy ở trust boundary phải **xóa các Forwarded/X-Forwarded-* headers không đáng tin** từ Internet rồi set giá trị chuẩn của chính proxy. Đừng bật blindly việc chấp nhận forwarded headers chỉ để URL ở Location trông đúng; nếu không kiểm soát, người dùng có thể làm server dựng liên kết/redirect tới host giả và tạo phishing hoặc web cache poisoning.

### Ví dụ cấu hình cần kiểm thử

Trong một deployment có proxy đáng tin và đã sanitize forwarded headers, Spring Boot có thể cấu hình:

```properties
server.forward-headers-strategy=framework
```

Đây là **cấu hình tùy chọn cho deployment**, không bắt buộc trong project runnable. Nó cho phép framework thực hiện xử lý forwarded headers thích hợp theo stack. Chỉ dùng sau khi xác minh ingress/proxy security policy và không cấu hình duplicate handling gây kết quả sai.

Khi không muốn tin forwarded headers nhưng muốn loại bỏ chúng, Spring `ForwardedHeaderFilter` có chế độ `removeOnly`. Cách triển khai thực tế khác nhau theo Servlet container, filter chain và chính sách host allowlist.

### Host header injection

Ngay cả khi không có forwarded headers, host từ HTTP request là dữ liệu chịu ảnh hưởng client/proxy. Nếu xây absolute `Location` hoặc email/reset link trực tiếp từ Host không validate, có thể tạo URL lừa đảo. Với callback/payment/email quan trọng, nên dùng **canonical public base URL từ cấu hình tin cậy** thay vì request host tùy ý, hoặc áp dụng allowlist host/scheme nghiêm ngặt.

## 14. URI builder không thay thế validation và encoding ở đích

### 14.1. SSRF

Nếu server nhận:

```text
?callback=http://169.254.169.254/latest/meta-data/
```

rồi dùng `UriComponentsBuilder.fromUriString(callback)` để tạo URI và gọi HTTP client tới đó, builder không chặn **SSRF**. Phải giới hạn scheme, host, port, DNS resolution, redirects, internal addresses và outbound network policy. Nếu chỉ dùng builder để format một URI và trả text, không có network request được thực hiện; nguy cơ xuất hiện khi server **sử dụng** URI để truy cập tài nguyên hoặc redirect.

### 14.2. Open redirect

```java
// PHẢN VÍ DỤ: không trả Location từ URI client tự chọn.
@GetMapping("/go")
public String go(@RequestParam String next) {
    return "redirect:" + next;
}
```

Đây là **đoạn code không an toàn**, trong `@Controller` nếu thiếu allowlist. Kẻ tấn công có thể dùng endpoint đáng tin để chuyển trình duyệt sang trang giả. Dùng server-controlled destination keys hoặc allowlist paths/hosts, canonicalization và origin policy. `UriComponentsBuilder.encode()` không làm một host độc hại trở thành host tin cậy.

### 14.3. Path traversal và encoded slash

Nếu ứng dụng xây URL từ tên tệp của user, encode dấu `/` có thể giúp giữ segment, nhưng dữ liệu `..`/`%2e%2e` và sự khác biệt double decoding giữa proxy/Servlet vẫn có thể khiến đường dẫn bị giải thích khác nhau. Không dùng URI path trực tiếp làm filesystem path; ánh xạ ID sang server-owned storage key và xác minh authorization.

### 14.4. Query parameter pollution

Nếu builder nhận cả query cũ và gọi `queryParam("role","viewer")`, client có thể có `role=admin&role=viewer`. Framework/server khác nhau có thể chọn first/last/list value. Khi override một tham số do server kiểm soát, dùng `replaceQueryParam()`, không append; tốt hơn là reconstruct query từ allowlist.

### 14.5. Dữ liệu nhạy cảm trong URI

Query strings có thể xuất hiện trong browser history, reverse proxy access logs, analytics, referrer ở những tình huống nhất định và screenshots. Không đưa password, bearer token, refresh token, session secret hoặc PII không cần thiết vào query chỉ vì `queryParam` encode được nó. Encode là **đảm bảo cú pháp**, không phải mã hóa bảo mật.

## 15. Những lỗi hay gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `/apiv1` thay vì `/api/v1` | `path("v1")` append không slash | Dùng `path("/v1")` hoặc `pathSegment` |
| Một ID `a/b` bị tách thành hai cấp | Coi identifier là raw path string | Dùng template variable + strict encoding hoặc URL-safe ID |
| `C++` bị đọc thành `C  ` | Dấu `+` để literal query, server form-decode thành space | Dùng `queryParam("q","{q}")`, `encode()` rồi expand |
| Input `A&B` tạo hai query params | Nối raw input vào `?q=...` | Builder + template variable strict encoding |
| `page` xuất hiện hai lần | `queryParam` append chứ không replace | `replaceQueryParam("page",value)` |
| URL vẫn giữ `legacy=true` | Chỉ replace path, chưa xóa query | `replaceQueryParam("legacy")` hoặc `replaceQuery(null)` |
| URI có `%252F` thay vì `%2F` | Encode một giá trị đã percent-encoded | Chuẩn hóa pipeline raw data → encode một lần |
| `buildAndExpand` báo thiếu variable | Tên `{id}` không có trong Map | So template và keys, dùng Map đầy đủ |
| Location thiếu context path | Hardcode `/api/v1` hoặc URL tuyệt đối sai | `ServletUriComponentsBuilder.fromCurrentContextPath()` |
| Location có `http://localhost:8080` ở production | Reverse proxy không truyền/xử lý origin metadata đúng | Config proxy, forwarded headers hoặc canonical base |
| Location trỏ host lạ | Tin `Host` hoặc `X-Forwarded-Host` client | Sanitize tại trusted proxy, allowlist/canonical base |
| Query xấu dù dùng encode | Builder.encode không strict-encode raw literal reserved ký tự | Đưa dynamic value vào URI template variable |
| URI không tới đúng controller | Encode slash đã tới nhưng Servlet/proxy từ chối | Kiểm tra path policy và dùng ID URL-safe |
| URI mất fragment ở server | Fragment không đi trong HTTP request | Không trông đợi `#...` trong Spring MVC |
| Link query chứa token lộ trong logs | Query không dành cho bí mật | Dùng header/body/session theo threat model |
| Link dùng đúng URI nhưng user không được phép | URI construction không làm authorization | Kiểm tra principal/resource/tenant |
| Test MockMvc pass, CDN URL sai | Forwarded headers/path rewrite khác runtime | Integration tests tại origin và public proxy |
| Builder dùng lại giữa requests gây query tích lũy | Builder mutable và dùng chung/singleton | Tạo builder mới theo request hoặc dùng `cloneBuilder()` |
| Xây URI từ raw URL không biết encode state | `fromUri(URI)` nhận raw encoded components | Dùng `build(true)` đúng contract hoặc xây từ template mới |

Một quy trình debug:

1. Log an toàn **URI template** và tên components, không log query chứa secret.
2. So `URI.getRawPath()` / `getRawQuery()` với `getPath()` / `getQuery()` để xác định encoding.
3. Kiểm tra dữ liệu đầu vào là **raw hay đã encoded**; tránh encode hai lần.
4. Xác nhận có dùng `pathSegment()` cho các identifiers cần giữ một segment.
5. Đối với query value có dấu `+`, `&`, `#`, kiểm tra strict variable encoding.
6. Nếu có duplicate keys, xem `queryParam` hay `replaceQueryParam`.
7. Với Location, kiểm tra context path, public host, scheme, forwarded headers tại trusted proxy.
8. Test URI trên cả HTTP client và Servlet container vì encoded slash/path normalization có thể khác.
9. Với link dùng cho redirect/fetch, kiểm tra SSRF/open redirect allowlist.
10. Khi thay đổi version API, test cả `v1`/`v2` và link consistency.

## 16. Checklist trước khi phát hành API có xây URI động

1. URI base/scheme/host được kiểm soát hoặc xác thực theo allowlist.
2. Path prefix và version nằm trong routing policy, không tự thêm tùy input client.
3. Identifiers được đưa vào `{variables}` hoặc `pathSegment`, không raw string nối tùy ý.
4. Query dynamic values dùng template variables với strict encoding khi có reserved characters.
5. Query do server kiểm soát dùng replace, không vô tình append duplicate.
6. Không chuyển dữ liệu đã encoded qua encode lần nữa; có rule rõ raw/encoded components.
7. Absolute `Location` hoặc redirect tôn trọng context path và trusted proxy deployment.
8. Tests xem raw percent-encoding của `+`, `&`, space, `/`, `%` và Unicode.
9. Link tạo ra không đồng nghĩa với cấp quyền truy cập tài nguyên.
10. Không đưa secrets vào URI path/query/fragment.
11. API phân biệt public versioned routes và personal data/cache behavior.
12. Forwarded headers và Host không được chấp nhận vô điều kiện từ client.
13. Không dùng builder mutable singleton làm state giữa requests.
14. Contract tests bao gồm cả request parameters lặp, optional, thiếu/blank và lỗi input.
15. Chỉ chuyển sang `MvcUriComponentsBuilder` khi cần refactor-safe mapping và kiểm chứng version/framework cụ thể.

## 17. Bài tập tự kiểm tra

1. `path("/api").path("v1")` có thể tạo lỗi đường dẫn nào? `pathSegment("api","v1")` khác gì?
2. `queryParam("page",2)` và `replaceQueryParam("page",2)` khác nhau thế nào khi query đã có `page=1`?
3. Một giá trị query `C++ & Spring` nên được đưa vào URI template và encode ra sao?
4. Vì sao builder-level `encode()` thường phù hợp hơn post-expansion `UriComponents.encode()` với URI variables là dữ liệu opaque?
5. `pathSegment("files","{id}")` với `id="a/b"` sẽ dùng encoding gì? Có chắc tất cả proxies đều chấp nhận encoded slash không?
6. `build(true)` có nghĩa gì? Khi nào `fromUri(URI)` cần đặc biệt cẩn thận?
7. `ServletUriComponentsBuilder.fromCurrentRequest()` khác `fromCurrentRequestUri()` ở thành phần nào?
8. Khi tạo REST resource, vì sao `201 Created` + `Location` thường thích hợp hơn response JSON chứa string URL tự ghép?
9. Nếu service chạy sau proxy, vì sao generated Location có thể là HTTP/localhost thay vì HTTPS public?
10. Vì sao không được tin `X-Forwarded-Host` từ Internet để tạo absolute URI?
11. `URI fragment` có được browser gửi trong HTTP request tới Spring MVC không?
12. UriComponentsBuilder có ngăn SSRF, open redirect hoặc path traversal nếu client kiểm soát host/path không?
13. Khi nào dùng `queryParamIfPresent`? Khi nào dùng `queryParams(MultiValueMap)`?
14. Vì sao `UriComponentsBuilder` tạo đúng URI chưa có nghĩa đường dẫn đã tồn tại hoặc user có quyền truy cập?
15. Khi đổi `/api/v1` sang `/api/v2`, bạn nên quản lý version ở tầng nào để link nhất quán?

**Gợi ý:** (1) Có thể `/apiv1`; pathSegment thêm phân tách. (2) Append có thể tạo duplicate, replace thay tất cả. (3) Template `{q}` + encode trước expand cho ra `C%2B%2B%20%26%20Spring`. (4) Strictly encode reserved trong dữ liệu thay vì để nó bị hiểu là cấu trúc. (5) `%2F` nhưng proxy/container vẫn có policy. (6) Đánh dấu components đã encoded; fromUri có raw components. (7) Factory có `Request` giữ query, `RequestUri` không. (8) HTTP Location là contract định vị resource; dễ follow. (9) Thiếu/không tin forwarded metadata và context mapping. (10) Giả host dẫn đến phishing. (11) Không. (12) Không; phải có allowlist/auth/validation. (13) Optional param và nhiều values lặp. (14) URI chỉ là một tham chiếu. (15) Routing/config/template/controller mapping theo chính sách rõ.

## 18. Tài liệu tham khảo

- [Spring Framework 6.1 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Spring Framework — URI Links and URI Encoding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Framework 6.1 — UriBuilder API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/util/UriBuilder.html)
- [Spring Framework 6.1 — UriComponents API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/util/UriComponents.html)
- [Spring Framework 6.1 — ServletUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html)
- [Spring Framework — Forwarded Headers Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Framework 6.1 — MvcUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)

**Tổng kết:** `UriComponentsBuilder` giúp dựng scheme, host, path, query và URI template **theo từng component**, tránh nối chuỗi dễ sai. `pathSegment` bảo toàn ý niệm một segment; `queryParam` thêm values còn `replaceQueryParam` thay/xóa; `builder.encode().buildAndExpand(...)` phù hợp để strict-encode biến dữ liệu, nhất là `+`, `&` và `/`. Trong Spring MVC, `ServletUriComponentsBuilder` có thể dựng header `Location` theo request/context path, nhưng proxy forwarded headers, host trust boundary, authorization và chính sách versioning vẫn cần được kiểm soát độc lập.
