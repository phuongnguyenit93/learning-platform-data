# Tạo URI bằng UriBuilder và mã hóa tham số đúng cách

## 1. Vì sao phải dùng URI builder?

Một ứng dụng Spring WebFlux thường tạo URL từ base URL, path, query parameter và giá trị do người dùng hoặc hệ thống cung cấp. Ví dụ:

~~~text
https://api.example.test/v1/search/C%2B%2B?tag=reactive%20webflux&page=2
~~~

Khi tạo URI cần giải quyết hai việc:

1. Ghép đúng scheme, host, port, path, query và fragment.
2. Mã hóa từng giá trị theo đúng URI component để dữ liệu không vô tình trở thành dấu phân cách.

Nếu nối chuỗi thủ công, giá trị `C++ & Java` có thể làm sai cấu trúc query vì `&` thường phân cách các query parameter. Một path value có dấu `/` có thể tạo thêm segment. Dấu `#` có thể bắt đầu fragment, khiến phần phía sau không được gửi tới server.

Spring cung cấp các API:

- **`UriBuilder`**: interface mô tả cách xây dựng URI.
- **`UriComponentsBuilder`**: implementation để ghép scheme, host, path, query, fragment và URI variables.
- **`UriBuilderFactory`**: factory tạo UriBuilder với cấu hình dùng chung.
- **`DefaultUriBuilderFactory`**: implementation mặc định, dựa trên UriComponentsBuilder và có thể cấu hình encoding mode.
- **`WebClient`**: HTTP client reactive, hỗ trợ URI template và UriBuilder.

**Nguyên tắc:** giữ template URI cố định trong code, truyền dữ liệu động dưới dạng URI variables và để builder mã hóa chúng theo đúng component. Không nối input vào URL hoàn chỉnh rồi hy vọng parser tự hiểu ý định.

## 2. Cấu trúc URI theo RFC 3986

Một URI tổng quát có cấu trúc:

~~~text
scheme://userinfo@host:port/path?query#fragment
~~~

Ví dụ:

~~~text
https://alice@example.test:8443/v1/orders/42?status=PAID&page=2#details
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scheme | `https` | Giao thức |
| User info | `alice` | Thông tin user trong authority; hiếm khi nên đưa credentials vào URL |
| Host | `example.test` | Máy chủ đích |
| Port | `8443` | Cổng kết nối |
| Path | `/v1/orders/42` | Đường dẫn tài nguyên |
| Query | `status=PAID&page=2` | Tham số truy vấn |
| Fragment | `details` | Vị trí trong tài nguyên phía client; không gửi trong HTTP request |

Không phải URI nào cũng có đủ mọi thành phần. URI tương đối có thể chỉ chứa path và query, ví dụ `/orders/42?expand=items`.

### 2.1. Unreserved và reserved characters

RFC 3986 chia các ký tự quan trọng thành hai nhóm.

**Unreserved** gồm chữ cái, chữ số và:

~~~text
- . _ ~
~~~

**Reserved** gồm:

~~~text
:/?#[]@!$&'()*+,;=
~~~

Các ký tự reserved có thể đóng vai trò dấu phân cách hoặc mang ý nghĩa riêng trong URI:

- `/` phân cách path segment.
- `?` bắt đầu query.
- `#` bắt đầu fragment.
- `&` thường phân cách query parameter.
- `=` thường phân cách tên và giá trị query.
- `;` có thể phân cách subcomponent trong một số URI.
- `+` là ký tự reserved thuộc nhóm sub-delimiters.

Reserved character không phải lúc nào cũng phải mã hóa. Nếu nó đang đóng vai trò dấu phân cách trong template, giữ nguyên. Nếu cùng ký tự đó là **dữ liệu của một biến**, mã hóa để nó không thay đổi cấu trúc URI.

Ví dụ, dấu `&` trong template query là dấu phân cách:

~~~text
/search?q={term}&page={page}
~~~

Nhưng nếu `term` có giá trị `java & reactor`, dấu `&` bên trong dữ liệu phải thành `%26`.

### 2.2. Percent-encoding

Percent-encoding biểu diễn một octet bằng ba ký tự:

~~~text
%HH
~~~

`HH` là hai chữ số hexadecimal của byte. Ví dụ:

| Dữ liệu | Percent-encoding |
| --- | --- |
| Space | `%20` |
| `&` | `%26` |
| `+` | `%2B` |
| `/` trong một path variable opaque | `%2F` |
| `#` trong dữ liệu | `%23` |
| `%` literal | `%25` |

Ký tự ngoài ASCII thường được mã hóa từ **các byte UTF-8**, không phải từ code point Unicode thành một số hex duy nhất. Ví dụ `é` có UTF-8 bytes `C3 A9`, nên biểu diễn là `%C3%A9`.

### 2.3. Encoding không phải encryption

Percent-encoding chỉ là cách biểu diễn dữ liệu trong URI. Nó không che password, token hay thông tin cá nhân. URL có thể xuất hiện trong browser history, proxy log, access log, tracing và cache key. Không đặt credentials hoặc dữ liệu nhạy cảm vào query/path chỉ vì chúng đã được percent-encode.

## 3. Mã hóa theo từng URI component

Một ký tự có thể hợp lệ trong component này nhưng là dấu phân cách trong component khác.

~~~text
Path:  /files/a%2Fb.txt
Query: ?q=C%2B%2B%20Java%26Spring
~~~

