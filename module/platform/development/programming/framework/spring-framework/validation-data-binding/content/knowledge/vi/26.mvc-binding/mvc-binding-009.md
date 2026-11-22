# @RequestParam, @PathVariable và @RequestHeader với chuyển đổi kiểu trong Spring MVC

Trong Spring MVC, một HTTP request có thể mang dữ liệu ở **query string**, **form body**, **URI path** hoặc **HTTP headers**. Controller không nhất thiết phải nhận các dữ liệu này dưới dạng `String` rồi tự parse: Spring có những annotation tương ứng để chọn **nguồn dữ liệu**, xác định **tên đầu vào**, xử lý **thiếu giá trị / giá trị mặc định**, và dùng **cơ chế type conversion** để đưa chuỗi HTTP về đúng kiểu Java.

Ba annotation trọng tâm là:

- `@RequestParam`: lấy **request parameter** của Servlet request, thường là query parameter hoặc field của form URL-encoded.
- `@PathVariable`: lấy **biến trong URI template** đã được route handler match.
- `@RequestHeader`: lấy **một HTTP request header** hoặc tập headers.

Cả ba có thể dùng cho `String`, số, enum và nhiều kiểu khác nếu `ConversionService` / formatter phù hợp đã được đăng ký. Ví dụ `?page=3` có thể trở thành `int page = 3`, `/orders/42` trở thành `long id = 42`, hoặc header `X-Retry-Count: 2` trở thành `int retryCount = 2`.

**Phạm vi:** bài này giải thích Spring MVC trên **Servlet stack**, sử dụng Java 17+ và ví dụ Spring Boot 3.x. Không đồng nhất với Spring WebFlux: ở WebFlux, `@RequestParam` chủ yếu đọc query parameters, trong khi ở Servlet MVC khái niệm request parameter còn bao gồm dữ liệu form.

## 1. So sánh ba nguồn dữ liệu

Một request mẫu:

~~~http
GET /api/items/42?page=3&tag=java&tag=spring HTTP/1.1
Host: localhost:8080
X-Client-Id: mobile
X-Retry-Count: 2
~~~

Controller có thể khai báo:

~~~java
@GetMapping("/api/items/{itemId}")
public Object find(
        @PathVariable("itemId") long itemId,
        @RequestParam("page") int page,
        @RequestParam("tag") List<String> tags,
        @RequestHeader("X-Client-Id") String clientId,
        @RequestHeader("X-Retry-Count") int retryCount) {
    // Sử dụng các tham số đã được Spring resolve và convert.
    return ...;
}
~~~

Đây là snippet minh họa chữ ký method, **không phải chương trình Java độc lập**. Trong project hoàn chỉnh ở phần 6, mỗi trường có giá trị:

| Đối số Java | Nguồn HTTP | Giá trị Java sau chuyển đổi |
|---|---|---|
| `long itemId` | `/api/items/42`, URI template `{itemId}` | `42L` |
| `int page` | `?page=3` | `3` |
| `List<String> tags` | `tag=java&tag=spring` | `["java","spring"]` |
| `String clientId` | Header `X-Client-Id: mobile` | `"mobile"` |
| `int retryCount` | Header `X-Retry-Count: 2` | `2` |

Ba annotation **không phải là ba cách viết tương đương**. Chúng cùng tận dụng các thành phần chuyển đổi kiểu của Spring nhưng chọn **vị trí input khác nhau**. Một URL `/api/items/42?page=3` không tự biến `42` thành `@RequestParam("itemId")` và cũng không biến `page` thành `@PathVariable("page")`.

### Quy tắc chọn annotation

| Tình huống | Lựa chọn | Vì sao? |
|---|---|---|
| ID của tài nguyên trong URL, ví dụ `/users/42` | `@PathVariable` | Tài nguyên được nhận diện bởi cấu trúc URI |
| Bộ lọc, trang, thứ tự sắp xếp: `?page=2&sort=recent` | `@RequestParam` | Tham số điều chỉnh cách truy xuất/danh sách |
| Form HTML gửi `application/x-www-form-urlencoded` | `@RequestParam` cho vài field hoặc `@ModelAttribute` cho DTO | Form fields thuộc Servlet request parameters |
| Giá trị do giao thức/client gửi trong request headers | `@RequestHeader` | Không phải query/form/path |
| Body JSON `{"name":"A"}` | `@RequestBody` | JSON cần HTTP message conversion, không phải query binding |
| Đọc toàn bộ các key query/form | `@RequestParam Map` hoặc `MultiValueMap` không chỉ định tên | Đọc tập parameter thay vì một key |
| Đọc toàn bộ HTTP headers | `@RequestHeader HttpHeaders` | Xử lý tập header đầy đủ |
| Tập trường nghiệp vụ phức tạp, cần validation DTO | `@ModelAttribute` (form) hoặc `@RequestBody` (JSON) | Tránh chữ ký handler quá dài |

## 2. `@RequestParam`: query parameters và form parameters

### 2.1. Lấy đúng tên parameter

~~~java
@GetMapping("/search")
public String search(
        @RequestParam("term") String keyword,
        @RequestParam("page") int page) {
    return keyword + ":" + page;
}
~~~

Với `GET /search?term=spring&page=2`, Spring gán `keyword = "spring"` và `page = 2`. Tên HTTP là `term` dù tên biến Java là `keyword`, vì annotation đã chỉ định tên. Khai báo rõ tên bằng `@RequestParam("term")` giúp code độc lập hơn với việc compiler có bật `-parameters` hay không.

Annotation có hai tên thuộc tính tương đương về ý nghĩa: `value` và `name`. Các cách sau tương đương:

~~~java
@RequestParam("page") int page
@RequestParam(name = "page") int page
@RequestParam(value = "page") int page
~~~

Các dòng trên là **các khai báo tham số minh họa**, không đứng riêng trong file Java ngoài method signature.

Trong Spring MVC, `@RequestParam` nhận Servlet request parameters. Nguồn này thường bao gồm:

- Query: `GET /search?page=2`.
- Form URL-encoded: `POST /search` với body `page=2` và Content-Type `application/x-www-form-urlencoded`.
- Multipart form parameters, khi multipart processing được cấu hình.

Không xem `@RequestParam` là annotation đọc JSON body. Với JSON, dùng `@RequestBody` và DTO phù hợp.

### 2.2. `required`, `Optional` và `defaultValue`

Mặc định `@RequestParam` **bắt buộc** (`required=true`):

~~~java
@GetMapping("/required")
public String required(@RequestParam("q") String q) {
    return q;
}
~~~

Request không chứa `q` thường bị Spring MVC từ chối với HTTP 400 trước khi handler chạy, điển hình qua `MissingServletRequestParameterException`. Nếu giá trị cần là tùy chọn:

