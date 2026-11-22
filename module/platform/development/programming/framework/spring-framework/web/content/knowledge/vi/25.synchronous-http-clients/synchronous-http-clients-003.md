# Gửi yêu cầu với URI template, query, form và multipart bằng HTTP client đồng bộ của Spring

## 1. Mục tiêu bài học

Một ứng dụng Spring thường cần gọi một HTTP API khác để lấy dữ liệu, tra cứu trạng thái, gửi biểu mẫu hoặc tải một tệp cùng metadata. Với HTTP client **đồng bộ**, thread gọi client thường chờ cho tới khi nhận và xử lý xong response hoặc xảy ra timeout/error. Nếu ghép URL và request body không đúng, những lỗi tưởng nhỏ như dấu `+`, dấu `&`, `Content-Type` và tên file có thể khiến server nhận dữ liệu khác ý định.

Bài học thuộc nhóm **HTTP client đồng bộ** trong Spring Framework Web. Các ví dụ chính sử dụng **Java 17+, Spring Framework 6.1+ và Spring Boot 3.2+**, vì `RestClient` được giới thiệu từ Spring Framework 6.1. Để học trong nhánh Spring 6.2, có thể dùng Spring Boot 3.4 hoặc 3.5 tương thích; chọn một phiên bản Boot 3.x cụ thể do dự án quản lý, không ghép thủ công các Spring jars khác version. Phần `RestTemplate` mô tả lựa chọn tương thích với code cũ.

Sau bài học, bạn cần làm được:

- Phân biệt **URI template**, **path variable**, **query parameter**, **form-urlencoded body** và **multipart/form-data body**.
- Dùng `RestClient.get()`/`post()`, `.uri(...)`, `.accept(...)`, `.contentType(...)`, `.body(...)`, `.retrieve()`.
- Truyền URI variables bằng map/arguments, tạo query với `UriBuilder`/`UriComponentsBuilder` thay vì nối chuỗi không kiểm soát.
- Hiểu vì sao `C++`, `a&b`, khoảng trắng, `/` và chuỗi đã percent-encoded cần được encode đúng ngữ cảnh và **không double-encode**.
- Gửi `application/x-www-form-urlencoded` bằng `MultiValueMap<String,String>` để giữ giá trị lặp.
- Gửi `multipart/form-data` bằng `MultiValueMap<String,Object>`, `FileSystemResource` và `HttpEntity<?>` cho từng part có header riêng.
- Hiểu cách message converters chọn representation, tự sinh multipart `boundary` và parse response JSON.
- Xử lý HTTP 4xx/5xx, lỗi mạng, timeout, retry, idempotency và kích thước payload.
- Tự chạy ứng dụng Spring Boot có HTTP endpoint kiểm chứng cả ba trường hợp và test bằng `RestClient`/JUnit.
- Biết khi nào nên tiếp tục dùng `RestTemplate` và khi nào cần client bất đồng bộ `WebClient`.

**Phạm vi:** đây là client gọi HTTP **đồng bộ**. `RestClient` API trông có fluent chaining giống `WebClient`, nhưng **không** trả `Mono`/`Flux` và không tự trở thành non-blocking. Nếu gọi từ Netty event loop trong WebFlux mà chờ I/O, bạn có thể chặn event loop; khi cần throughput I/O cao, chọn WebClient/reactive downstream hoặc tách blocking work sang bounded worker với giới hạn tài nguyên.

## 2. Bản đồ request: dữ liệu ở vị trí nào?

Xem request giả định:

```http
POST /orders/sku-42?region=vn&tag=urgent&tag=gift HTTP/1.1
Host: inventory.example.test
Accept: application/json
Content-Type: application/x-www-form-urlencoded

customer=Linh+An&note=C%2B%2B%20%26%20Java
```

Phân tích:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| URI path | `/orders/sku-42` | Xác định resource; `sku-42` có thể đến từ `{id}` |
| Query string | `region=vn&tag=urgent&tag=gift` | Tham số trong URL, có thể lặp cùng tên |
| `Accept` | `application/json` | Client muốn nhận representation nào |
| `Content-Type` | `application/x-www-form-urlencoded` | Loại **body request** đang gửi |
| Form field | `customer=Linh+An` | Form decoder hiểu `+` là khoảng trắng |
| Encoded form value | `note=C%2B%2B%20%26%20Java` | Literal `C++ & Java` sau decode |
| HTTP method | `POST` | Operation của resource; không thay thế việc xác định body |

Với **multipart** thì body được chia thành nhiều parts có `Content-Disposition`, tên field, optional filename và từng `Content-Type`. Multipart không giống một form-urlencoded string nối bằng `&`.

Các vị trí trên cần **các công cụ encode khác nhau**. Lỗi phổ biến là dùng `URLEncoder` dành cho HTML form để tạo cả URI path hoặc tự thêm `?`/`&` mà quên encode từng component.

## 3. Các client HTTP đồng bộ trong Spring

Theo tài liệu Spring Framework:

| API | Mô hình | Khi nào phù hợp |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent API | Code mới với Spring Framework 6.1+ |
| `RestTemplate` | Synchronous, template methods | Ứng dụng cũ, cần bảo trì/tích hợp |
| HTTP Service Client | Java interface có HTTP exchange annotations; backend có thể dùng RestClient | Muốn HTTP contract declarative |
| `WebClient` | Non-blocking/reactive | I/O reactive, nhiều request đồng thời, streaming bất đồng bộ |
| Java 11+ `HttpClient.send` | Synchronous JDK API không phụ thuộc Spring | Java thuần hoặc cần hiểu HTTP primitives |

Bài tập dùng `RestClient` vì API hiện đại trong dòng Spring 6.x và hỗ trợ converters giống `RestTemplate`. Ở Spring Framework 7.x, `RestTemplate` đã được đánh dấu deprecated, nhưng **không suy tất cả ứng dụng Spring 6.x phải viết lại ngay**; chọn phương án theo version và vòng đời hệ thống thực tế.

### Synchronous khác reactive thế nào?

```text
Thread A: RestClient.get() ------ waiting I/O ------ response DTO
Thread B: WebClient.get() ------ returns Mono -------- subscription/callback

RestClient + Tomcat Servlet app: có thể hợp lý cho outbound HTTP ngắn.
RestClient trong Netty WebFlux event-loop: có thể gây blocking/starvation.
```

RestClient trả DTO khi operation hoàn tất (hoặc ném exception), không phải một Publisher có thể giữ mà chưa gọi. Nếu client timeout, remote server vẫn có thể đang xử lý request; timeout không chứng minh operation chưa commit.

## 4. Khởi tạo RestClient đúng version

Dependencies Maven của ứng dụng Spring Boot 3.2+:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
```

Đây là **đoạn dependencies** để thêm vào `pom.xml` do Spring Initializr tạo, **không** phải một POM độc lập. `spring-boot-starter-web` cung cấp Spring MVC để dựng local server demo cùng HTTP message converters/Jackson. Thư viện `spring-web` có `RestClient`; không cần thêm WebFlux chỉ để dùng RestClient.

Khởi tạo tối giản:

```java
RestClient client = RestClient.create();
```

Hoặc cấu hình:

```java
RestClient client = RestClient.builder()
    .baseUrl("https://api.example.test")
    .defaultHeader("X-App", "learning")
    .build();
```

Lớp `RestClient` là `org.springframework.web.client.RestClient`. Client sau `build()` có thể được chia sẻ giữa các threads theo tài liệu Spring; **không** vì thế mà biến mọi POJO/request body mutable thành thread-safe. Dự án production nên tạo Bean singleton với base URL/timeouts/error policy được cấu hình thay vì khởi tạo một RestClient mới cho mỗi request.

### Yêu cầu HTTP GET đơn giản

```java
ItemView item = client.get()
    .uri("/items/{id}", "SKU-42")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(ItemView.class);