| Dữ liệu cần truyền | Vị trí | Cách biểu diễn |
| --- | --- | --- |
| `report 2026.pdf` | Một path segment | `report%202026.pdf` |
| `folder/a.txt` | Một path variable opaque | `folder%2Fa.txt` nếu cần giữ như một segment |
| `C++ & Java` | Query value | `C%2B%2B%20%26%20Java` |
| `a=b` | Query value | `a%3Db` nếu dấu `=` là dữ liệu |
| `x#section` | Query value | `x%23section` |
| `100%` | Query value | `100%25` |

Không dùng `URLEncoder` để encode toàn bộ URI. `URLEncoder` được thiết kế cho `application/x-www-form-urlencoded`, thường dùng cho form data. Nó biểu diễn space bằng `+`, trong khi URI percent-encoding thông thường dùng `%20`. Áp dụng nó lên toàn URL còn có thể biến các dấu cấu trúc `/`, `?`, `&` thành dữ liệu và làm hỏng URI.

## 4. Phân biệt path, pathSegment và queryParam

### 4.1. path và pathSegment

`path(String)` nối một đoạn path. Nó phù hợp với template path do ứng dụng kiểm soát:

~~~java
builder.path("/v1/orders/{orderId}");
~~~

`pathSegment(String...)` thêm từng segment riêng:

~~~java
builder.pathSegment("v1", "files", "{fileName}");
~~~

Nếu giá trị động có slash, `pathSegment` giúp thể hiện rằng giá trị đó thuộc một segment. Với encoding nghiêm ngặt, slash trong variable có thể được mã hóa thành `%2F`.

Không làm thế này:

~~~java
String url = "/files/" + userSuppliedName;
URI uri = URI.create(url);
~~~

Nếu `userSuppliedName` là `a/b.txt?download=true`, input có thể làm thay đổi path hoặc query structure.

Nên dùng:

~~~java
URI uri = UriComponentsBuilder.fromPath("/files/{name}")
        .encode()
        .buildAndExpand(userSuppliedName)
        .toUri();
~~~

Hoặc:

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://api.example.test")
        .pathSegment("files", "{name}")
        .encode()
        .buildAndExpand(userSuppliedName)
        .toUri();
~~~

**Lưu ý encoded slash:** proxy, gateway và server có thể decode `%2F` trước khi route. Nếu identifier thực sự cần chứa slash, hãy test toàn bộ đường đi HTTP; có thể chọn ID dạng Base64URL hoặc query parameter để tránh phụ thuộc cách hạ tầng xử lý.

### 4.2. queryParam và queryParams

`queryParam(name, value...)` thêm một hoặc nhiều giá trị cho query key:

~~~java
builder.queryParam("page", "{page}")
       .queryParam("tag", "{tag1}", "{tag2}");
~~~

Kết quả có dạng:

~~~text
?page=2&tag=spring&tag=reactive
~~~

Các giá trị cùng tên có thể lặp lại. API đích phải hiểu đúng semantics nhiều giá trị.

Các API liên quan:

- `queryParam(name, values...)`: thêm giá trị.
- `queryParamIfPresent(name, Optional)`: chỉ thêm khi Optional có giá trị.
- `replaceQueryParam(name, values...)`: thay giá trị hiện có của key.
- `queryParams(MultiValueMap)`: thêm query parameter từ map nhiều giá trị.

Không ghép query string thủ công:

~~~java
String query = "?q=" + term + "&page=" + page;
~~~

Dùng builder để giữ rõ key/value và áp dụng encoding đúng vị trí.

### 4.3. fragment

`fragment(value)` tạo phần fragment:

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://example.test/docs")
        .fragment("install")
        .build()
        .toUri();
~~~

URI hiển thị là `https://example.test/docs#install`. Fragment không được gửi trong HTTP request; nó chủ yếu phục vụ xử lý phía client hoặc tham chiếu vị trí trong tài liệu.

## 5. UriComponentsBuilder: xây URI từ template

Ví dụ cơ bản:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand("Westin", "123")
        .toUri();
~~~

Quy trình:

1. `fromUriString` tạo builder từ URI template.
2. `queryParam` thêm query component và placeholder.
3. `encode()` yêu cầu mã hóa template trước, rồi mã hóa chặt URI variables khi expand.
4. `buildAndExpand` thay placeholder bằng giá trị thực.
5. `toUri()` tạo `java.net.URI`.

Có thể dùng map để tên biến rõ ràng hơn:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand(Map.of(
                "hotel", "Westin",
                "q", "foo+bar"))
        .toUri();
~~~

Đoạn này cần import `java.util.Map`. Spring cũng cho phép rút gọn bằng `build(...)`:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://example.com/hotels/{hotel}")
        .queryParam("q", "{q}")
        .build("Westin", "123");
~~~

Nếu muốn encoding policy hiển thị rõ trong code review, chuỗi `encode().buildAndExpand(...).toUri()` dễ quan sát hơn.

### 5.1. Không trộn dữ liệu với template

Template là cấu trúc do ứng dụng kiểm soát:

~~~text
https://api.example.test/v1/customers/{customerId}/orders
~~~

Giá trị động:

~~~text
customerId = "A/B?C"
~~~

Giữ template và value riêng giúp builder hiểu `/`, `?` trong template là cú pháp; còn `/`, `?` trong value là dữ liệu cần encode.