~~~java
@GetMapping("/optional")
public String optional(
        @RequestParam(name = "q", required = false)
        String q) {
    return q == null ? "không có" : q;
}
~~~

Hoặc dùng `Optional`:

~~~java
@GetMapping("/optional-wrapper")
public String optionalWrapper(
        @RequestParam("q") java.util.Optional<String> q) {
    return q.orElse("không có");
}
~~~

`Optional<String>` giúp thể hiện rõ ràng trường có thể không được gửi. Với kiểu số, tránh khai báo `int page` cùng `required=false` mà không có default: kiểu nguyên thủy `int` không chứa được `null`. Dùng `Integer`, `Optional<Integer>` hoặc một default hợp lệ.

Cách phổ biến cho pagination:

~~~java
@GetMapping("/items")
public String items(
        @RequestParam(name = "page", defaultValue = "1")
        int page) {
    return "page=" + page;
}
~~~

`defaultValue = "1"` mang hai hệ quả:

1. Khi thiếu parameter `page`, Spring dùng chuỗi mặc định `"1"` rồi **convert thành `int`**.
2. `defaultValue` mặc nhiên làm `required=false`; mặc định cũng được áp dụng cho giá trị chuỗi rỗng trong cơ chế request-param resolution.

Vì vậy `GET /items` và `GET /items?page=` cùng nhận `page = 1` trong cấu hình thông dụng. Tuy nhiên `GET /items?page=abc` **không** dùng lại mặc định: input có mặt nhưng chuyển kiểu thất bại, thường dẫn đến HTTP 400.

**Đừng nhầm `required=false` với quy tắc validation.** Nó chỉ nói rằng input HTTP được phép thiếu; `@Min(1)` hoặc constraint khác mới diễn đạt quy tắc miền của con số sau khi chuyển kiểu.

### 2.3. Nhiều giá trị cho cùng một key

~~~http
GET /search?tag=java&tag=spring&tag=backend HTTP/1.1
Host: localhost:8080
~~~

Controller:

~~~java
@GetMapping("/search")
public List<String> search(
        @RequestParam("tag") List<String> tags) {
    return tags;
}
~~~

Spring có thể resolve thành danh sách theo dữ liệu lặp lại từ cùng key. Có thể dùng `String[]`, `List<String>`, hoặc collection của các kiểu chuyển đổi được. Một số converter cũng xử lý chuỗi phân tách bằng dấu phẩy khi phù hợp, nhưng đừng tự giả định dữ liệu client luôn giữ ý nghĩa đồng nhất giữa “lặp key” và “một key có dấu phẩy”: hãy quy định API contract và kiểm thử đúng dạng input.

Nếu cần **toàn bộ request parameters** mà không biết trước tên:

~~~java
@GetMapping("/debug-params")
public Map<String, String> oneValuePerKey(
        @RequestParam Map<String, String> params) {
    return params;
}
~~~

~~~java
@GetMapping("/debug-multiple")
public org.springframework.util.MultiValueMap<String, String>
        allValues(@RequestParam
        org.springframework.util.MultiValueMap<String, String> params) {
    return params;
}
~~~

Khi `@RequestParam` **không chỉ định tên** và tham số là `Map` hoặc `MultiValueMap`, Spring gom các request parameter names vào map. `Map<String,String>` phù hợp khi chỉ quan tâm một giá trị mỗi key; `MultiValueMap` giữ được nhiều giá trị cho cùng một key.

Đây là các handler **minh họa**; không đưa trực tiếp vào controller demo nếu không cần. Tránh dùng map không giới hạn làm nguồn cập nhật trực tiếp entity hoặc audit log chứa thông tin nhạy cảm.

### 2.4. Ngầm định request param đối với simple types

Trong Spring MVC, một handler argument kiểu đơn giản (theo tiêu chí `BeanUtils.isSimpleProperty`) chưa được một resolver khác xử lý có thể được coi như `@RequestParam` **ngay cả khi không viết annotation**. Ví dụ:

~~~java
@GetMapping("/implicit")
public String implicit(String term) {
    return term;
}
~~~

Tuy vậy, **nên viết `@RequestParam("term")` tường minh** trong tài liệu, API public và codebase lớn. Nó làm rõ nguồn dữ liệu, bắt buộc/tùy chọn, default, và tránh phụ thuộc vào metadata tên tham số sau biên dịch.

## 3. `@PathVariable`: chuyển biến URI thành kiểu Java

### 3.1. Chỉ lấy được biến có trong URI template

Ví dụ route:

~~~java
@GetMapping("/orders/{orderId}")
public String detail(
        @PathVariable("orderId") long id) {
    return "order=" + id;
}
~~~

`GET /orders/125` → `id == 125L`. Cần phân biệt:

- `/orders/125` là path phù hợp template.
- `/orders/abc` thường vẫn phù hợp template `{orderId}` ở bước routing, nhưng chuyển `abc` thành `long` **thất bại**; lỗi có thể thành HTTP 400.
- `/orders` **không phù hợp** template có segment `{orderId}`, nên thông thường không có handler match và trả 404. `required=false` trên `@PathVariable` không tự tạo route mới cho URL thiếu segment.

Một số API viết cả hai route khi thực sự cần hỗ trợ “có và không có ID”:

~~~java
@GetMapping({"/orders", "/orders/{orderId}"})
public String optionalId(
        @PathVariable(name = "orderId", required = false)
        Long orderId) {
    return orderId == null ? "all" : "one=" + orderId;
}
~~~

Đây là snippet minh họa riêng. Dùng wrapper `Long` thay cho primitive `long` vì khi route không có `orderId`, giá trị có thể là `null`. Với API REST, thường nên có hai handler rõ ràng `GET /orders` và `GET /orders/{id}` để tách ý nghĩa collection và resource.

### 3.2. Tên biến URI và tên parameter Java

~~~java
@GetMapping("/products/{sku}")
public String product(@PathVariable("sku") String code) {
    return code;
}
~~~

URI name là `sku`, còn tên argument là `code`. Đừng trông chờ Spring tự đoán rằng hai tên khác nhau có liên quan; chỉ định `@PathVariable("sku")`.

Một số project có thể bỏ tên trong annotation nếu parameter Java trùng tên URI variable và compiler giữ metadata `-parameters`. Tuy nhiên, việc ghi tên tường minh giảm phụ thuộc cấu hình build và giúp người đọc nhìn đúng contract.

### 3.3. Ràng buộc pattern URL và lỗi chuyển kiểu

Route có thể dùng pattern:

~~~java
@GetMapping("/orders/{orderId:\\d+}")
public String numericOrder(
        @PathVariable("orderId") long orderId) {
    return "order=" + orderId;
}
~~~