```

Đây là **snippet** yêu cầu client và record `ItemView`, không phải class độc lập. `.uri("/items/{id}", "SKU-42")` thay placeholder bằng URI variable theo chính sách encoding. `.retrieve().body(ItemView.class)` thực hiện HTTP exchange đồng bộ và dùng message converter để decode JSON; method có thể trả null nếu không có body phù hợp, không nên `item.id()` mà không kiểm null.

## 5. URI template: path variable và query không được trộn

Một URI template có placeholders:

```text
https://api.example.test/items/{id}
https://api.example.test/items/{id}?locale={locale}
https://api.example.test/search?q={keyword}&page={page}
```

Các placeholder **không phải literal path**. Chúng được thay bằng values để Spring có cơ hội encode theo URI component. Ví dụ:

```java
String id = "SKU-42";

ItemView item = client.get()
    .uri("/items/{id}", id)
    .retrieve()
    .body(ItemView.class);
```

Nếu value đến từ người dùng, đừng ghép:

```java
String unsafe = "/items/" + userSuppliedId;
```

Đây là anti-pattern: ID chứa `?`, `#`, `/`, `%` hoặc dấu cách có thể đổi ý nghĩa URI. Dùng template expansion và ID validation ở domain layer.

### Sử dụng nhiều biến với Map

```java
Map<String, Object> params = Map.of(
    "shop", "vn",
    "id", "SKU-42");

ItemView item = client.get()
    .uri("/shops/{shop}/items/{id}", params)
    .retrieve()
    .body(ItemView.class);
```

Đây là snippet với imports `java.util.Map`. Dùng map tránh phụ thuộc vào thứ tự positional arguments khi URI có nhiều placeholders.

**Không mặc định URI variable có slash sẽ được server chấp nhận.** Nếu item ID chứa `a/b`, template encoding có thể biểu diễn nó thành `a%2Fb`; nhiều server/gateway có chính sách chặn encoded slash hoặc decode trước routing. Thiết kế ID path-safe/opaque phù hợp và test qua ingress thật, không “vượt rào” bằng double encoding.

## 6. Query parameters với UriBuilder thay vì nối chuỗi

Trường hợp cần URI như:

```text
GET /search?q=C%2B%2B%20%26%20Java&page=2&tag=java&tag=spring%20web
```

Không nên tự viết:

```java
String url = "/search?q=" + keyword + "&tag=" + tag;
```

Nếu `keyword="C++ & Java"`, literal `+`/`&` có thể bị diễn giải khác bởi decoder/query parser. Dùng URI builder và **URI variables** khi cần strict encoding.

```java
SearchResult result = client.get()
    .uri(b -> b.path("/search")
        .queryParam("q", "{q}")
        .queryParam("page", 2)
        .queryParam("tag", "{tag1}", "{tag2}")
        .build(Map.of(
            "q", "C++ & Java",
            "tag1", "java",
            "tag2", "spring web")))
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(SearchResult.class);
```

Đây là snippet với `SearchResult` được ứng dụng định nghĩa. `queryParam("tag", ...)` có thể thêm repeated parameter values, còn `UriBuilder.build(Map)` expand URI variables.

**Mấu chốt encoding:** dùng `DefaultUriBuilderFactory` với mode phù hợp, thường `TEMPLATE_AND_VALUES` (giá trị template variable được encode nghiêm ngặt). Nếu dự án thay custom `UriBuilderFactory` hoặc truyền một `URI` đã build sẵn, encoding rules có thể khác. Khi query chứa `+`, percent escapes hoặc reserved characters, phải test **URI thực gửi lên wire** thay vì suy từ chuỗi Java.

## 7. Cấu hình URI builder encoding rõ ràng

`DefaultUriBuilderFactory` là factory Spring dùng để tạo URI builder. Mặc định từ những bản Spring 5.1 đã đổi theo hướng `TEMPLATE_AND_VALUES`, nhưng cấu hình rõ giúp code ít phụ thuộc các defaults bị sửa ở client.

```java
DefaultUriBuilderFactory factory =
    new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

RestClient client = RestClient.builder()
    .uriBuilderFactory(factory)
    .build();
```

Imports:

```java
import org.springframework.web.util.DefaultUriBuilderFactory;
import org.springframework.web.client.RestClient;
```

Đây là snippet trong config/test có classpath Spring. Với `TEMPLATE_AND_VALUES`, template được xử lý và **giá trị biến** được encode như dữ liệu, giúp `C++ & Java` không phá ký tự phân cách. Trong ví dụ app chạy ở dưới, chúng ta dùng đúng cấu hình này.

### Query parameter trống, thiếu và nhiều values

```text
/search                  q không có
/search?q=               q có mặt, value rỗng
/search?q=one&q=two      q lặp hai lần
/search?q=a%2Bb          q literal "a+b" khi decode
```

API cần định nghĩa rõ **thiếu** khác **chuỗi rỗng** và repeated values. Đối với `page`, `-1` convert được thành số nhưng có thể sai domain range; validation là bước riêng của server.

### Optional query values

Nếu query optional, chỉ gọi `queryParamIfPresent(...)` khi có `Optional`, hoặc thêm parameter có điều kiện trong lambda builder. **Không** gửi string `"null"` chỉ vì variable Java có giá trị null; trong Spring, `queryParam("q", null)` còn có thể tạo parameter không có value tùy API. Mọi API cần quy định rõ absent vs empty.

## 8. encode URI: percent encoding và form encoding khác nhau

Có nhiều chuẩn biểu diễn:

| Giá trị đầu vào | Trong URI query variable (ví dụ strict encoding) | Trong form-urlencoded |
| --- | --- | --- |
| `A B` | `A%20B` | `A+B` |
| `C++` | `C%2B%2B` | `C%2B%2B` |
| `a&b` | `a%26b` | `a%26b` |
| `x=y` | `x%3Dy` | `x%3Dy` |
| `a/b` | `a%2Fb` khi là variable strict | `a%2Fb` |
| `100%` | `100%25` | `100%25` |

Bảng minh họa **giá trị** khi encoding nghiêm ngặt, không phải lời hứa mọi HTTP client/version đều chọn byte-for-byte cùng cách mã hóa nếu cấu hình khác. `%20` và `+` có thể cùng đại diện space khi giải mã form, nhưng **trong URI query nhiều parser không coi chúng hoàn toàn tương đương**. Literal dấu `+` rất dễ mất nếu client không encode đúng khi server xử lý query theo form convention.

### Vì sao không dùng URLEncoder cho URI path?

`java.net.URLEncoder` encode theo **application/x-www-form-urlencoded**, nghĩa là **space → +**. Trong path, `+` có thể là literal dấu cộng chứ không phải space. Vì vậy không lấy `URLEncoder.encode(id)` rồi nối vào path. Dùng `UriBuilder`, `UriComponentsBuilder`/URI template expansion đúng ngữ cảnh.

### Không double-encode

Nếu value gốc là `"a/b"`, encoder có thể gửi `a%2Fb`. Nếu bạn truyền vào client **chuỗi đã encode** `"a%2Fb"` như dữ liệu chưa encode, lần encode tiếp có thể tạo `a%252Fb`. Server nhận literal `a%2Fb` sau một lần decode, không phải slash. Quy tắc: **lưu value ở dạng chưa encode ở business layer; encode một lần tại HTTP boundary**. Nếu đã có một `URI` được build/encode đúng, truyền `uri(URI)` và đừng đưa nó lại vào template expander.

## 9. Tạo URI hoàn chỉnh bằng UriComponentsBuilder

Có trường hợp dùng cùng một URI cho RestClient và RestTemplate. `UriComponentsBuilder` giúp build `java.net.URI` hoàn chỉnh:

```java
URI uri = UriComponentsBuilder
    .fromUriString("https://api.example.test")
    .path("/items/{id}")
    .queryParam("q", "{q}")
    .queryParam("page", 2)
    .encode()
    .buildAndExpand(Map.of(
        "id", "SKU-42",
        "q", "C++ & Java"))
    .toUri();

ItemView item = client.get()
    .uri(uri)
    .retrieve()
    .body(ItemView.class);
```

Snippet cần imports `java.net.URI`, `java.util.Map`, `org.springframework.web.util.UriComponentsBuilder`. `encode()` **trước** `buildAndExpand` bảo đảm URI variables được encode nghiêm ngặt theo contract builder; literal template special characters có semantics khác variable values.

**Quan trọng:** `RestClient.uri(URI)` sử dụng URI đã tạo; không encode lại như `uri(String, variables)`. Nếu protocol/API yêu cầu query parameter order cụ thể để ký request, đừng tin unordered Map; xây canonical request theo chuẩn chữ ký của service, bao gồm thứ tự/escaping một cách tường minh.

## 10. GET parameters khác POST form body

Những cặp HTTP request sau **không giống nhau**:

```http
GET /search?name=Linh+An HTTP/1.1
Host: example.test

POST /form HTTP/1.1
Host: example.test
Content-Type: application/x-www-form-urlencoded

name=Linh+An
```

`GET` query nằm trong URI; `POST` form fields nằm trong **body**. Cùng server có thể gom query + form qua `@RequestParam` khi chạy **Spring MVC/Servlet**, nhưng không được vì vậy xây client giả định form-urlencoded là query string.

Form body thường được tạo bằng `MultiValueMap<String,String>`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "Linh & An");
form.add("tag", "java");
form.add("tag", "C++");
```

`MultiValueMap` chứa nhiều values cho cùng key; map thường `Map<String,String>` không biểu đạt đủ `tag` xuất hiện hai lần. Đây cũng là cách an toàn để tránh nối body string thủ công.

## 11. POST application/x-www-form-urlencoded với RestClient

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "Linh & An");
form.add("tag", "java");
form.add("tag", "C++");

FormReply reply = client.post()
    .uri("/form")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .accept(MediaType.APPLICATION_JSON)
    .body(form)
    .retrieve()
    .body(FormReply.class);
```

Đây là snippet cần client và record `FormReply`. Khi cấu hình message converters chuẩn Spring Web, `FormHttpMessageConverter` biến các fields thành **body form-urlencoded**, percent-encode values, thêm Content-Type phù hợp và gửi POST đồng bộ.

Ví dụ body wire **về mặt ý nghĩa**:

```text
name=Linh+%26+An&tag=java&tag=C%2B%2B
```

Thứ tự keys, charset/encoding và header phụ thuộc converter/config; dùng integration test để bảo đảm contract. Không xây string ghép tay trong business logic.

### Content-Type và Accept khác nhau

- `.contentType(APPLICATION_FORM_URLENCODED)`: client **đang gửi form**.
- `.accept(APPLICATION_JSON)`: client **muốn nhận JSON**.
- `.body(form)`: giá trị cần encode theo form writer.
- `.retrieve().body(FormReply.class)`: đọc JSON response thành record.

Nếu gửi form map mà đặt Content-Type `application/json`, server có thể không nhận được form như mong đợi và trả 400/415. Ngược lại một body JSON DTO không tự biến thành form chỉ nhờ gọi `.post()`.

## 12. Lựa chọn message converter cho form và multipart

Spring HTTP message conversion chọn writer dựa vào **Java body type** và **Content-Type**.

| Body Java | Content-Type chủ định | Converter thường phù hợp |
| --- | --- | --- |
| `MultiValueMap<String,String>` | `application/x-www-form-urlencoded` | `FormHttpMessageConverter` |
| `MultiValueMap<String,Object>` chứa Resource/HttpEntity | `multipart/form-data` | `FormHttpMessageConverter` / `AllEncompassingFormHttpMessageConverter` |
| DTO Java record | `application/json` | `MappingJackson2HttpMessageConverter` |
| `String` | `text/plain` | `StringHttpMessageConverter` |
| `byte[]` | `application/octet-stream` | `ByteArrayHttpMessageConverter` |
| `Resource` | stream binary content tùy converter | `ResourceHttpMessageConverter` |

Spring Framework reference cho phép multipart parts là `Object`, `Resource` hoặc `HttpEntity<?>` có headers riêng. Spring tự chọn part converter theo content và headers.

**Lưu ý:** Khi `MultiValueMap` chứa ít nhất một part **không phải String**, converter có thể suy ra multipart; nếu chỉ chứa String, default thường là form-urlencoded. Để bài dễ hiểu, **đặt rõ `Content-Type` mong muốn**, nhất là khi bạn muốn multipart chỉ có text fields. Đừng giả định `Content-Type` của response giống của request.

### Multipart chỉ chứa text có được không?

Có. Một client có thể gửi multipart với các parts đều là text. Vì đó vẫn là multipart representation, phải đặt `MediaType.MULTIPART_FORM_DATA` tường minh hoặc đảm bảo converter phân loại đúng. Nếu không có file và endpoint chỉ cần vài fields, form-urlencoded thường đơn giản và nhẹ hơn.

## 13. Multipart là gì?

HTTP multipart/form-data bao gồm các parts phân cách bằng **boundary** được quy định trong header.

```http
POST /upload HTTP/1.1
Host: example.test
Content-Type: multipart/form-data; boundary=someUniqueBoundary

--someUniqueBoundary
Content-Disposition: form-data; name="description"

Demo document
--someUniqueBoundary
Content-Disposition: form-data; name="file"; filename="sample.txt"
Content-Type: text/plain

hello
--someUniqueBoundary--
```

Đây là cấu trúc minh họa của HTTP payload, **không nên tự gõ ra** khi dùng Spring RestClient. Spring multipart converter sẽ tạo boundary phù hợp, viết từng phần và đóng dấu cuối.

Một multipart request có thể chứa:
- Text field `description`.
- File `file` từ `Resource`.
- JSON metadata `meta` được encode bằng Jackson.
- Part khác với media type và headers riêng.

Không đồng nhất multipart `Content-Type` tổng thể với `Content-Type` riêng của part. Một request `multipart/form-data` có thể chứa `application/json` ở part `meta`.

## 14. Xây multipart với MultiValueMap<String,Object>

```java
MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();

parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));

UploadReply reply = client.post()
    .uri("/upload")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .accept(MediaType.APPLICATION_JSON)
    .body(parts)
    .retrieve()
    .body(UploadReply.class);
```

Đây là snippet trong method đã có client và `sample.txt` thực sự tồn tại. Imports `org.springframework.core.io.FileSystemResource`, `org.springframework.util.MultiValueMap`, `LinkedMultiValueMap`, `java.nio.file.Path`.

- `"description"` là plain form part.
- `"file"` dùng FileSystemResource; converter có thể lấy filename và đọc nội dung file.
- `contentType(MULTIPART_FORM_DATA)` khai báo toàn request là multipart.
- **Không** tự đặt boundary trong header; converter chịu trách nhiệm.
- Body `parts` được xử lý đồng bộ; implementation request factory có thể buffer hoặc stream tùy cấu hình. Đừng khẳng định mọi client mặc định stream file với memory O(1).

### Tại sao dùng FileSystemResource thay vì byte[]?

`FileSystemResource` cung cấp tên file, đường dẫn và nội dung stream theo Resource API, phù hợp một file đã có trên disk. Nếu bạn dùng `byte[]` thuần, converter không luôn coi đó là **file có filename** như mong muốn. Nếu API đòi filename, sử dụng Resource có `getFilename()` đúng hoặc bao part bằng `HttpEntity<Resource>` với Content-Disposition phù hợp.

## 15. Part JSON và HttpEntity có headers riêng

Một multipart request có thể có metadata JSON:

```java
record Meta(String source) {}

HttpHeaders jsonHeaders = new HttpHeaders();
jsonHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<Meta> jsonPart =
    new HttpEntity<>(new Meta("draft"), jsonHeaders);

MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();

parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));
parts.add("meta", jsonPart);

UploadReply reply = client.post()
    .uri("/upload")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(parts)
    .retrieve()
    .body(UploadReply.class);
```

Đây là **snippet**: `Meta` record/`UploadReply` phải có đúng contract với server. `HttpEntity` là wrapper **part content + part headers**, không phải một HTTP request mới. JSON part có `Content-Type: application/json`, được Jackson converter encode khi dependency tương ứng có mặt. File part vẫn là FileSystemResource.

**Không dùng `HttpEntity` để thay cho top-level request headers.** Top-level RestClient `.contentType(...)`/`.accept(...)` thuộc HTTP request; part HttpEntity headers chỉ áp dụng cho part. Nếu service yêu cầu tên part là `metadata` thay vì `meta`, phải trùng chính xác.

## 16. ByteArrayResource và vấn đề filename

Có trường hợp file nằm trong bộ nhớ (ví dụ report nhỏ được tạo trước đó):

```java
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(bytes) {
    @Override
    public String getFilename() {
        return "report.txt";
    }
};

MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();
parts.add("file", resource);
```

Đây là snippet với imports `java.nio.charset.StandardCharsets`, `org.springframework.core.io.ByteArrayResource`, `Resource`.

`ByteArrayResource` mặc định có thể **không có filename**; nhiều server yêu cầu `Content-Disposition: form-data; name="file"; filename="..."` để bind vào file part. Override `getFilename()` khi hợp đồng đòi tên file.

**Memory caution:** `ByteArrayResource` giữ toàn bộ bytes trong heap; không phù hợp upload hàng GB. `InputStreamResource` cũng không phải thay thế vô điều kiện: thường non-repeatable, tên file có thể null và một số converters/request factories cần biết content length hay replay body. Chọn `FileSystemResource` cho file có thật hoặc streaming adapter được kiểm thử khi tải file lớn.

## 17. Form và multipart khác JSON body

Một lỗi thường thấy:

```java
client.post()
    .uri("/upload")
    .contentType(MediaType.APPLICATION_JSON)
    .body(parts);
```

Đây là **anti-pattern** nếu `parts` là `MultiValueMap<String,Object>` intended multipart. JSON converter không tự tạo `Content-Disposition` và boundary cho file.

Phân biệt:

| Cần gửi | Content-Type | Request body Java |
| --- | --- | --- |
| JSON DTO | `application/json` | `new CreateOrder(...)` |
| Form các ô đơn giản | `application/x-www-form-urlencoded` | `MultiValueMap<String,String>` |
| File + text + JSON parts | `multipart/form-data` | `MultiValueMap<String,Object>` |
| Binary đơn lẻ không multipart | `application/octet-stream` | `byte[]`/`Resource` theo writer |
| Query filters | Nằm trong URL | `UriBuilder.queryParam(...)`, không cần body |

Server Spring MVC có thể dùng `@RequestParam` để đọc form fields hoặc `@RequestPart` cho multipart JSON/file parts. Spring WebFlux server lại có form/multipart body APIs riêng. Client RestClient chỉ chịu trách nhiệm phát HTTP payload đúng contract; server framework có thể là Java, Node, Python hoặc hệ thống khác.

## 18. Tổng hợp nhanh RestClient, RestTemplate và JDK HttpClient

### RestClient (Spring 6.1+)

```java
Book book = client.get()
    .uri("/books/{id}", id)
    .retrieve()
    .body(Book.class);
```

### RestTemplate (giữ tương thích)

```java
RestTemplate restTemplate = new RestTemplate();

Book book = restTemplate.getForObject(
    "https://api.example.test/books/{id}",
    Book.class, id);
```

### Java 17 HttpClient (không có Spring converters)

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/books/42"))
    .GET().build();

HttpResponse<String> response =
    HttpClient.newHttpClient().send(
        request, HttpResponse.BodyHandlers.ofString());
```

Đây là **snippets** với `Book` record/`id` hoặc Java HTTP imports tương ứng. `HttpClient.send` là synchronous; muốn JSON DTO phải tự dùng JSON parser (ví dụ Jackson) và tự xây multipart/form encoding nếu không có Spring converters. Mẫu Java17 runnable không dùng mạng bên ngoài ở phần sau.

## 19. RestTemplate gửi form và multipart thế nào?

RestTemplate vẫn dùng `HttpMessageConverter` trong dòng Spring 6.x.

### Form-urlencoded

```java
MultiValueMap<String, String> form =
    new LinkedMultiValueMap<>();
form.add("name", "Linh");
form.add("tag", "java");
form.add("tag", "C++");

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

HttpEntity<MultiValueMap<String, String>> entity =
    new HttpEntity<>(form, headers);

FormReply reply = restTemplate.postForObject(
    "https://api.example.test/form",
    entity, FormReply.class);
```

### Multipart

```java
MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();
parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.MULTIPART_FORM_DATA);

HttpEntity<MultiValueMap<String, Object>> entity =
    new HttpEntity<>(parts, headers);

UploadReply reply = restTemplate.postForObject(
    "https://api.example.test/upload",
    entity, UploadReply.class);
```

Hai đoạn này là **snippets** cần `RestTemplate restTemplate`, response records và imports. RestTemplate dùng request `HttpEntity` ở top-level, còn RestClient tách `.headers(...)` và `.body(...)`. Không mang nguyên `RequestEntity`/`HttpEntity` từ RestTemplate nhét vào RestClient.body rồi mong RestClient hiểu top-level headers giống cũ.

### So sánh API

| Công việc | RestTemplate | RestClient |
| --- | --- | --- |
| GET URI template | `getForObject(url,Dto.class,vars)` | `get().uri(url,vars).retrieve().body(Dto.class)` |
| GET ResponseEntity | `getForEntity(...)` | `retrieve().toEntity(Dto.class)` |
| POST form/multipart | `postForObject(url,HttpEntity,Dto.class)` | `post().contentType(...).body(map).retrieve().body(Dto.class)` |
| Set request headers | `HttpEntity`/`RequestEntity` | `header/headers/accept/contentType` |
| Customize per response status | `ResponseErrorHandler` | `onStatus(...)` |
| Underlying HTTP transport | `ClientHttpRequestFactory` | `ClientHttpRequestFactory` |
| Async response publisher | Không | Không |

**Không trộn các object types** của MVC server (`MultipartFile` đại diện upload đã nhận) với client upload file (`Resource`). `MultipartFile` có thể xuất hiện trong HTTP service interface client API, nhưng với RestClient manual multipart body, dùng Resource/HttpEntity rõ ràng.

## 20. Xử lý HTTP response, lỗi và null body

RestClient `retrieve()` cung cấp response metadata/body:

```java
ResponseEntity<ItemView> result = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .toEntity(ItemView.class);

int status = result.getStatusCode().value();
ItemView body = result.getBody();
```

Đây là snippet. `getStatusCode()` là `HttpStatusCode`, không giả định luôn là enum `HttpStatus`. `getBody()` có thể null cho response không body.

Theo mặc định `retrieve()` có thể ném `RestClientResponseException`/subclasses khi server trả 4xx hoặc 5xx; các lỗi khác do transport/converter cũng có thể là `RestClientException`. Đừng nghĩ mọi exception đều có HTTP status: **connect timeout, DNS failure, TLS handshake** không có HTTP response từ server để đọc.

### Custom status handling

```java
ItemView item = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw new IllegalStateException(
                "Remote item not found");
        })
    .body(ItemView.class);