Không tạo template bằng cách chèn input chưa tin cậy vào chuỗi:

~~~java
// Không nên: input đã trở thành một phần của template.
String template = "/search/" + userInput + "?page={page}";
~~~

Thay vào đó:

~~~java
URI uri = UriComponentsBuilder.fromPath("/search/{term}")
        .queryParam("page", "{page}")
        .encode()
        .buildAndExpand(userInput, page)
        .toUri();
~~~

## 6. Hai cách encode của UriComponentsBuilder và UriComponents

Đây là khác biệt quan trọng nhất khi làm việc với URI variables.

1. **`UriComponentsBuilder.encode()`**: mã hóa template trước, sau đó mã hóa nghiêm ngặt URI variables khi expand.
2. **`UriComponents.encode()`**: expand variables trước, rồi mã hóa từng component theo các ký tự bị cấm trong component đó.

### 6.1. Builder encode trước khi expand

~~~java
URI strict = UriComponentsBuilder.fromPath("/codes/{value}")
        .encode()
        .buildAndExpand("A;B")
        .toUri();
~~~

Kết quả:

~~~text
/codes/A%3BB
~~~

`;` là dữ liệu của biến `value`, nên bị mã hóa thành `%3B`. Cách này xem URI variables như **opaque data**: giá trị không được phép thay đổi cấu trúc URI.

Đây là lựa chọn phù hợp cho hầu hết trường hợp truyền ID, tên tìm kiếm, mã khách hàng, chuỗi filter hoặc dữ liệu người dùng.

### 6.2. Encode component sau khi expand

~~~java
URI componentEncoded = UriComponentsBuilder.fromPath("/codes/{value}")
        .buildAndExpand("A;B")
        .encode()
        .toUri();
~~~

Kết quả:

~~~text
/codes/A;B
~~~

Dấu `;` là ký tự hợp lệ trong path component và được giữ lại. Cách này hữu ích khi URI variable cố ý chứa reserved character với ý nghĩa cấu trúc của component.

| Giá trị variable trong path | Builder encode trước expand | Component encode sau expand |
| --- | --- | --- |
| `A B` | `A%20B` | `A%20B` |
| `A;B` | `A%3BB` | `A;B` |
| `A/B` | `A%2FB` | `A/B` nếu slash thuộc path syntax sau expand |
| `A?B` | `A%3FB` | `A%3FB` vì `?` không hợp lệ như dữ liệu path segment |
| `A#B` | `A%23B` | `A%23B` |

Với `A/B`, khác biệt đặc biệt quan trọng: sau khi expand, slash có thể trở thành dấu phân cách segment. Nếu variable phải là giá trị opaque, dùng builder `encode()` trước expand hoặc `pathSegment(...)`.

**Khuyến nghị:** mặc định dùng `UriComponentsBuilder.encode()` trước khi expand. Chỉ encode sau expand khi hợp đồng URI thực sự cần giữ reserved character trong component và đã test cách server parse.

## 7. DefaultUriBuilderFactory và EncodingMode

`DefaultUriBuilderFactory` cung cấp một nơi cấu hình base URL và chiến lược encoding dùng chung. Nó được dùng bởi `WebClient` và các HTTP client Spring khác thông qua `UriBuilderFactory`.

Bốn mode chính:

| EncodingMode | Cách hoạt động | Khi cân nhắc |
| --- | --- | --- |
| `TEMPLATE_AND_VALUES` | Encode template trước và encode chặt variables khi expand | Phù hợp phần lớn giá trị động |
| `VALUES_ONLY` | Không encode template; encode chặt URI variables trước khi expand | Template đã được kiểm soát/định dạng đặc biệt |
| `URI_COMPONENT` | Expand trước, encode từng component sau | Khi reserved character trong variable cần được giữ nếu hợp lệ |
| `NONE` | Không tự encode | Chỉ dùng khi caller đã tạo URI đúng dạng encoded |

Trong Spring Framework 7.0.8, `WebClient` dùng mặc định `TEMPLATE_AND_VALUES` thông qua `DefaultUriBuilderFactory`. Nếu ứng dụng dùng nhiều client, phiên bản Spring khác nhau hoặc cần contract rõ ràng, nên cấu hình mode tường minh.

Ví dụ:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

URI uri = factory.uriString("/search/{term}")
        .queryParam("q", "{q}")
        .build("C++ & Java", "reactive webflux");
~~~

Factory giữ base URL và encoding preferences. Khi có nhiều service gọi cùng một API, có thể chia sẻ factory hoặc dùng nó để cấu hình WebClient chung.

**Không chọn `NONE` chỉ để tránh `%25` hoặc `%2F`.** Nếu output sai, kiểm tra xem input có bị encode trước hay không, component nào đang được xây và encoding mode nào đang được áp dụng.

## 8. WebClient: truyền URI variables đúng cách

`WebClient` hỗ trợ nhiều cách cung cấp URI:

- Chuỗi URI template cùng các biến.
- Một `URI` đã được tạo sẵn.
- Một hàm nhận `UriBuilder` và trả `URI`.

Cách dùng template:

~~~java
Mono<ProductPage> response = webClient.get()
        .uri("/products/{category}?page={page}",
                category, page)
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Cách dùng UriBuilder function:

~~~java
Mono<ProductPage> response = webClient.get()
        .uri(builder -> builder
                .path("/products/{category}")
                .queryParam("q", "{q}")
                .queryParam("page", "{page}")
                .build(category, searchTerm, page))
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Cách thứ hai tiện khi có nhiều query parameter, optional parameter hoặc cấu trúc URI cần điều kiện.

Cấu hình encoding factory:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient webClient = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

Sử dụng:

~~~java
Mono<String> result = webClient.get()
        .uri(builder -> builder
                .path("/search/{term}")
                .queryParam("page", "{page}")
                .build(searchTerm, page))
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là các đoạn minh họa trong service; cần khai báo `webClient`, kiểu response, giá trị input và dependency Spring WebFlux. `WebClient` được thiết kế non-blocking và dùng Reactor để compose request/response; việc tạo URI đúng không yêu cầu gọi `block()`.

Nếu đưa một `java.net.URI` đã được xây dựng vào API client, caller phải bảo đảm URI đã có encoding đúng. Không encode lại URI hoàn chỉnh nếu các `%HH` đã là octet escapes hợp lệ.

## 9. Query parameter: dấu cộng, khoảng trắng và URLEncoder

### 9.1. Dấu `+` không phải cách biểu diễn URI space phổ quát

Trong generic URI syntax, `+` là một reserved sub-delimiter. Trong một số cách giải mã query theo `application/x-www-form-urlencoded`, dấu `+` được hiểu là khoảng trắng.

Vì vậy:

- Dữ liệu literal `C++` nên được biểu diễn là `C%2B%2B` khi builder strict-encode variable.
- Khoảng trắng trong URI component thông thường được biểu diễn là `%20`.
- Form encoding có thể biểu diễn khoảng trắng bằng `+`.

Không giả định mọi server, framework hoặc decoder đều xử lý `+` giống nhau. Khi dấu cộng là dữ liệu, mã hóa thành `%2B` sẽ tránh việc form decoder biến nó thành space.

### 9.2. URLEncoder dành cho form encoding

Ví dụ Java:

~~~java
String encoded = URLEncoder.encode(
        "C++ & Java",
        StandardCharsets.UTF_8);
~~~

Kết quả:

~~~text
C%2B%2B+%26+Java
~~~

Dấu `+` trong output này đại diện cho khoảng trắng theo form encoding. Nó không phải cách encode một URI path segment và cũng không phải phép encode cả URL.

Dùng `URLEncoder` khi bạn thực sự cần giá trị theo contract `application/x-www-form-urlencoded`. Với URI builder của Spring, hãy dùng `queryParam` và URI variables.

### 9.3. Query value có dấu `&`, `=`, `#`

Giả sử tìm kiếm bằng chuỗi:

~~~text
C++ & Spring=WebFlux #1
~~~

Nếu nối thủ công:

~~~text
/search?q=C++ & Spring=WebFlux #1
~~~

URL có thể bị phân tích sai:

- `&` có thể mở query parameter tiếp theo.
- `#` bắt đầu fragment; phần sau không được gửi đến server.
- `=` có thể được hiểu là dấu phân cách key/value.
- `+` có thể bị form decoder hiểu thành space.

Dùng builder:

~~~java
URI uri = UriComponentsBuilder.fromPath("/search")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand("C++ & Spring=WebFlux #1")
        .toUri();
~~~

Query value được mã hóa để các ký tự đó vẫn là dữ liệu của một parameter.

## 10. Nhiều query values, Optional và query parameter rỗng

### 10.1. Nhiều giá trị cùng key

~~~java
URI uri = UriComponentsBuilder.fromUriString("https://api.example.test/products")
        .queryParam("tag", "{first}", "{second}")
        .encode()
        .buildAndExpand("spring", "reactive")
        .toUri();
~~~

Kết quả có dạng:

~~~text
https://api.example.test/products?tag=spring&tag=reactive
~~~

Đây là query lặp key. API đích có thể diễn giải thành danh sách hai giá trị. Nếu contract yêu cầu comma-separated hoặc JSON, hãy encode theo contract đó thay vì tự thay đổi cấu trúc.

### 10.2. Optional parameter

Khi query parameter chỉ nên có nếu Optional chứa giá trị, có thể dùng `queryParamIfPresent`:

~~~java
Optional<String> status = Optional.of("PAID");

URI uri = UriComponentsBuilder.fromUriString("https://api.example.test/orders")
        .queryParamIfPresent("status", status)
        .build()
        .toUri();
~~~

Nếu Optional rỗng, `status` không được thêm. Phân biệt ba trường hợp:

| Cách tạo | Ý nghĩa |
| --- | --- |
| Không thêm key | Parameter không được gửi |
| `queryParam("q", "")` | Có key `q` với value rỗng |
| Placeholder `{q}` với null | Cần xác định semantics null theo API và builder; tránh để null thành hành vi ngầm |

Hãy định nghĩa rõ contract cho absent, empty và null; chúng không phải lúc nào cũng tương đương.

### 10.3. Thứ tự và chữ ký request

Thông thường server không nên phụ thuộc thứ tự query parameter. Tuy nhiên, một số API ký request hoặc hệ thống cache có thể canonicalize query theo quy tắc cụ thể.

Nếu request có chữ ký:

- Tuân thủ chính xác quy tắc canonicalization của provider.
- Xác định thứ tự key, repeated key, percent-encoding hex case và cách xử lý space.
- Không normalize hoặc decode/encode lại URI sau khi ký.
- Dùng cùng một thuật toán tạo canonical URI và gửi request thực tế.

Một URI tương đương về mặt tài nguyên vẫn có thể có chuỗi byte khác và làm chữ ký HMAC thất bại.

## 11. Double encoding: vì sao `%2F` biến thành `%252F`?

Giả sử dữ liệu gốc thực sự là:

~~~text
a/b
~~~

Nếu builder strict-encode một URI variable, slash được mã hóa thành `%2F`. Đây là kết quả mong muốn khi slash thuộc dữ liệu.

Nhưng nếu bạn truyền chuỗi **đã encode** `a%2Fb` vào builder như một value raw, ký tự `%` cũng là dữ liệu và được encode thành `%25`:

~~~text
a%252Fb
~~~

Khi decode một lần, nó trở thành chuỗi `a%2Fb`, chưa phải `a/b`. Đây là **double encoding**.

Quy tắc:

1. Giữ dữ liệu gốc chưa encode trong biến.
2. Gọi builder một lần để tạo URI encoded.
3. Không gọi URLEncoder hoặc UriUtils encode trước khi đưa value vào builder.
4. Không decode rồi encode lặp lại trong interceptor/filter nếu không có contract rõ.
5. Nếu input là URI đã encoded hoàn chỉnh, xử lý nó như URI cần parse/validate, không coi toàn bộ chuỗi là một raw variable.

Không sửa double encoding bằng cách đổi mode thành `NONE` mà chưa xác định component và nguồn của dữ liệu. Làm vậy có thể mở lỗi injection vào cấu trúc URI.

## 12. Unicode và charset

URI truyền dữ liệu dưới dạng octet, nên cần thống nhất character encoding. Spring URI builders dùng UTF-8 mặc định trong các ví dụ thông thường; có thể chỉ định charset qua overload encoding phù hợp.

~~~java
URI uri = UriComponentsBuilder.fromPath("/search/{term}")
        .queryParam("q", "{q}")
        .encode(StandardCharsets.UTF_8)
        .buildAndExpand("Hồ Chí Minh", "cà phê sữa")
        .toUri();
~~~

Các ký tự tiếng Việt được chuyển thành UTF-8 bytes rồi percent-encode. Không tự thay một ký tự tiếng Việt bằng một ký tự ASCII gần giống; đó là thay đổi dữ liệu chứ không phải encoding.

Một số lưu ý:

- Chuẩn hóa Unicode (NFC/NFD) có thể làm chuỗi nhìn giống nhau nhưng byte khác nhau; nếu ID hoặc chữ ký phụ thuộc byte, cần thống nhất normalization.
- Không decode URI trước khi parser tách các component.
- Không giả định một `%HH` tương ứng trực tiếp một Unicode character; UTF-8 code point có thể gồm nhiều byte.
- Khi hiển thị URI cho người dùng, có thể decode để dễ đọc ở UI; khi gửi HTTP, giữ dạng URI hợp lệ và encoded.

## 13. Đọc URI đã có sẵn và parser type

`UriComponentsBuilder` hỗ trợ parser theo RFC và parser theo WHATWG URL Standard. RFC parser yêu cầu input theo cú pháp RFC 3986 và xử lý nghiêm hơn; WHATWG parser linh hoạt hơn với một số URL không chuẩn mà browser thường chấp nhận.

Trong Spring Framework 7.0.8, `WebClient`, `RestClient` và `RestTemplate` mặc định dùng RFC parser. Có thể tùy chỉnh `UriBuilderFactory` nếu ứng dụng có lý do cụ thể để dùng parser khác.

Nếu parse URI do người dùng cung cấp:

1. Parse thành cấu trúc URI.
2. Kiểm tra scheme được phép, thường là `https` hoặc một tập scheme rất nhỏ.
3. Kiểm tra host, port và path theo policy.
4. Không tin rằng parse thành công có nghĩa URL an toàn.
5. Khi gửi request từ server, kiểm tra đích mạng và redirect theo chính sách SSRF.

Không chấp nhận một URL đầy đủ do user kiểm soát rồi chỉ gọi `UriComponentsBuilder.fromUriString(...)` và gửi đi. Parser giúp đọc cấu trúc, **không quyết định ứng dụng được phép kết nối tới host nào**.

## 14. Bảo mật: encoding không thay thế validation và SSRF protection

### 14.1. SSRF khi host do client kiểm soát

Một tính năng như webhook, import ảnh hoặc fetch URL có thể cho client nhập URL. Nếu server gọi URL đó, attacker có thể thử truy cập dịch vụ nội bộ, localhost, metadata endpoint hoặc địa chỉ private.

**Percent-encoding không ngăn SSRF.** Builder có thể tạo một URI cú pháp hoàn toàn hợp lệ nhưng host vẫn là đích không được phép.

Nếu nghiệp vụ chỉ cho gọi một số dịch vụ:

- Không nhận toàn bộ URL nếu không cần.
- Nhận một identifier hoặc hostname được giới hạn theo allowlist.
- Ứng dụng tự chọn scheme, port và base path.
- Kiểm tra DNS resolution và địa chỉ IPv4/IPv6 được phép.
- Kiểm soát redirect để không chuyển sang host/địa chỉ khác ngoài policy.
- Áp dụng policy tương tự cho retry, proxy và fallback.