Trong Java string literal của annotation, regex `\d+` cần escape thành `\\d+` như đoạn code. Pattern này **chỉ match đoạn URL chứa chữ số**, do đó `/orders/abc` có thể bị loại ở bước route matching thay vì được chuyển kiểu rồi báo mismatch.

Một route pattern không thay thế quy tắc nghiệp vụ. `/orders/0` vẫn có thể match `\\d+` và convert sang `0L`; muốn cấm ID 0, thêm kiểm tra nghiệp vụ/Bean Validation phù hợp.

### 3.4. Nhiều URI variables và map

~~~java
@GetMapping("/shops/{shopId}/products/{productId}")
public String product(
        @PathVariable("shopId") long shopId,
        @PathVariable("productId") long productId) {
    return shopId + ":" + productId;
}
~~~

Nếu muốn lấy mọi template variables:

~~~java
@GetMapping("/shops/{shopId}/products/{productId}")
public Map<String, String> pathMap(
        @PathVariable Map<String, String> variables) {
    return variables;
}
~~~

`@PathVariable Map` **không có tên cụ thể** cho phép gom toàn bộ URI template variables. Các giá trị trong map là dạng chuỗi, trong khi các tham số `long` riêng lẻ có conversion. Map không tự đảm bảo rằng các biến đã được validate về quyền truy cập; ID từ URL vẫn là input không tin cậy.

### 3.5. UUID, enum và kiểu đặc biệt

~~~java
@GetMapping("/documents/{id}")
public String document(
        @PathVariable("id") java.util.UUID id) {
    return id.toString();
}
~~~

Với URI chứa UUID theo cú pháp hợp lệ, Spring conversion system có thể tạo `UUID`. Một chuỗi không parse được thường dẫn đến conversion error thay vì giá trị `UUID` tùy ý.

Có thể dùng `enum`:

~~~java
public enum OrderState {
    NEW, PAID, CANCELLED
}

@GetMapping("/orders/by-state/{state}")
public String byState(
        @PathVariable("state") OrderState state) {
    return state.name();
}
~~~

Các snippet là các ví dụ trong controller riêng; định nghĩa enum nên đặt trong file `OrderState.java` hoặc nested enum hợp lệ. Converter mặc định từ `String` sang `Enum` thường dựa trên **tên enum**, không tự cho phép chữ thường/alias theo ý muốn. Nếu contract yêu cầu `paid` tương đương `PAID`, định nghĩa converter rõ ràng thay vì dựa vào ngầm định.

## 4. `@RequestHeader`: chuyển HTTP header thành method argument

### 4.1. Lấy một header cụ thể

Request có:

~~~http
GET /status HTTP/1.1
Host: localhost:8080
X-Client-Id: mobile
X-Retry-Count: 2
~~~

Controller:

~~~java
@GetMapping("/status")
public String status(
        @RequestHeader("X-Client-Id") String clientId,
        @RequestHeader("X-Retry-Count") int retryCount) {
    return clientId + ":" + retryCount;
}
~~~

`X-Client-Id` trở thành `String` và `X-Retry-Count` được chuyển sang `int`. Header names trong HTTP **không phân biệt hoa/thường**, nên `x-client-id` cũng là tên header tương ứng, dù trong code thường viết một dạng chuẩn dễ đọc.

Giống `@RequestParam`, `@RequestHeader` có `required=true` theo mặc định; có thể dùng `required=false`, `Optional<T>` hoặc `defaultValue`.

~~~java
@GetMapping("/status")
public String status(
        @RequestHeader(
            name = "X-Retry-Count",
            defaultValue = "0") int retryCount) {
    return "retry=" + retryCount;
}
~~~

Khi header thiếu, `retryCount == 0`. Nếu header tồn tại nhưng chứa `not-a-number`, chuyển đổi sang `int` thất bại; default **không phải** cách im lặng bỏ qua giá trị sai kiểu.

### 4.2. Header có nhiều giá trị, list và media type

Nhiều header có thể chứa danh sách các token được phân tách bằng dấu phẩy, ví dụ:

~~~http
Accept: application/json, text/plain
~~~

Spring hỗ trợ chuyển một số header dạng comma-separated thành `String[]`/`List<String>` khi conversion phù hợp:

~~~java
@GetMapping("/accepts")
public List<String> accepts(
        @RequestHeader("Accept") List<String> accept) {
    return accept;
}
~~~

Đây là snippet minh họa. Nếu cần phân tích đúng **ngữ nghĩa HTTP media types** với trọng số `q`, dùng các lớp chuyên biệt như `MediaType`/`HttpHeaders` hoặc nội dung negotiation framework thay vì tự chia chuỗi dựa trên dấu phẩy một cách đơn giản. Một số header có grammar phức tạp, không thể áp quy tắc “split bằng dấu phẩy” cho mọi loại.

### 4.3. Đọc tất cả headers

~~~java
@GetMapping("/all-headers")
public Map<String, String> allHeaders(
        @RequestHeader Map<String, String> headers) {
    return headers;
}
~~~

Hoặc bảo toàn nhiều giá trị:

~~~java
@GetMapping("/all-headers")
public org.springframework.http.HttpHeaders allHeaders(
        @RequestHeader
        org.springframework.http.HttpHeaders headers) {
    return headers;
}
~~~

Trong ví dụ thứ hai, `HttpHeaders` có API truy cập header thuận tiện, chẳng hạn `getFirst("X-Client-Id")`. `@RequestHeader` không có tên kết hợp `Map`, `MultiValueMap` hoặc `HttpHeaders` giúp lấy tập headers. Hai snippet có cùng route `/all-headers` nên là **các lựa chọn thay thế**, không thêm cả hai method vào một controller.

Không trả toàn bộ headers về client trong production để debug một cách vô điều kiện: cookie, authorization token và các header hạ tầng có thể chứa dữ liệu nhạy cảm.

### 4.4. Header tùy chọn và bảo mật

Một custom header `X-User-Id`, `X-Role` hoặc `X-Admin` **không đáng tin chỉ vì đến qua `@RequestHeader`**. Client HTTP thường có thể tự gửi header tùy ý. Xác thực và phân quyền phải dùng cơ chế security/trusted gateway phù hợp; nếu gateway gắn header người dùng, phải có đường bảo đảm rằng client không thể giả mạo hoặc vượt qua gateway.

`@RequestHeader` chỉ đọc và chuyển giá trị, **không tự xác thực chữ ký, quyền hay nguồn gốc header**.

## 5. Type conversion hoạt động như thế nào?

### 5.1. Từ chuỗi đầu vào tới Java type

Một số handler arguments không nhận `String` mà nhận `Integer`, `Long`, `UUID`, `LocalDate`, `Enum` hoặc collection. Spring MVC sử dụng các converter/formatter đã cấu hình để tạo giá trị tương ứng.