```

Đây là snippet cho một cách tùy chỉnh, không phải policy duy nhất. Đừng nuốt mọi 404 thành `null` rồi coi là thành công nếu API phải phân biệt not-found với upstream outage. Với 401/403, phải kiểm credentials và permission; với 429/503, có thể cần backoff; với lỗi format, inspect body có giới hạn và sanitize trước khi log.

### Timeout và status không giống nhau

HTTP 504 do gateway trả là một **response** (có status). Connect/read timeout ở client thường là **exception không có HTTP response**. Cùng một request POST có thể đã được remote xử lý dù client gặp timeout lúc chờ reply.

## 21. Timeout và ClientHttpRequestFactory

Đối với client đồng bộ, bắt buộc suy nghĩ về timeout và connection pool. Một ví dụ với Spring standard request factory:

```java
SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(3000);
requestFactory.setReadTimeout(5000);

RestClient client = RestClient.builder()
    .requestFactory(requestFactory)
    .baseUrl("https://api.example.test")
    .build();
```

Snippet cần import `org.springframework.http.client.SimpleClientHttpRequestFactory`. Hai mốc ở đây là **milliseconds** với Spring 6.x API. Connect timeout giới hạn bước kết nối, read timeout là thời gian chờ hoạt động đọc theo transport; **không phải một deadline tổng cho mọi thao tác DNS/TLS/upload/retry/response**.

Production có thể dùng Apache HttpComponents/Jetty/JDK client request factory tùy dependencies, connection pooling và proxy/TLS needs. Khi đổi transport, phải đọc cách cấu hình pool/connection-request timeout riêng của thư viện đó. Không chỉ tăng timeout lên 10 phút để che một upstream chậm.

### Hạn mức tải đồng thời

Nếu 200 server request threads cùng gọi RestClient rồi đợi 5 giây, cả 200 có thể bị chiếm. Cần:
- Đo p95/p99 outbound latency.
- Pool connection có giới hạn; tránh tạo client/connection pool per request.
- Bulkhead/concurrency quota với downstream dễ quá tải.
- Timeout, retry với backoff/jitter và circuit breaker tùy nghiệp vụ.
- Hạn mức upload file, response size và streaming readers.
- Quan sát tổng deadline từ caller/gateway tới các downstream.

Đừng tạo retry storm bằng cách retry đồng loạt một endpoint 503 đang bão hòa.

## 22. Retry, idempotency và bảo vệ dữ liệu

URI/query GET thường an toàn để retry theo HTTP semantics nếu endpoint thực hiện GET đúng (không mutate server state). POST gửi form/multipart có thể tạo đơn hàng, upload hoặc thanh toán, vì vậy **retry không được bật mù quáng**.

Các tình huống:

| Tình huống | Có thể retry? | Ghi chú |
| --- | --- | --- |
| Connect failure trước khi gửi HTTP | Có thể, nếu đánh giá an toàn | Vẫn cần kiểm request thực sự chưa tới server |
| GET timeout | Thường được cân nhắc | Chỉ nếu GET không có side effect quan trọng |
| POST timeout sau upload bytes | **Nguy hiểm** | Server có thể đã lưu file/commit |
| POST 409 conflict | Không tự retry | Cần domain conflict resolution |
| 429/503 | Theo Retry-After/backoff nếu phù hợp | Rate limit và server capacity |
| Multipart từ non-repeatable InputStreamResource | Retry có thể không khả thi | Body có thể đã tiêu thụ stream |
| Multipart từ FileSystemResource | Có thể mở lại file, nhưng operation vẫn có side effect | Dùng idempotency key nếu cần |

**Idempotency key** phải được server hỗ trợ, giữ kết quả bền vững và gắn với actor/request semantics. Một header tùy ý không tự ngăn duplicate uploads nếu server bỏ qua. Với upload lớn, cân nhắc resumable upload protocol hoặc presigned URLs thay vì POST multipart đồng bộ kéo dài.

### Data security

- Không log nguyên Authorization, Cookie, API keys, form passwords hoặc binary multipart content.
- Không trả raw response error chứa PII/token lên client.
- Không để client chỉ định URL bất kỳ nếu backend sẽ gọi RestClient theo URL đó (SSRF).
- Chặn redirects bất ngờ tới internal network tùy request factory/policy.
- Pin base host, allowlist scheme/host/port và không trộn URI raw do user gửi với trusted base URL.
- Kiểm TLS certificates/hostname verification; không tắt SSL verification để “sửa” lỗi.
- Validate file filename/path và kích thước trước khi gửi; filename nhận lại từ remote vẫn là untrusted metadata.
- Không gửi credentials sang host khác qua redirect không kiểm soát.
- Tôn trọng rate limits và authorization.

## 23. Bài tập runnable Spring Boot 3.2+ (server + RestClient)

Để kiểm chứng end-to-end, tạo **một ứng dụng Spring MVC nhỏ đóng vai server nhận request** và một bài integration test dùng `RestClient` làm **client đồng bộ** gửi request tới localhost. Cách này không phụ thuộc API công cộng, không cần token, không cần mock cả luồng multipart.

Yêu cầu Maven/Gradle:

- Java 17+.
- Spring Boot **3.2+** trong dòng 3.x.
- `spring-boot-starter-web`.
- `spring-boot-starter-test` (test scope).

Từ Spring Initializr có Maven wrapper, tạo các tệp:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  DemoController.java
src/test/java/com/example/demo/
  RestClientIntegrationTest.java
```

Cả ba file cùng package `com.example.demo`. Demo không cần database hoặc Spring Security; chỉ phản hồi lại giá trị đã parse để quan sát URI/query/form/multipart.

### 23.1. DemoApplication.java

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

### 23.2. DemoController.java

```java
package com.example.demo;

import java.io.IOException;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemReply item(
            @PathVariable String id,
            @RequestParam String q,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false)
                    List<String> tags) {

        return new ItemReply(id, q, page,
                tags == null ? List.of() : List.copyOf(tags));
    }

    @PostMapping(path = "/form",
                 consumes =
                   MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public FormReply form(
            @RequestParam String name,
            @RequestParam("tag") List<String> tags) {

        return new FormReply(name, List.copyOf(tags));
    }

    @PostMapping(path = "/upload",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public UploadReply upload(
            @RequestParam String description,
            @RequestPart("file") MultipartFile file,
            @RequestPart("meta") Meta meta) throws IOException {

        // Chỉ đọc metadata và độ dài, KHÔNG lưu file demo.
        return new UploadReply(
            description,
            file.getOriginalFilename(),
            file.getSize(),
            meta.source());
    }

    public record ItemReply(
        String id, String q, int page, List<String> tags) {}

    public record FormReply(
        String name, List<String> tags) {}

    public record Meta(String source) {}

    public record UploadReply(
        String description, String filename,
        long size, String source) {}
}
```

**Giải thích**: MVC controller nhận `@RequestParam` từ query (GET) hoặc body form-urlencoded (POST). `@RequestPart("file") MultipartFile` đại diện file nhận ở server; client gửi `FileSystemResource`. `@RequestPart("meta") Meta` decode JSON part bằng Jackson nhờ `Content-Type: application/json` riêng part.

Code nhận size từ MultipartFile, không lưu file. Demo sử dụng `throws IOException` dù method hiện không đọc file stream: có thể bỏ declaration nếu không cần; Java cho phép checked exception declaration dư. Trong production cần cấu hình file size limit, filename validation, virus scanning, storage permission và stream processing đúng.

## 24. RestClientIntegrationTest: URI template, query, form và multipart