### 14.2. Open redirect

Nếu response trả `Location` dựa trên URL người dùng gửi, cần kiểm tra host và scheme theo allowlist. Encode URL không ngăn browser điều hướng tới một host độc hại.

### 14.3. Path traversal

Nếu một path variable đại diện tên file, các giá trị như `../secret.txt` hoặc dạng percent-encoded có thể trở thành traversal sau khi decode ở tầng server.

- Validate theo business contract.
- Chuẩn hóa path tại filesystem boundary.
- Giới hạn đường dẫn trong root được phép.
- Kiểm tra symlink và quyền truy cập.
- Không dựa riêng vào việc `%2E` hoặc `%2F` đã được encode.

### 14.4. Không đưa secret vào URI

Token, API key, password hoặc dữ liệu cá nhân không nên đặt trong query string. Dùng header hoặc body theo chuẩn API. Percent-encoding không bảo vệ chúng khỏi access log hoặc history.

## 15. WebClient: ví dụ service gọi API với path và query variables

Ví dụ sau minh họa cách tạo request; giả định có WebClient bean và kiểu response:

~~~java
public Mono<SearchResponse> search(
        String category,
        String term,
        int page) {

    return webClient.get()
            .uri(builder -> builder
                    .path("/v1/categories/{category}/search")
                    .queryParam("q", "{term}")
                    .queryParam("page", "{page}")
                    .build(category, term, page))
            .retrieve()
            .bodyToMono(SearchResponse.class);
}
~~~

Với `category` và `term` do input đưa vào, URI builder xử lý từng biến theo component. Không nối term vào query string.

Một cấu hình client dùng chung:

~~~java
@Configuration
class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        DefaultUriBuilderFactory factory =
                new DefaultUriBuilderFactory("https://partner.example.test");

        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return WebClient.builder()
                .uriBuilderFactory(factory)
                .build();
    }
}
~~~

Đây là ví dụ cấu hình Spring Boot WebFlux, cần import `Configuration`, `Bean`, `WebClient` và `DefaultUriBuilderFactory`. Base URL là cấu hình do ứng dụng kiểm soát; không lấy nguyên URL do user gửi rồi gắn làm base URL.

## 16. Chương trình Java 17+ chạy được: quan sát output của URI builder

Chương trình sau chỉ dùng Spring Web module, không cần chạy HTTP server. Nó minh họa:

1. Space, plus, ampersand và Unicode trong path/query.
2. Slash nằm trong một path segment value.
3. DefaultUriBuilderFactory với TEMPLATE_AND_VALUES.
4. Khác biệt giữa encode trước expand và encode sau expand.
5. Double encoding khi đưa giá trị đã percent-encode vào builder.
6. Khác biệt giữa URI percent-encoding và form encoding của URLEncoder.

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Framework 7.0.8**. Trong dự án thật, dùng Spring version line được Spring Boot BOM quản lý nếu ứng dụng đang dùng Boot.

Cấu trúc:

~~~text
uri-builder-demo/
  pom.xml
  src/main/java/example/uri/UriBuilderDemo.java
~~~

### 16.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>uri-builder-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>7.0.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.2. UriBuilderDemo.java

~~~java
package example.uri;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;

import org.springframework.web.util.DefaultUriBuilderFactory;
import org.springframework.web.util.UriComponentsBuilder;

public final class UriBuilderDemo {

    private static void printAndCheck(
            String name, URI actual, String expected) {

        String value = actual.toASCIIString();

        if (!expected.equals(value)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", actual=" + value);
        }

        System.out.println(name + "=" + value);
    }

    public static void main(String[] args) {
        // 1) Strict encoding of path and query variables.
        URI search = UriComponentsBuilder
                .fromPath("/hotel list/{city}")
                .queryParam("q", "{q}")
                .encode()
                .buildAndExpand("New York", "foo+bar & café")
                .toUri();

        printAndCheck(
                "search",
                search,
                "/hotel%20list/New%20York?q=foo%2Bbar%20%26%20caf%C3%A9");

        // 2) A slash inside a path-segment variable is encoded as data.
        URI file = UriComponentsBuilder
                .fromUriString("https://api.example.test/v1")
                .pathSegment("files", "{fileName}")
                .encode()
                .buildAndExpand("guide 1/2.pdf")
                .toUri();

        printAndCheck(
                "file",
                file,
                "https://api.example.test/v1/files/guide%201%2F2.pdf");

        // 3) A shared UriBuilderFactory with an explicit encoding policy.
        DefaultUriBuilderFactory factory =
                new DefaultUriBuilderFactory("https://api.example.test");

        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        URI fromFactory = factory.uriString("/search/{term}")
                .queryParam("tag", "{tag}")
                .queryParam("page", "{page}")
                .build("C++ & Java", "spring boot", 2);

        printAndCheck(
                "factory",
                fromFactory,
                "https://api.example.test/search/C%2B%2B%20%26%20Java"
                        + "?tag=spring%20boot&page=2");

        // 4) Strict variable encoding versus component encoding.
        URI strict = UriComponentsBuilder
                .fromPath("/codes/{value}")
                .encode()
                .buildAndExpand("A;B")
                .toUri();

        URI component = UriComponentsBuilder
                .fromPath("/codes/{value}")
                .buildAndExpand("A;B")
                .encode()
                .toUri();

        printAndCheck("strict", strict, "/codes/A%3BB");
        printAndCheck("component", component, "/codes/A;B");

        // 5) Passing an already encoded value encodes the percent sign again.
        URI doubleEncoded = UriComponentsBuilder
                .fromPath("/files/{name}")
                .encode()
                .buildAndExpand("a%2Fb")
                .toUri();

        printAndCheck("doubleEncoded", doubleEncoded, "/files/a%252Fb");

        // 6) URLEncoder is form encoding: a space becomes plus.
        String formEncoded = URLEncoder.encode(
                "C++ & Java", StandardCharsets.UTF_8);

        System.out.println("form=" + formEncoded);
    }
}
~~~