~~~text
HTTP request
  |
  +-- query/form parameter ----> @RequestParam
  |
  +-- URI template variable ---> @PathVariable
  |
  +-- request header ----------> @RequestHeader
                                   |
                                   v
                    MVC HandlerMethodArgumentResolver
                                   |
                                   v
                     WebDataBinder / ConversionService
                                   |
              +--------------------+---------------------+
              |                                          |
          chuyển đổi OK                            chuyển đổi lỗi
              |                                          |
              v                                          v
       Java method argument                     MVC error/exception
       (Long, int, enum, Date...)               (thường HTTP 400)
              |
              v
       Controller method body
~~~

Tất cả ba annotation đều dựa trên hệ thống chuyển đổi kiểu có thể mở rộng của Spring, nhưng **nguồn đầu vào và lỗi thiếu giá trị** là riêng của từng argument resolver. Đừng nhầm ConversionService với Jackson deserialization: `@RequestBody` cho JSON thường đi qua `HttpMessageConverter`.

### 5.2. Các kiểu thường gặp

| Dữ liệu chuỗi trong HTTP | Target Java | Kết quả khi giá trị hợp lệ |
|---|---|---|
| `"42"` | `long` hoặc `Long` | `42L` |
| `"3"` | `int` hoặc `Integer` | `3` |
| `"true"` | `boolean` hoặc `Boolean` | `true` |
| `"8.50"` | `BigDecimal` | `new BigDecimal("8.50")` về giá trị |
| `"9a3a..."` đúng định dạng UUID | `UUID` | instance `UUID` |
| `"PAID"` | `OrderState` enum | `OrderState.PAID` |
| `"2026-11-06"` | `LocalDate` với ISO formatter | ngày 6/11/2026 |
| `tag=java&tag=spring` | `List<String>` | hai phần tử |
| `"application/json"` từ header | `MediaType` khi converter hỗ trợ | một media type object |

Với số, không giả định mọi locale đều parse `1,5` thành `1.5`. Với ngày, không giả định `dd/MM/yyyy` tương đương ISO. Hãy khai báo format và kiểm thử đúng locale/HTTP contract.

### 5.3. `@DateTimeFormat` cho tham số ngày

~~~java
@GetMapping("/reports")
public String report(
        @RequestParam("from")
        @org.springframework.format.annotation.DateTimeFormat(
            iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
        java.time.LocalDate from) {
    return from.toString();
}
~~~

`GET /reports?from=2026-11-06` → `LocalDate` ngày 2026-11-06. Đây là handler minh họa, cần đặt trong controller có imports/route phù hợp. Chọn ISO format khi muốn hợp đồng API rõ ràng và dễ chia sẻ giữa client.

Nếu request gửi `from=06/11/2026` mà formatter đang chờ ISO, conversion có thể thất bại và thường trả HTTP 400. Lỗi này khác với violation từ `@NotNull` hoặc `@Past`: chuyển đổi phải thành công trước khi constraint tương ứng có thể đánh giá một `LocalDate` hợp lệ.

Một số trường hợp nên dùng `@NumberFormat` hoặc `@DurationFormat` để công bố format của số/thời lượng; không áp dụng `@DateTimeFormat` cho mọi kiểu.

### 5.4. `@NumberFormat` và locale

~~~java
@GetMapping("/prices")
public String price(
        @RequestParam("amount")
        @org.springframework.format.annotation.NumberFormat(
            pattern = "#,##0.00")
        java.math.BigDecimal amount) {
    return amount.toPlainString();
}
~~~

Đây là snippet minh họa, cần cân nhắc locale. Dấu `,` và dấu `.` có thể mang nghĩa khác nhau theo locale request. Với public JSON REST API cần số có format bất biến, việc đặt ra một contract thống nhất thường dễ hơn dùng localised number formatting. Nếu chấp nhận input theo ngôn ngữ người dùng, cần test các locale mà sản phẩm hỗ trợ.

### 5.5. Converter tùy chỉnh cho value object

Giả sử domain muốn nhận một ID có dạng `INV-123` và biểu diễn bằng một record type thay vì truyền `String` vào service.

Tệp `InvoiceKey.java`:

~~~java
package com.example.customconvert;

public record InvoiceKey(long number) {
}
~~~

Tệp `InvoiceKeyConverter.java`:

~~~java
package com.example.customconvert;

import org.springframework.core.convert.converter.Converter;

public final class InvoiceKeyConverter
        implements Converter<String, InvoiceKey> {

    @Override
    public InvoiceKey convert(String source) {
        if (!source.matches("INV-[0-9]+")) {
            throw new IllegalArgumentException(
                "Invoice key must look like INV-123");
        }

        try {
            long number = Long.parseLong(source.substring(4));
            return new InvoiceKey(number);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Invoice key is outside the long range", ex);
        }
    }
}
~~~

Tệp `MvcConversionConfig.java`:

~~~java
package com.example.customconvert;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new InvoiceKeyConverter());
    }
}
~~~

Khi ba file trên được Spring scan và MVC config được áp dụng, handler có thể viết:

~~~java
@GetMapping("/invoices/{id}")
public InvoiceKey find(
        @PathVariable("id") InvoiceKey id) {
    return id;
}
~~~

Request `GET /invoices/INV-123` có thể tạo `new InvoiceKey(123)`. Đây là snippet handler minh họa **trong một `@RestController` cùng ứng dụng đã đăng ký converter**, không phải project runnable tách biệt với ba file trên. Nếu sai pattern hoặc số vượt giới hạn `long`, converter ném exception báo conversion failure để Spring xử lý lỗi request.

Một converter `Converter<String,InvoiceKey>` cũng có thể được dùng cho `@RequestParam` hoặc `@RequestHeader` có cùng kiểu đích khi nó nằm trong ConversionService mà MVC sử dụng. Đó là điểm mạnh: **một cơ chế chuyển đổi** được tái sử dụng ở nhiều vị trí input.

Không nên viết converter tự động truy cập database để tạo entity có side effects; với ID của resource, có thể convert sang value object đơn giản rồi service tải dữ liệu sau khi kiểm tra quyền. Nếu dùng converter truy DB, phải hiểu rõ vòng đời request, lỗi không tìm thấy và chi phí.

### 5.6. `@InitBinder` so với converter toàn ứng dụng

Để tùy chỉnh binding tại controller, Spring còn có `@InitBinder` và `WebDataBinder`. Nó hữu ích khi format/binding rule chỉ áp dụng cho một nhóm endpoint; `WebMvcConfigurer.addFormatters(...)` thích hợp khi muốn converter dùng rộng hơn cho MVC. Không ghi đè toàn bộ ConversionService đang được Boot cấu hình chỉ để thêm một converter; hãy đăng ký bổ sung qua extension point tương ứng.