Tệp `src/test/java/com/example/demo/RestClientIntegrationTest.java`:

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RestClientIntegrationTest {

    @LocalServerPort
    int port;

    private RestClient client() {
        DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory(
                "http://localhost:" + port);

        factory.setEncodingMode(
            DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return RestClient.builder()
            .uriBuilderFactory(factory)
            .build();
    }

    @Test
    void uriTemplateAndRepeatedQueryValues() {
        DemoController.ItemReply result = client().get()
            .uri(builder -> builder
                .path("/demo/items/{id}")
                .queryParam("q", "{q}")
                .queryParam("page", 2)
                .queryParam("tag", "{tag1}", "{tag2}")
                .build(Map.of(
                    "id", "SKU-42",
                    "q", "C++ & Java",
                    "tag1", "java",
                    "tag2", "spring web")))
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(DemoController.ItemReply.class);

        assertNotNull(result);
        assertEquals("SKU-42", result.id());
        assertEquals("C++ & Java", result.q());
        assertEquals(2, result.page());
        assertEquals(
            java.util.List.of("java", "spring web"),
            result.tags());
    }

    @Test
    void postsFormUrlencoded() {
        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();
        form.add("name", "Linh & An");
        form.add("tag", "java");
        form.add("tag", "C++");

        DemoController.FormReply reply = client().post()
            .uri("/demo/form")
            .contentType(
                MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .body(form)
            .retrieve()
            .body(DemoController.FormReply.class);

        assertNotNull(reply);
        assertEquals("Linh & An", reply.name());
        assertEquals(
            java.util.List.of("java", "C++"),
            reply.tags());
    }

    @Test
    void postsMultipartWithTextFileAndJsonPart(
            @TempDir Path tempDir) throws IOException {

        Path file = tempDir.resolve("sample.txt");
        Files.writeString(
            file, "hello", StandardCharsets.UTF_8);

        HttpHeaders jsonHeaders = new HttpHeaders();
        jsonHeaders.setContentType(
            MediaType.APPLICATION_JSON);

        HttpEntity<DemoController.Meta> metadata =
            new HttpEntity<>(
                new DemoController.Meta("draft"),
                jsonHeaders);

        MultiValueMap<String, Object> parts =
            new LinkedMultiValueMap<>();
        parts.add("description", "Demo document");
        parts.add("file", new FileSystemResource(file));
        parts.add("meta", metadata);

        DemoController.UploadReply reply = client().post()
            .uri("/demo/upload")
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .accept(MediaType.APPLICATION_JSON)
            .body(parts)
            .retrieve()
            .body(DemoController.UploadReply.class);

        assertNotNull(reply);
        assertEquals("Demo document",
                     reply.description());
        assertEquals("sample.txt", reply.filename());
        assertEquals(5L, reply.size());
        assertEquals("draft", reply.source());
    }
}
```

**Đây là Java test hoàn chỉnh dành cho project Boot 3.2+ đúng dependencies**, chưa phải kết quả test được chạy trong repository của người dùng. Test không dùng mock request builder mà chạy local HTTP server thực trên RANDOM_PORT, nhờ đó kiểm đồng thời URL encoding, form converter, multipart boundary/part headers và server parsing.

`DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES` là lựa chọn có chủ đích để `C++ & Java` và `spring web` được encode như **variable values**. Test kiểm dữ liệu được decode lại ở server, không dựa vào cách format URL theo thói quen.

### Chạy tests

macOS/Linux:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

Nếu chạy app trước:

```bash
./mvnw spring-boot:run
```

Mặc định server khi chạy độc lập ở `http://localhost:8080` nếu không đổi port. Tests dùng **RANDOM_PORT**, vì vậy không nên hardcode :8080 trong test.

### Kết quả mong đợi

| Test | Status và nội dung |
| --- | --- |
| `uriTemplateAndRepeatedQueryValues` | 200, ID SKU-42, q literal `C++ & Java`, page 2, 2 tags |
| `postsFormUrlencoded` | 200, name `Linh & An`, tags `java`, `C++` |
| `postsMultipartWithTextFileAndJsonPart` | 200, filename sample.txt, file size 5, source draft |

Các code tests assert domain data, không assert thứ tự JSON properties, multipart boundary tự sinh hoặc header casing.

## 25. Curl đối chiếu cùng các requests

Sau khi chạy `DemoApplication` trên port 8080, có thể đối chiếu request HTTP bằng curl. Nếu base port bị đổi, thay giá trị URI.

### GET URI/query

```bash
curl -i --get 'http://localhost:8080/demo/items/SKU-42' \
  --data-urlencode 'q=C++ & Java' \
  --data-urlencode 'page=2' \
  --data-urlencode 'tag=java' \
  --data-urlencode 'tag=spring web' \
  -H 'Accept: application/json'
```

`curl --get --data-urlencode` xây query, tránh bạn tự encode dấu `+`/`&`. Response JSON minh họa:

```json
{
  "id": "SKU-42",
  "q": "C++ & Java",
  "page": 2,
  "tags": ["java", "spring web"]
}
```

### Form-urlencoded

```bash
curl -i -X POST 'http://localhost:8080/demo/form' \
  --data-urlencode 'name=Linh & An' \
  --data-urlencode 'tag=java' \
  --data-urlencode 'tag=C++' \
  -H 'Accept: application/json'
```

`curl --data-urlencode` gửi form body, kèm Content-Type form phù hợp. Response:

```json
{"name":"Linh & An","tags":["java","C++"]}
```

### Multipart (file + JSON part)

Tạo `sample.txt` chứa năm bytes `hello` không có newline, rồi chạy:

```bash
curl -i -X POST 'http://localhost:8080/demo/upload' \
  -F 'description=Demo document' \
  -F 'file=@sample.txt;type=text/plain' \
  -F 'meta={"source":"draft"};type=application/json' \
  -H 'Accept: application/json'
```

Dự kiến:

```json
{
  "description": "Demo document",
  "filename": "sample.txt",
  "size": 5,
  "source": "draft"
}
```

**Mấu chốt:** `curl -F` và Spring multipart converter đều tự quản lý boundary. Không tự thêm `Content-Type: multipart/form-data` không có boundary khi dùng curl hoặc Spring; điều đó dễ làm server không parse được parts.

## 26. Test request generation không cần network thật

Khi chỉ muốn xác nhận request method/URI/headers/body converter, Spring Test cung cấp `MockRestServiceServer` để bind với `RestClient.Builder`.

Ví dụ test GET đơn giản:

```java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://api.example.test");

MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();

server.expect(requestTo(
        "https://api.example.test/items/SKU-42"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"id\":\"SKU-42\"}",
        MediaType.APPLICATION_JSON));

ItemView response = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .body(ItemView.class);

server.verify();
```

Đây là **snippet trong JUnit test method**, cần `ItemView`, `HttpMethod`, `MediaType` và static imports:

```java
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response
    .MockRestResponseCreators.withSuccess;
```

**Chú ý:** đoạn imports ở trên được bẻ dòng bằng Java syntax không hợp lệ nếu copy nguyên bản; hãy viết trên một dòng đầy đủ như `import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;` trong file thực. Các dòng trình bày nhằm minh họa namespace, không phải file runnable.

`MockRestServiceServer` hữu ích kiểm client logic không phụ thuộc network, nhưng **không thay thế** HTTP integration test với server thật cho multipart parsing, filename, charset, proxy, TLS, redirects và large upload. Test cần biết form-urlencoded request body là chuỗi bytes, còn multipart body có dynamic boundary; không hardcode boundary literal để assert.

## 27. Java 17 độc lập: form encoding và URI khác nhau

Đây là **một file JDK 17 có thể biên dịch/chạy mà không có Spring dependencies**, giúp thấy rõ `URLEncoder` tạo form-urlencoded representation.

Tệp `FormEncodingDemo.java`:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class FormEncodingDemo {

    private static String encode(String value) {
        return URLEncoder.encode(
            value, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String name = "Linh & An";
        String tag = "C++";

        String body = "name=" + encode(name)
            + "&tag=" + encode(tag);

        System.out.println(body);
        System.out.println(
            "Do not use form encoding for URI path");
    }
}
```

Chạy:

```bash
javac FormEncodingDemo.java
java FormEncodingDemo
```

Stdout **chính xác**:

```text
name=Linh+%26+An&tag=C%2B%2B
Do not use form encoding for URI path
```

Đây là mô hình giáo dục cho form encoding; khi dùng Spring RestClient hãy đưa `MultiValueMap` cho converter để không phải tự nối fields. Chương trình thuần JDK này không gửi request: ví dụ gọi HTTP sync thực đã có ở integration test của Spring Boot.

### Vì sao import URLEncoder nhưng không dùng cho path?

Trong form body, space được encode thành `+` theo form convention. URI path cần xử lý slash/path segment riêng; nếu dùng `URLEncoder` trực tiếp, giá trị có khoảng trắng có thể không được server hiểu như bạn muốn. Spring URI template builder có cơ chế đúng cho path/query variables.

## 28. Tình huống nâng cao: upload metadata và filename

Server đôi khi yêu cầu multipart structure:

```http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="meta"
Content-Type: application/json

{"source":"draft"}
--...
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain

hello
--...--
```

Có một số chi tiết cần xác minh ở API contract:

1. Tên part phải đúng: `file` khác `upload`.
2. Text field và JSON part khác nhau: `description` nhận String, `meta` nhận DTO.
3. `Content-Type` từng part cần đúng để server decoder chọn converter.
4. Filename do FileSystemResource/Resource#getFilename cung cấp; với in-memory resource có thể cần override.
5. Boundary của request không được hardcode cùng value ở nhiều client.
6. File bytes có thể chứa mọi ký tự nhị phân, không chuyển qua `String`/UTF-8 rồi tự ghép boundary.
7. Không dùng raw path user nhập làm file system path trên client nếu không qua allowlist/authorization.
8. Nếu file có size lớn, kiểm HTTP transport có thể streaming và policies về retry/body repeatability.
9. Một phần thành công rồi timeout không đồng nghĩa remote đã rollback file.
10. multipart/mixed và multipart/form-data không thay được cho nhau nếu server contract phân biệt.

### Chọn Resource

| Resource | Nguồn | Cảnh báo |
| --- | --- | --- |
| `FileSystemResource` | File trên disk | File có thể đổi giữa lúc kiểm và gửi; kiểm permission/size |
| `ByteArrayResource` | byte[] in memory | Không có filename mặc định, giữ toàn bộ bytes |
| `InputStreamResource` | InputStream đã mở | Non-repeatable; có thể không có filename/size và gây khó khi retry |
| `UrlResource` | Remote URL | Không dùng URL user nhập tùy tiện; SSRF và fetch ngoài ý muốn |
| `ClassPathResource` | Resource trong classpath | Phù hợp fixture nhỏ; filename/stream metadata tùy resource |

Trên production, bảo vệ thời điểm mở tệp, chủ sở hữu dữ liệu, giới hạn kích thước và tạo file tạm trong thư mục an toàn. Đừng giữ một `InputStream` mở qua nhiều requests hoặc threads mà không có lifecycle.

## 29. HTTP status khi request sai

Các lỗi thường gặp:

| Status/exception | Vì sao xuất hiện |
| --- | --- |
| 400 Bad Request | Thiếu form field, type conversion sai, malformed multipart |
| 401 Unauthorized | Thiếu/không hợp lệ authentication |
| 403 Forbidden | Có identity nhưng không đủ quyền |
| 404 Not Found | URL/path variable không map resource |
| 405 Method Not Allowed | Gửi POST tới route GET hoặc ngược lại |
| 406 Not Acceptable | `Accept` không tương thích representation |
| 409 Conflict | Operation đụng state/resource version |
| 413 Content Too Large | Payload/upload vượt limit |
| 415 Unsupported Media Type | Gửi body/part Content-Type không được hỗ trợ |
| 422 Unprocessable Content | Body syntactically đúng nhưng domain validation không chấp nhận, nếu API chọn status này |
| 429 Too Many Requests | Rate/quota limit |
| 500/502/503/504 | Server, gateway hoặc upstream lỗi/tạm quá tải |
| `ResourceAccessException` | I/O/connect/read timeout, DNS/TLS... ở RestClient |
| `RestClientResponseException` | HTTP response lỗi và RestClient chọn throw |

Không phải mọi hệ thống dùng đúng status giống nhau; verify dựa trên server API contract và tests. Mã lỗi 4xx là **response từ server**, còn `ResourceAccessException` có thể xảy ra khi chưa nhận HTTP response nào.

### Tại sao lỗi media type hay gặp?

- Gửi multipart nhưng quên boundary.
- Đặt Content-Type application/json cho form map.
- Gửi text/plain body vào server chỉ nhận JSON.
- Dùng JSON part nhưng không đặt part-level Content-Type.
- Truyền String body JSON có ký tự escape sai, trong khi đáng lẽ gửi DTO và để Jackson encode.
- Cho rằng `Accept` dùng để xác định loại request body.

## 30. Lỗi phổ biến khi viết client

1. **Dùng Spring Boot 3.0/3.1 nhưng gọi RestClient**: API ra mắt từ Spring Framework 6.1 (Boot 3.2+).
2. **Import `WebClient` nhưng mong đồng bộ**: WebClient là reactive, không thay RestClient một cách máy móc.
3. **Nối query bằng string interpolation**: `+`/`&`/`#` phá URI.
4. **Dùng URLEncoder cho path segment**: encoding form khác URI path.
5. **Double encode input đã có `%2F`**: server nhận sai value.
6. **Dùng default/custom URI factory mà không test encoded special chars**.
7. **Nhầm `.uri(URI)` với `.uri(String, vars)`**: cái trước là URI đã build.
8. **Đưa query vào body form hoặc form fields vào query mà không theo API contract**.
9. **Dùng Map<String,String> cho repeated query/form fields**: mất nhiều values.
10. **Không phân biệt absent param và empty string**: default/validation bị sai.
11. **Đặt Content-Type trong client theo format response**: nhầm `Accept`.
12. **Gửi MultiValueMap<String,Object> multipart nhưng set application/json**.
13. **Tự sinh multipart boundary mà không đồng bộ header/body**.
14. **Tự ghép multipart byte stream qua String**: hỏng binary file.
15. **Dùng ByteArrayResource không filename khi server bắt buộc filename**.
16. **Dùng InputStreamResource non-repeatable rồi retry POST**.
17. **Không set part JSON Content-Type khiến server parse sai DTO**.
18. **Tạo HTTP client/request factory cho mỗi server request**: connection pool overhead.
19. **Không có connect/read timeout**: threads chờ lâu vô hạn.
20. **Retry POST/multipart sau timeout mà không idempotency**: trùng upload/thanh toán.
21. **Gọi RestClient trực tiếp trên Netty event loop**: blocking.
22. **Tin `retrieve().body(...)` luôn trả non-null**: no body/204 có thể null.
23. **Catch mọi RestClientException rồi trả HTTP 200**: giấu outage.
24. **Log nguyên Authorization/form passwords/file bytes**: lộ secrets.
25. **Để user chọn absolute URL tùy ý**: SSRF.
26. **Dựa vào header Location/redirect từ remote không allowlist**: có thể leak credentials.
27. **Cho rằng POST form là JSON vì request object là POJO**: cần đúng converter.
28. **Không kiểm repeated field order** khi server business contract phụ thuộc.
29. **Dùng MultipartFile làm client upload Resource**: nhầm server và client APIs.
30. **Test chỉ với mock HTTP, bỏ qua server multipart parser**.
31. **Hardcode dynamic boundary trong assertions**: tests flaky.
32. **Không validate filenames/kích thước trước upload**.
33. **Phụ thuộc file tồn tại theo relative path của IDE**: tests khác môi trường fail.
34. **Tin RestTemplate đã biến mất trong Spring 6.2**: còn API, migrations phụ thuộc version.
35. **Tin RestClient gửi đi trên thread nền tự động**: client synchronous chặn caller.
36. **Gọi POST form-urlencoded nhưng thiếu Content-Type**: converter/server có thể hiểu sai.
37. **Dùng raw URI query chứa `+` không encode**: server có thể đổi thành space.
38. **Không kiểm charset/Unicode của form field**: tiếng Việt có thể lỗi encoding.
39. **Không tách 400 validation và 415 media mismatch**: client khó sửa request.
40. **Đọc file upload vào byte[] khổng lồ**: memory pressure.

## 31. Checklist triển khai production

### URI và query

- [ ] Dùng template variables/UriBuilder thay vì nối URL raw?
- [ ] URI variable chứa `&`, `+`, khoảng trắng, slash và Unicode được test?
- [ ] Không truyền dữ liệu đã encode vào formatter encode lần nữa?
- [ ] DefaultUriBuilderFactory/config encoding mode đã được ghi rõ nếu cần?
- [ ] Repeated query params và thiếu/rỗng được xử lý theo API contract?
- [ ] Base URL/scheme/host/port được allowlist; không SSRF từ user input?
- [ ] Không đưa secrets vào query URL/logs nếu có lựa chọn khác?

### Body và converters

- [ ] `Content-Type` biểu thị đúng request body?
- [ ] `Accept` biểu thị đúng representation response mong muốn?
- [ ] `MultiValueMap<String,String>` cho form-urlencoded có repeated values?
- [ ] `MultiValueMap<String,Object>` và Resource/HttpEntity cho multipart?
- [ ] File parts có đúng filename, size, media type và tên part?
- [ ] JSON parts có part-level `Content-Type`?
- [ ] Không tự quản lý multipart boundary?
- [ ] Multipart large files có size quota và streaming/repeatability policy?
- [ ] Charset/Unicode/form encoding được test?

### Độ tin cậy

- [ ] Connect/read timeout có giá trị rõ ràng và đo thực tế?
- [ ] Client/request factory/connection pools dùng lại có kiểm soát?
- [ ] Retry có phân biệt GET/POST và idempotency keys?
- [ ] Phân loại HTTP error vs transport error?
- [ ] Response DTO có nullable/no-body semantics rõ?
- [ ] Không block reactive event-loop nếu ứng dụng là WebFlux?
- [ ] 429/503 có backoff/jitter và circuit-breaker/bulkhead policy?
- [ ] Không để client tự follow redirects không an toàn?
- [ ] Không log secrets/file contents/PII?

### Tests và vận hành

- [ ] Integration test URI template + special characters + repeated query?
- [ ] Form-urlencoded test có dấu cộng/ampersand/Unicode?
- [ ] Multipart test gửi FileSystemResource + JSON HttpEntity part?
- [ ] Test 400/415/413 và error body đủ an toàn?
- [ ] Test timeout, connection reset, invalid TLS và rate-limit trong staging?
- [ ] Test qua gateway/proxy thật nếu encoding/redirect có khả năng bị thay đổi?
- [ ] File upload/response size limits và metrics theo downstream được bật?
- [ ] JUnit không phụ thuộc cổng cố định hoặc file nằm ngoài temp dir?

## 32. Câu hỏi tự kiểm tra

**1.** RestClient có phải asynchronous HTTP client không?

**Đáp án:** Không. RestClient đồng bộ, chặn thread gọi tới khi có response/error. WebClient mới là reactive/non-blocking.

**2.** Tại sao `"/items/" + id` kém an toàn hơn `.uri("/items/{id}", id)`?

**Đáp án:** URI template expansion giúp encode value theo ngữ cảnh, còn nối raw có thể biến characters thành path/query delimiters.

**3.** Khi query cần value `C++ & Java`, nên làm gì?

**Đáp án:** Dùng URI builder với template variables và encoding mode phù hợp (ví dụ TEMPLATE_AND_VALUES), kiểm value được decode đúng ở server.

**4.** URLEncoder có phù hợp cho URI path không?

**Đáp án:** Không. Nó encode application/x-www-form-urlencoded, trong đó space thành `+`, khác URI path semantics.

**5.** Query param và form field có cùng vị trí trong HTTP request không?

**Đáp án:** Không. Query nằm trên URL; form-urlencoded là request body.

**6.** Vì sao `MultiValueMap` hơn `Map<String,String>` cho form?

**Đáp án:** MultiValueMap giữ nhiều giá trị cùng tên như `tag=java&tag=webflux`.

**7.** Để gửi form body cần Content-Type nào?

**Đáp án:** `application/x-www-form-urlencoded`.

**8.** Để gửi file + metadata cùng request, nên dùng representation nào?

**Đáp án:** `multipart/form-data` với `MultiValueMap<String,Object>` chứa Resource, text field và HttpEntity cho part custom headers.

**9.** Multipart boundary nên do ai tạo?

**Đáp án:** HTTP message converter/RestClient; ứng dụng không tự hardcode header và body separators.

**10.** Vì sao dùng FileSystemResource cho file part?

**Đáp án:** Nó cung cấp stream và filename từ tệp trên disk để converter tạo Content-Disposition phù hợp.

**11.** ByteArrayResource có chắc gửi filename không?

**Đáp án:** Không. Có thể cần override getFilename hoặc bọc headers tương ứng.

**12.** HttpEntity chứa JSON part khác top-level HttpEntity ở RestTemplate thế nào?

**Đáp án:** Trong multipart map, HttpEntity đại diện body/headers **của part**. Top-level RestTemplate HttpEntity đại diện body/headers toàn request.

**13.** Khi server trả 204, `retrieve().body(Dto.class)` có chắc khác null không?

**Đáp án:** Không. HTTP response có thể không có body; phải xử lý null/ResponseEntity nếu cần status.

**14.** POST upload timeout thì có chắc server chưa lưu file không?

**Đáp án:** Không. Server có thể đã nhận/commit trước khi client mất response; retry cần idempotency.

**15.** Spring Boot 3.0 có RestClient không?

**Đáp án:** Chưa có trong Spring Framework 6.0 mặc định của Boot 3.0; dùng Boot 3.2+ hoặc phù hợp Framework 6.1+ để có RestClient.

**16.** Có cần tự chuyển multipart FileSystemResource thành byte[] trước không?

**Đáp án:** Không. Message converter có thể dùng Resource; giữ bytes toàn bộ trong heap thường không cần thiết.

**17.** Nếu Content-Type của một JSON part bị đặt text/plain thì chuyện gì có thể xảy ra?

**Đáp án:** Server không chọn đúng JSON decoder để bind DTO, gây lỗi request/part conversion; đặt HttpEntity với application/json.

**18.** Trong WebFlux server, có nên gọi RestClient đồng bộ trên Netty event-loop không?

**Đáp án:** Không. Nó có thể block loop; chọn WebClient reactive hoặc bridge blocking work sang bounded scheduler khi bắt buộc.

## 33. Nguồn tham khảo

- Spring Framework 6.2 — REST Clients, RestClient/RestTemplate/HTTP Interface và Multipart: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework 6.2 — URI Links, UriBuilder/encoding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html
- Spring Framework — `DefaultUriBuilderFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html
- Spring Framework — `UriComponentsBuilder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html
- Spring Framework — `RestClient` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html
- Spring Framework — `RestTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html
- Spring Framework — `FormHttpMessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/converter/FormHttpMessageConverter.html
- Spring Framework — `HttpEntity` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/HttpEntity.html
- Spring Framework — `FileSystemResource` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/FileSystemResource.html
- Spring Framework — `MockRestServiceServer` tests: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html
- Spring Framework 6.2 — Spring MVC Multipart forms: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Java 17 — `URLEncoder` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java 17 — `HttpClient` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- HTTP Semantics RFC 9110 — Content-Type, Accept, methods, status codes: https://www.rfc-editor.org/rfc/rfc9110.html