### 16.3. Chạy chương trình

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.uri.UriBuilderDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
search=/hotel%20list/New%20York?q=foo%2Bbar%20%26%20caf%C3%A9
file=https://api.example.test/v1/files/guide%201%2F2.pdf
factory=https://api.example.test/search/C%2B%2B%20%26%20Java?tag=spring%20boot&page=2
strict=/codes/A%3BB
component=/codes/A;B
doubleEncoded=/files/a%252Fb
form=C%2B%2B+%26+Java
~~~

Diễn giải:

- `search`: space thành `%20`, dấu `+` thành `%2B`, dấu `&` thành `%26`, và `é` thành `%C3%A9`.
- `file`: slash nằm bên trong một path-segment variable được mã hóa thành `%2F`.
- `factory`: factory dùng TEMPLATE_AND_VALUES cho path và query variables.
- `strict`: dấu `;` trong variable được coi là dữ liệu và mã hóa thành `%3B`.
- `component`: encode sau expand giữ `;` vì ký tự đó hợp lệ trong path component.
- `doubleEncoded`: `%` của chuỗi đã encode được mã hóa thành `%25`, nên `%2F` thành `%252F`.
- `form`: URLEncoder biểu diễn space bằng `+`, đúng semantics form encoding.

Chương trình không gửi HTTP request ra mạng. Nó kiểm tra cách Spring xây dựng URI và xác minh chuỗi output bằng assertion trước khi in.

## 17. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nối query string bằng `+` | `&`, `#`, `=` có thể thay đổi cấu trúc | Dùng `queryParam` với URI variable |
| Nối user input vào path | Slash hoặc dấu `?` có thể tạo segment/query ngoài ý muốn | Dùng `pathSegment` hoặc path template |
| Dùng URLEncoder cho toàn URL | Dấu cấu trúc `/`, `?`, `&` bị biến thành dữ liệu | Chỉ dùng form encoding cho form value; dùng UriBuilder cho URI |
| Encode value trước rồi đưa vào builder | `%2F` thành `%252F` | Truyền raw value và encode một lần |
| Dùng `URI_COMPONENT` mà không hiểu reserved characters | `;`, `/` hoặc reserved char có thể giữ ý nghĩa cấu trúc | Dùng TEMPLATE_AND_VALUES khi variable là opaque data |
| Dùng `NONE` để né double encoding | Ký tự dữ liệu có thể trở thành dấu phân cách | Tìm nguồn đã encode trước và sửa tại boundary |
| Dùng `path()` với input có slash | Input có thể thêm path segment | Dùng `pathSegment()` và kiểm thử encoded slash qua toàn hạ tầng |
| Cho rằng `+` luôn là space | Literal plus có thể bị đổi thành khoảng trắng | Encode literal plus thành `%2B` |
| Nghĩ fragment `#details` được gửi tới server | Fragment không nằm trong HTTP request | Dùng path/query/body theo contract |
| Encode cả URI thay vì từng component | Cấu trúc URI bị phá | Tạo từng component bằng builder |
| Chỉ kiểm tra URL parse được | URL có thể vẫn trỏ tới host không được phép | Validate scheme, host, port và destination policy |
| Coi percent-encoding là bảo mật | Dữ liệu nhạy cảm vẫn xuất hiện trong log/history | Không đặt secret trong URL |
| Chỉ test URL ASCII | Lỗi Unicode và UTF-8 bị bỏ sót | Test tiếng Việt và ký tự reserved |
| Không test proxy/server decode | `%2F` có thể được xử lý khác giữa các tầng | Integration test qua toàn bộ đường đi |
| Normalize URI sau khi ký | Chữ ký request không còn khớp | Canonicalize theo contract trước khi ký và gửi cùng URI |

## 18. Quy trình kiểm tra khi URI sai

Khi request không tới endpoint đúng hoặc server nhận giá trị sai, kiểm tra theo thứ tự:

1. **In URI cuối cùng** bằng `toASCIIString()` ở môi trường test; không log token hoặc thông tin nhạy cảm.
2. **Tách component** bằng `URI.getScheme()`, `getHost()`, `getPath()`, `getRawPath()`, `getQuery()` và `getRawQuery()`.
3. **Kiểm tra template**: biến động có được đặt thành placeholder không?
4. **Kiểm tra vị trí builder**: path variable có được thêm bằng `pathSegment`? Query có được thêm bằng `queryParam`?
5. **Kiểm tra encoding mode**: TEMPLATE_AND_VALUES, VALUES_ONLY, URI_COMPONENT hay NONE?
6. **Kiểm tra raw input**: giá trị có bị encode trước khi vào builder không?
7. **Kiểm tra UTF-8**: server có giải mã cùng charset và cùng normalization không?
8. **Kiểm tra network path**: proxy/gateway có decode `%2F`, normalize dot-segment hoặc rewrite query không?
9. **Kiểm tra contract server**: server có nhận repeated key, empty value và plus theo semantics dự kiến không?
10. **Kiểm tra signature/cache** nếu URI tham gia canonical request hoặc cache key.