## 6. Ví dụ Spring Boot chạy được: trộn cả ba annotation

Bộ ví dụ gồm hai file trong package `com.example.requestinputs`, sử dụng Spring Boot 3.x, Java 17+, Servlet MVC và Gradle. Nó nhận một URL chứa ID số, query parameters có giá trị mặc định/danh sách/ngày tháng và hai HTTP headers. Controller trả một JSON object để quan sát giá trị sau chuyển đổi.

### 6.1. Dependency

Trong một project đã có Spring Boot Gradle plugin và dependency management hợp lệ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Để thử thêm `@Min`/`@NotBlank` ở phần validation bên dưới, bổ sung `spring-boot-starter-validation`. Nhưng ví dụ chính chỉ cần Spring MVC conversion, không cần validation provider để parse `long`, `int`, `LocalDate`.

Lệnh chạy dưới đây giả định project có `settings.gradle`, build Gradle và wrapper được tạo bởi Spring Initializr hoặc dự án Boot hiện hữu. Không thể chỉ chạy `javac` với JDK thuần vì mã import Spring MVC.

### 6.2. Entry point — `RequestInputsApplication.java`

Tạo file `src/main/java/com/example/requestinputs/RequestInputsApplication.java`:

~~~java
package com.example.requestinputs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestInputsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestInputsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật component scanning cho package hiện tại và subpackages, nên controller cùng package sẽ được phát hiện.

### 6.3. Controller — `ItemController.java`

Tạo file `src/main/java/com/example/requestinputs/ItemController.java`:

~~~java
package com.example.requestinputs;

import java.time.LocalDate;
import java.util.List;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @GetMapping("/api/items/{itemId}")
    public ItemView findItem(
            @PathVariable("itemId") long itemId,
            @RequestParam(
                name = "page",
                defaultValue = "1") int page,
            @RequestParam(
                name = "tag",
                required = false) List<String> tags,
            @RequestParam(
                name = "since",
                required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate since,
            @RequestHeader(
                name = "X-Client-Id",
                defaultValue = "web") String clientId,
            @RequestHeader(
                name = "X-Retry-Count",
                defaultValue = "0") int retryCount) {

        return new ItemView(
            itemId,
            page,
            tags == null ? List.of() : tags,
            since,
            clientId,
            retryCount
        );
    }

    public record ItemView(
        long itemId,
        int page,
        List<String> tags,
        LocalDate since,
        String clientId,
        int retryCount
    ) {
    }
}
~~~

Từng tham số thể hiện một ý:

- `@PathVariable("itemId") long itemId`: đọc `{itemId}` từ URI và chuyển sang `long`.
- `@RequestParam(name="page", defaultValue="1") int page`: nếu thiếu hoặc rỗng thì dùng mặc định `1`; giá trị số khác được parse.
- `@RequestParam(name="tag",required=false) List<String> tags`: nhiều giá trị query có cùng key; khi thiếu, controller chuẩn hóa kết quả thành danh sách rỗng, không trả `null`.
- `@RequestParam(name="since",required=false) @DateTimeFormat(ISO.DATE) LocalDate since`: query ngày ISO khi được gửi; nếu thiếu, có thể nhận `null`.
- `@RequestHeader(name="X-Client-Id",defaultValue="web") String clientId`: đọc header và dùng mặc định `"web"` nếu không có.
- `@RequestHeader(name="X-Retry-Count",defaultValue="0") int retryCount`: đọc header và convert sang số nguyên.
- `ItemView` là Java `record` chỉ dùng để hiển thị giá trị đã resolve; nó không phải entity được lưu database.

Viết rõ tên trong cả ba annotation giúp tránh nhầm tên method argument với key từ client.

### 6.4. Lệnh chạy

Unix/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Spring Boot mặc định nghe tại `http://localhost:8080` nếu chưa đổi `server.port` và cổng không bị ứng dụng khác chiếm.

Gọi request với đầy đủ trường:

~~~bash
curl -i "http://localhost:8080/api/items/42?page=3&tag=java&tag=spring&since=2026-11-06" \
  -H "X-Client-Id: mobile" \
  -H "X-Retry-Count: 2"
~~~

Kỳ vọng **HTTP 200 OK** và JSON có nội dung tương đương (thứ tự keys không được bảo đảm):

~~~json
{
  "itemId": 42,
  "page": 3,
  "tags": ["java", "spring"],
  "since": "2026-11-06",
  "clientId": "mobile",
  "retryCount": 2
}
~~~

Gọi request thiếu các query/header tùy chọn:

~~~bash
curl -i "http://localhost:8080/api/items/42"
~~~

Kỳ vọng **HTTP 200** với:

~~~json
{
  "itemId": 42,
  "page": 1,
  "tags": [],
  "since": null,
  "clientId": "web",
  "retryCount": 0
}
~~~

Dùng URL sai kiểu cho path variable:

~~~bash
curl -i "http://localhost:8080/api/items/abc"
~~~

Route `/api/items/{itemId}` match segment `abc`, nhưng `long itemId` không convert được. Với xử lý lỗi MVC mặc định, kết quả thường là **HTTP 400 Bad Request**. Nội dung error body cụ thể thay đổi theo phiên bản Spring Boot và cấu hình error handling nên không chốt một JSON message cố định.

Dùng query sai kiểu:

~~~bash
curl -i "http://localhost:8080/api/items/42?page=xyz"
~~~

Kỳ vọng **HTTP 400** do `xyz` không parse được thành `int`. `defaultValue="1"` không cứu một giá trị đã có nhưng sai kiểu.

Dùng header sai kiểu:

~~~bash
curl -i "http://localhost:8080/api/items/42" \
  -H "X-Retry-Count: no"
~~~

Kỳ vọng **HTTP 400** do header không parse được thành `int`.

Dùng ngày không đúng ISO:

~~~bash
curl -i "http://localhost:8080/api/items/42?since=06-11-2026"
~~~

Kỳ vọng **HTTP 400** vì `@DateTimeFormat(ISO.DATE)` yêu cầu input dạng `yyyy-MM-dd` với giá trị ngày hợp lệ.

Dùng path không khớp:

~~~bash
curl -i "http://localhost:8080/api/items"
~~~

Không có mapping `/api/items` trong demo, nên kết quả thông thường **HTTP 404 Not Found**, khác với lỗi chuyển đổi kiểu ở URL có segment nhưng segment không parse được.

### 6.5. Form POST không khác về kiểu conversion của `@RequestParam`

Trong Servlet MVC, form URL-encoded fields cũng là request parameters. Ví dụ một handler riêng trong controller:

~~~java
@PostMapping(
    path = "/api/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public String search(
        @RequestParam("term") String term,
        @RequestParam(name = "page", defaultValue = "1")
        int page) {
    return term + ":" + page;
}
~~~

Đây là snippet bổ sung, cần imports cho `@PostMapping`, `MediaType` và `@RequestParam`. Nếu client gửi body `term=spring&page=3` với `Content-Type: application/x-www-form-urlencoded`, handler trả `spring:3`. Với nhiều form fields, `@ModelAttribute SearchForm form` thường dễ quản lý hơn viết từng `@RequestParam`.

## 7. Kiểm thử bằng MockMvc: conversion thành công và thất bại

Thêm `spring-boot-starter-test` như phần dependencies. Tệp `src/test/java/com/example/requestinputs/ItemControllerTest.java`:

~~~java
package com.example.requestinputs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void bindsAllThreeSourcesAndConvertsTypes()
            throws Exception {
        mvc.perform(get("/api/items/42")
                .param("page", "3")
                .param("tag", "java", "spring")
                .param("since", "2026-11-06")
                .header("X-Client-Id", "mobile")
                .header("X-Retry-Count", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemId").value(42))
            .andExpect(jsonPath("$.page").value(3))
            .andExpect(jsonPath("$.tags[0]").value("java"))
            .andExpect(jsonPath("$.tags[1]").value("spring"))
            .andExpect(jsonPath("$.since").value("2026-11-06"))
            .andExpect(jsonPath("$.clientId").value("mobile"))
            .andExpect(jsonPath("$.retryCount").value(2));
    }

    @Test
    void appliesDefaultsForMissingValues()
            throws Exception {
        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(1))
            .andExpect(jsonPath("$.tags").isEmpty())
            .andExpect(jsonPath("$.since").value(
                org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.clientId").value("web"))
            .andExpect(jsonPath("$.retryCount").value(0));
    }

    @Test
    void rejectsInvalidPathId() throws Exception {
        mvc.perform(get("/api/items/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidQueryNumber() throws Exception {
        mvc.perform(get("/api/items/42")
                .param("page", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidHeaderNumber() throws Exception {
        mvc.perform(get("/api/items/42")
                .header("X-Retry-Count", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidDateFormat() throws Exception {
        mvc.perform(get("/api/items/42")
                .param("since", "06-11-2026"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void pathMustMatchRoute() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Trong project Spring Boot 3.x với cấu hình MVC mặc định, bảy test trên kỳ vọng **PASS**. Các test kiểm tra từ phía request qua `MockMvc` (argument resolution, conversion, response rendering), không chỉ thử `Long.parseLong` hoặc setter trong Java. Với project thực có Spring Security/custom filters, phải cấu hình security test tương ứng.

Nếu dự án dùng Spring Boot 4+, các dependency/module và package testing có thể khác; mã test này được mô tả cho **Spring Boot 3.x**.

## 8. Phân biệt lỗi thiếu tham số và lỗi chuyển kiểu

Một ứng dụng cần trả lỗi HTTP nhất quán, nhưng không được gom mọi lỗi vào “validation error”.

| Tình huống | Pha xảy ra | Hành vi mặc định thường gặp |
|---|---|---|
| `@RequestParam("page") int page` nhưng không gửi `page` | Resolve required parameter | `MissingServletRequestParameterException` → HTTP 400 |
| `@RequestHeader("X-Key") String key` nhưng thiếu header | Resolve required header | `MissingRequestHeaderException` → HTTP 400 |
| URI `/items/abc` với `@PathVariable long id` | Type conversion sau route match | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Query `?page=abc` với `int page` | Type conversion | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Header `X-Retry-Count: abc` với `int retryCount` | Type conversion | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Query có giá trị rỗng bị converter biến thành `null` | Conversion rồi required check | Có thể được xem như thiếu giá trị sau conversion |
| URI thiếu segment của route `/items/{id}` | Handler mapping | Thường HTTP 404, không phải “missing path variable” trong handler |
| `@Min(1)` trên `page` và giá trị `0` | Bean/method validation (nếu đã bật) | Method validation exception tương ứng; không phải type mismatch |
| Logic service không tìm được ID hợp lệ trong DB | Business/service | Tùy ứng dụng quyết định 404 hoặc lỗi khác |

**Giá trị rỗng đặc biệt:** Spring reference chỉ ra nếu một chuỗi sau conversion trở thành `null` thì argument required có thể bị coi là thiếu. Nếu parameter thực sự có thể null, dùng `required=false` hoặc `@Nullable`/`Optional` theo contract. `required=false` không có nghĩa là mọi giá trị không hợp lệ đều được chấp nhận.

### Không nên “bắt hết exception rồi trả 200”

Một REST API có thể dùng `@RestControllerAdvice` để chuyển lỗi thành JSON ổn định. Đoạn minh họa:

~~~java
@RestControllerAdvice
public class InputErrorAdvice {

    @ExceptionHandler(
        org.springframework.web.method.annotation
            .MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> wrongType(
            org.springframework.web.method.annotation
                .MethodArgumentTypeMismatchException ex) {

        return ResponseEntity.badRequest().body(
            Map.of(
                "error", "INVALID_TYPE",
                "argument", ex.getName()));
    }
}
~~~

Đây là **mẫu riêng**, yêu cầu imports cho `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `Map` và đặt trong package được scan. Nó minh họa mapping lỗi conversion; chưa xử lý riêng thiếu parameter, thiếu header, body lỗi, Bean Validation hay request path không match. Trong ứng dụng thật, thiết kế error response nhất quán, tránh trả exception stack trace hoặc dữ liệu nhạy cảm ra client.

Một route match thành công nhưng conversion lỗi khác hoàn toàn với route không match. Khi debug, kiểm tra cả **mapping conditions** lẫn **conversion service**, không chỉ catch exception.

## 9. Bean Validation trên controller argument có phải type conversion không?

Không. Type conversion thay đổi/parse kiểu input (`"2"` thành `2`), còn Jakarta Bean Validation đánh giá constraint (`2` có thỏa `@Min(1)` không). Thứ tự khái quát:

~~~text
@RequestParam("page") String "0"
             |
             v
ConversionService -> int 0
             |
             v
Bean Validation nếu method validation được kích hoạt
             |
             v
@Min(1) => hợp lệ hay vi phạm?
~~~

Ví dụ minh họa với Spring MVC 6.1+ và validation starter:

~~~java
@GetMapping("/paged")
public String paged(
        @RequestParam(defaultValue = "1")
        @jakarta.validation.constraints.Min(1)
        int page) {
    return "page=" + page;
}
~~~

Với Spring MVC 6.1+, constraint trực tiếp trên handler method parameter có thể được kiểm tra qua **built-in handler method validation** và một violation thường dẫn đến `HandlerMethodValidationException`. Đây là cơ chế riêng với Spring AOP service method validation; **không cần suy luận rằng `@RequestParam` tự làm Bean Validation**.

Nếu project đang dùng Spring MVC bản cũ hơn hoặc controller có class-level `@Validated`, cơ chế kiểm tra/loại exception có thể khác; cần đối chiếu phiên bản Spring và đường validation đang hoạt động. Để bật Bean Validation trong Spring Boot 3, thông thường thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Việc `@Min(1)` có hiệu lực **không tự giải quyết** lỗi `page=abc`, vì input chưa chuyển được thành `int`. Ngược lại, `page=0` parse thành công nhưng sai validation. Phân biệt hai lớp lỗi để test và trả message chính xác.

## 10. Đăng ký converter và formatter trong cấu hình MVC

### 10.1. Dùng `WebMvcConfigurer.addFormatters`

Tài liệu Spring khuyến nghị extension point `WebMvcConfigurer` để đăng ký formatter/converter dùng trong MVC. Ví dụ:

~~~java
@Configuration
public class MyMvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(
            org.springframework.format.FormatterRegistry registry) {
        registry.addConverter(new InvoiceKeyConverter());
    }
}
~~~

Đây là một phần của ví dụ converter ở mục 5; nếu đặt thành file riêng, cần import `Configuration`, `WebMvcConfigurer` và class `InvoiceKeyConverter` cùng package. Không khai báo cả `MvcConversionConfig` và `MyMvcConfig` cùng đăng ký một converter nếu không có lý do.

### 10.2. Formatter cho date/time

`@DateTimeFormat(iso = ISO.DATE)` là lựa chọn trực tiếp cho một parameter. Ở cấp ứng dụng, có thể cấu hình một chiến lược ISO thống nhất cho formatter ngày bằng `DateTimeFormatterRegistrar` trong `addFormatters` khi hợp đồng sản phẩm yêu cầu. Lưu ý locale khi dùng pattern không phải ISO.

### 10.3. Tại sao không tự parse mọi thứ trong controller?

~~~java
// Không nên lặp trong hàng chục handler:
@GetMapping("/bad-example")
public String bad(
        @RequestParam("id") String rawId) {
    long id = Long.parseLong(rawId);
    return "id=" + id;
}
~~~

Snippet này chạy được trong một `@RestController` nhưng tự parse khiến mỗi handler phải tự bắt `NumberFormatException`, đưa ra HTTP error và tái hiện logic conversion. Thường nên viết:

~~~java
@GetMapping("/better-example")
public String better(
        @RequestParam("id") long id) {
    return "id=" + id;
}
~~~

Để Spring convert và xử lý input lỗi ở MVC boundary. Khi domain thực sự cần một định dạng riêng (ví dụ `INV-123`), đăng ký một converter thống nhất. Với xử lý bảo mật hoặc lookup DB, hãy giữ phân quyền và logic truy xuất bên service, không nhét tất cả vào converter.

## 11. Thiết kế API: path, query và header nên chứa gì?

### 11.1. ID trong path

`GET /users/42` mô tả tài nguyên được chọn. `@PathVariable("id") Long id` chuyển đổi ID nhưng **không** kiểm tra rằng user 42 tồn tại hoặc caller có quyền xem. Nếu ID không tồn tại, service có thể trả lỗi tài nguyên không tìm thấy; nếu thiếu quyền, xử lý bằng security/domain rules.

### 11.2. Bộ lọc và phân trang trong query

`GET /users?status=ACTIVE&page=1&size=20` phù hợp cho filter/pagination. `@RequestParam` hỗ trợ giá trị mặc định, enums, số và collection. Nên áp giới hạn `size`, tập sort keys và filter values ở server; converter đúng kiểu không đảm bảo giá trị phù hợp nghiệp vụ.

### 11.3. Metadata trong header

Header thường mang metadata về content negotiation, tracing, correlation, locale, preconditions hoặc client capability. Dùng `@RequestHeader` khi chính header là phần của HTTP contract, không phải để thay thế body cho dữ liệu nghiệp vụ phức tạp.

**Lưu ý an toàn:** header như `Authorization`, `Cookie` hoặc `X-Api-Key` không nên được ghi đầy đủ vào log, phản hồi cho client, hay dùng như plain text chứng minh đã xác thực. Header do reverse proxy cung cấp cần có trust boundary và anti-spoofing rõ ràng.

### 11.4. Phân biệt route mapping và type conversion

Route mapping giải quyết **handler nào** nhận request; type conversion giải quyết **argument Java nào** được cung cấp cho handler đó. Ví dụ `GET /orders/new` và `GET /orders/{id}` có thể cần route rõ ràng để tránh cố convert `new` thành `long`. Dùng một pattern/route design không mập mờ thay vì dựa vào exception để phân biệt action với resource ID.

## 12. Những lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `@RequestParam` nhận `null` dù URL có segment `/42` | Dùng sai nguồn dữ liệu | Dùng `@PathVariable` cho URI template variable |
| `@PathVariable` báo thiếu tên | Tên annotation khác tên URI variable hoặc thiếu parameter metadata | Viết `@PathVariable("orderId")` tường minh |
| `@RequestHeader` không đọc được query `?token=...` | Header không phải query param | Gửi header thực hoặc đổi thành `@RequestParam` theo API contract |
| `page=abc` gây HTTP 400 | String không chuyển sang `int` được | Sửa giá trị, dùng formatter/converter phù hợp hoặc error response rõ ràng |
| `page=0` được chấp nhận dù mong muốn trang tối thiểu 1 | Chuyển kiểu đúng nhưng thiếu constraint nghiệp vụ | Thêm `@Min(1)` với method validation hoặc kiểm tra service |
| `required=false int page` gây vấn đề khi input thiếu | Primitive không chứa `null` | Dùng `Integer`, `Optional<Integer>` hoặc `defaultValue` |
| `/orders` không chạy handler `/orders/{id}` | Thiếu path segment nên route không match | Khai báo mapping collection riêng |
| `/orders/abc` không vào method có `long id` | Conversion failure | Trả HTTP 400; phân biệt với route mismatch |
| Header `X-Retry-Count: abc` không chạy handler | Conversion failure cho header số | Yêu cầu số nguyên đúng format |
| `since=06-11-2026` thất bại | Formatter đang yêu cầu ISO date | Dùng `yyyy-MM-dd` hoặc sửa contract/formatter có chủ đích |
| `?tag=a&tag=b` chỉ còn một giá trị | Đang dùng `String`/`Map` một giá trị mỗi key | Dùng `List<String>` hoặc `MultiValueMap` |
| Mất header values khi dùng `Map<String,String>` | Một key có thể có nhiều giá trị | Dùng `HttpHeaders`/`MultiValueMap` khi cần |
| Enum chữ thường không parse | Default enum conversion dựa trên enum constants | Đăng ký custom converter nếu muốn alias/case policy |
| Custom `Converter` không chạy | Chưa thêm vào MVC ConversionService hoặc config không được scan | Đăng ký qua `WebMvcConfigurer.addFormatters` |
| Client gửi JSON nhưng `@RequestParam` không nhận field | JSON không là Servlet request parameter map | Dùng `@RequestBody` với DTO |
| Logic tin `X-Role: admin` do client gửi | Không có bước xác thực/ủy quyền | Dùng cơ chế authentication/authorization đáng tin |
| HTTP 400 không có JSON format mong muốn | Chưa định nghĩa error handling | Dùng `@RestControllerAdvice`, không nuốt exception |
| Test dùng default nhưng nhận lỗi do giá trị rỗng/space | Quy tắc empty String, null after conversion và default khác nhau | Test đủ missing, empty, whitespace, invalid và valid |
| Controller signature dùng parameter name ngầm nhưng không resolve được | Build thiếu `-parameters` hoặc tên bị thay đổi | Chỉ rõ `name`/`value` trong annotation |

### Thứ tự debug hữu ích

1. Xác nhận HTTP method và path thực tế; route có match hay không?
2. Xác định input ở đâu: query/form, URI template hay header?
3. Xem tên annotation `name`/`value` có khớp key/URI variable không?
4. Kiểm tra `required`, `defaultValue`, `Optional` và kiểu Java primitive/wrapper.
5. Nếu value tồn tại nhưng sai, kiểm tra `ConversionService`, locale, `@DateTimeFormat`/`@NumberFormat` và converter custom.
6. Đọc exception: missing request param/header, type mismatch, route mismatch, hoặc validation error.
7. Sau khi parse thành công, mới xét quy tắc nghiệp vụ, authorization và persistence.

Đừng khắc phục một lỗi conversion bằng cách bỏ mọi validation hoặc biến tất cả parameter thành `String` một cách máy móc. Type-safe method signature giúp hợp đồng controller rõ và tập trung logic xử lý lỗi.

## 13. Bài tập tự kiểm tra

**Bài 1 — Mặc định và thiếu tham số.** Với `@RequestParam(defaultValue="10") int size`, so sánh `GET /items`, `GET /items?size=`, `GET /items?size=20` và `GET /items?size=oops`. Trả lời: lần lượt nhận 10, 10, 20 và gặp lỗi chuyển kiểu. Default không sửa được input có mặt nhưng sai kiểu.

**Bài 2 — Path và query.** Với `@GetMapping("/products/{id}")`, hãy xác định vì sao `GET /products/21?page=2` cần `@PathVariable("id") long id` và `@RequestParam("page") int page`. Nếu dùng cả hai annotation ngược nguồn, Spring không đọc đúng giá trị mong muốn.

**Bài 3 — Header và trust boundary.** Một client gửi `X-User-Role: ADMIN`. Chỉ cần `@RequestHeader String role` có đủ chứng minh user là admin không? Không; HTTP header có thể bị client điều khiển và cần xác thực/ủy quyền theo security architecture.

**Bài 4 — Date conversion.** Handler dùng `@DateTimeFormat(iso=ISO.DATE) LocalDate from`. Input nào hợp lệ: `2026-11-06` hay `06/11/2026`? Với ISO.DATE, dạng đầu là phù hợp. Nếu muốn hỗ trợ dạng khác, phải khai báo formatter/contract thích hợp.

**Bài 5 — Repeated query.** Với `?tag=java&tag=spring`, nên dùng `String tag` hay `List<String> tags` nếu cần cả hai? Dùng `List<String>`; có thể dùng `MultiValueMap` nếu muốn dữ liệu của nhiều keys.

**Bài 6 — Kiểm tra logic.** Với `int page`, request gửi `page=0`. Conversion có thất bại không? Không, vì `"0"` là chuỗi số hợp lệ. Muốn cấm trang 0 cần ràng buộc/logic riêng.

**Bài 7 — Custom type.** Nếu API nhận `/invoices/INV-123` và method muốn `InvoiceKey`, bạn đăng ký gì? Một `Converter<String,InvoiceKey>` vào ConversionService của MVC, rồi dùng `@PathVariable("id") InvoiceKey id`.

**Bài 8 — Route vs mismatch.** `/items` và `/items/abc` dẫn đến khác nhau thế nào nếu chỉ có `/items/{itemId}` với `long itemId`? `/items` không match route (thường 404); `/items/abc` có thể match route nhưng conversion thất bại (thường 400).

## 14. Checklist áp dụng vào dự án

- [ ] Chọn annotation theo đúng nguồn: `@RequestParam`, `@PathVariable`, `@RequestHeader`.
- [ ] Ghi tên key/template/header tường minh để tránh phụ thuộc parameter-name metadata.
- [ ] Xác định rõ trường bắt buộc/tùy chọn; dùng `required=false`, `Optional` hoặc `defaultValue` có chủ đích.
- [ ] Không để primitive nhận giá trị thiếu nếu không có default.
- [ ] Kiểm tra các kiểu `Integer`, `Long`, `UUID`, enum, `LocalDate` và các collection được dùng trong hợp đồng API.
- [ ] Với ngày/giá trị phụ thuộc locale, định nghĩa format bằng `@DateTimeFormat` / `@NumberFormat` hoặc formatter phù hợp.
- [ ] Nếu cần custom value object, tạo converter và đăng ký bằng `WebMvcConfigurer.addFormatters`.
- [ ] Test input hợp lệ, missing, empty, wrong type, multiple values và route không match qua `MockMvc`.
- [ ] Phân biệt conversion error với Bean Validation constraint; chọn cách trả HTTP error nhất quán.
- [ ] Không ghi lại toàn bộ headers hoặc tin custom security headers nếu không có trust boundary.
- [ ] Với nhiều field form, cân nhắc `@ModelAttribute`; với body JSON, dùng `@RequestBody`.
- [ ] Giữ validation/authorization/business logic ở đúng tầng sau khi argument conversion đã hoàn tất.

**Ghi nhớ:** `@RequestParam` chọn dữ liệu **query/form**, `@PathVariable` chọn **URI template variable**, `@RequestHeader` chọn **HTTP header**. Spring MVC resolve nguồn trước, sau đó dùng **ConversionService/formatter** để tạo Java arguments; lỗi thiếu giá trị, lỗi chuyển kiểu, lỗi route không match và lỗi Bean Validation là **những tình huống khác nhau**, cần xử lý đúng ranh giới.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — @RequestParam](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework — URI patterns và @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — @RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — Type Conversion for Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
- [Spring Framework — MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Spring MVC and Web Features](https://docs.spring.io/spring-boot/reference/web/servlet.html)