Một URI được in đúng ở client chưa bảo đảm proxy và server xử lý giống nhau. Với những ký tự có ảnh hưởng cấu trúc như `%2F`, `%2E`, `%25`, hãy kiểm tra từ client tới server thật.

## 19. Checklist trước khi đưa URI builder vào production

- [ ] Base URL, scheme, host và port đến từ cấu hình hoặc destination allowlist đáng tin cậy.
- [ ] Template path/query được viết trong code hoặc được kiểm soát.
- [ ] Mọi dữ liệu động được truyền qua URI variables.
- [ ] Path value dùng `pathSegment` khi phải giữ trong một segment.
- [ ] Query được tạo bằng `queryParam`/`queryParams`.
- [ ] Encoding mode được hiểu và thống nhất.
- [ ] Dữ liệu raw chỉ được encode một lần.
- [ ] Literal `+` được encode thành `%2B` khi là dữ liệu.
- [ ] Space, `&`, `=`, `#`, `%`, `/` và Unicode đã có test.
- [ ] Repeated query key, empty và absent parameter theo đúng contract.
- [ ] Không đưa token/password/PII vào URI.
- [ ] URL do user kiểm soát được kiểm tra SSRF, redirect và destination.
- [ ] Encoded slash/path traversal được test qua proxy/server.
- [ ] Request signing và cache canonicalization dùng cùng quy tắc URI.

## 20. Tự kiểm tra

**Câu 1.** Tại sao không nên nối `?q=` với một chuỗi tìm kiếm tùy ý?

Vì chuỗi có thể chứa `&`, `#`, `=` hoặc reserved characters khác làm thay đổi cấu trúc query. Dùng `queryParam("q", "{q}")` và truyền value riêng.

**Câu 2.** `UriComponentsBuilder.encode()` khác `UriComponents.encode()` ở đâu?

Builder encode template trước và encode chặt URI variables khi expand; component encode diễn ra sau khi expand và có thể giữ reserved character hợp lệ trong component.

**Câu 3.** Khi variable path chứa `A;B`, tại sao TEMPLATE_AND_VALUES tạo `A%3BB`?

Vì `;` thuộc dữ liệu variable và được strict-encode để không mang ý nghĩa reserved trong path.

**Câu 4.** Vì sao `URLEncoder.encode("A B", UTF_8)` trả `A+B`?

Vì URLEncoder dùng semantics `application/x-www-form-urlencoded`, trong đó space được biểu diễn bằng `+`. URI percent-encoding thông thường dùng `%20`.

**Câu 5.** Nếu value gốc là `a/b`, builder strict-encode tạo gì khi nó là một path variable?

`a%2Fb`, để slash thuộc dữ liệu của variable thay vì dấu phân cách path.

**Câu 6.** Tại sao truyền `a%2Fb` vào builder lại có thể tạo `a%252Fb`?

Vì `%` được xem là ký tự dữ liệu và mã hóa thành `%25`; builder không biết chuỗi đó đã được encode trước.

**Câu 7.** Fragment `#details` có được gửi tới server trong HTTP request không?

Không. Fragment là phần định vị phía client và không thuộc request target gửi tới server.

**Câu 8.** WebClient có thể dùng chung UriBuilderFactory để làm gì?

Để chia sẻ base URL, encoding mode và các lựa chọn chuẩn bị URI giữa các request.

**Câu 9.** Dùng UriBuilder có tự ngăn SSRF nếu host do client gửi lên không?

Không. Builder tạo URI đúng cú pháp; ứng dụng vẫn phải kiểm tra scheme, host, port, DNS/address và redirect theo policy.

**Câu 10.** Khi nào cần integration test cho encoded slash?

Khi một path variable có thể chứa slash hoặc dữ liệu đã encode; proxy, gateway và server có thể decode/normalize khác nhau trước khi route.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — URI Links (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriComponentsBuilder, UriBuilderFactory, parser type và hai cấp URI encoding.
- [Spring Framework — UriComponentsBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): API xây dựng, expand, encode và tạo URI.
- [Spring Framework — UriBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriBuilder.html): path, pathSegment, queryParam, build và URI variables.
- [Spring Framework — DefaultUriBuilderFactory JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html): EncodingMode và cấu hình UriBuilderFactory.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình uriBuilderFactory cho WebClient.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): reserved/unreserved characters, URI components và percent-encoding.
- [Java 17 — URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html): form URL encoding và charset.
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlist destination, kiểm tra URL và kiểm soát redirect khi server gọi URL bên ngoài.

**Ghi nhớ:** Dùng `UriComponentsBuilder` hoặc `UriBuilderFactory` để ghép URI theo từng component. Giữ template cố định, truyền raw value qua URI variables, chọn encoding mode rõ ràng và encode đúng một lần. Dùng `pathSegment` cho dữ liệu thuộc một segment, `queryParam` cho query values, phân biệt `%20` với `+`, và kiểm tra destination riêng khi URL do người dùng ảnh hưởng.