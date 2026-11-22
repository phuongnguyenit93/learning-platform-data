# Đọc @RequestParam, @RequestHeader và @CookieValue trong Spring WebFlux

## 1. Mục tiêu

Một endpoint HTTP thường nhận dữ liệu từ nhiều vị trí của request:

- **Query string** trên URL, ví dụ `?page=2&sort=price`.
- **Request headers**, ví dụ `Accept-Language`, `X-Request-Id` hoặc `If-None-Match`.
- **Cookies** do client gửi trong header `Cookie`, ví dụ `theme=dark`.

Trong controller theo mô hình annotation của Spring WebFlux, ba annotation tương ứng là:

| Annotation | Nguồn dữ liệu | Ví dụ |
| --- | --- | --- |
| `@RequestParam` | Query parameters trong URL | `?page=2` |
| `@RequestHeader` | Một HTTP request header | `X-Request-Id: req-42` |
| `@CookieValue` | Giá trị của một cookie có tên cụ thể | `Cookie: theme=dark` |

Spring đọc request, tìm giá trị theo tên, chuyển đổi sang kiểu tham số của method rồi gọi handler. Controller không cần tự parse chuỗi URL, split header hoặc đọc toàn bộ Cookie header bằng tay trong các trường hợp thông thường.

Bài học tập trung vào **Spring WebFlux annotated controllers**. Các annotation có tên giống trong Spring MVC, nhưng một điểm khác biệt quan trọng là `@RequestParam` trong WebFlux chỉ bind query parameters; form data và multipart được xử lý qua các cơ chế riêng.

## 2. Phân biệt vị trí dữ liệu trong HTTP request

Xem request minh họa:

```http
GET /api/products?page=2&tag=reactor&tag=webflux HTTP/1.1
Host: localhost:8080
Accept: application/json
Accept-Language: vi
X-Request-Id: req-42
Cookie: theme=dark; session=opaque-session-value
```

Các giá trị được lấy như sau:

- `page=2`, hai giá trị `tag`: query parameters, đọc bằng `@RequestParam`.
- `Accept-Language: vi` và `X-Request-Id: req-42`: headers, đọc bằng `@RequestHeader`.
- `theme=dark` hoặc `session=...`: cookie pairs, đọc từng cookie bằng `@CookieValue`.

Một request có thể có nhiều query parameter cùng tên, nhiều header values hoặc nhiều cookie khác nhau. Cần chọn kiểu tham số phản ánh đúng dữ liệu cần nhận, thay vì luôn dùng `String` cho mọi thứ.

### 2.1. Điểm khác biệt giữa WebFlux và Spring MVC

Trong Spring MVC, khái niệm servlet request parameters gộp query parameters, form fields và một số multipart parameters vào cùng một mô hình. Trong **Spring WebFlux**, `@RequestParam` chỉ bind **query parameters**. Form data và multipart được truy cập riêng qua `ServerWebExchange` hoặc bind vào command object bằng `@ModelAttribute`; file/multipart part có cơ chế `@RequestPart`.

Không sao chép giả định từ một controller MVC sang WebFlux mà không kiểm tra. Nếu endpoint WebFlux nhận `application/x-www-form-urlencoded`, việc dùng `@RequestParam("email")` không tương đương một cách tổng quát với servlet MVC.

## 3. Dùng @RequestParam để đọc query parameters

### 3.1. Đọc một giá trị

Ví dụ:

```java
@GetMapping("/products")
public Mono<String> products(
        @RequestParam("page") int page) {

    return Mono.just("page=" + page);
}
```

Với URL `GET /products?page=3`, Spring chuyển chuỗi `"3"` sang `int 3` rồi truyền vào method. Nếu query parameter không tồn tại, tham số mặc định là **bắt buộc**; request thiếu `page` thường được xử lý thành HTTP 400 Bad Request.

Có thể dùng thuộc tính `name` thay cho `value`:

```java
@RequestParam(name = "page") int page
```

Hai cách tương đương. Tên nên được viết tường minh khi tên query parameter là một phần của API contract.

### 3.2. Đặt tên khác với tên biến Java

Tên trong HTTP không bắt buộc giống tên tham số:

```java
@GetMapping("/products")
public Mono<String> products(
        @RequestParam(name = "page_size") int pageSize) {

    return Mono.just("pageSize=" + pageSize);
}
```

Client gửi `?page_size=20`, còn code Java dùng tên dễ đọc `pageSize`. Nên duy trì một quy ước naming nhất quán cho API.

### 3.3. Giá trị mặc định và tham số không bắt buộc

Có ba cách thường dùng:

**Cách A – cung cấp defaultValue:**

```java
@RequestParam(name = "page", defaultValue = "1") int page
```

Nếu query parameter không được gửi hoặc có giá trị rỗng, Spring dùng giá trị mặc định theo quy tắc của annotation. Khi có `defaultValue`, `required` được ngầm chuyển thành `false`.

**Cách B – required=false:**

```java
@RequestParam(name = "page", required = false) Integer page
```

Khi thiếu tham số, giá trị có thể là `null`. Dùng kiểu wrapper `Integer`, `Long` hoặc kiểu nullable phù hợp; **không dùng primitive** `int`/`long` nếu bạn muốn nhận null.

**Cách C – Optional:**

```java
@RequestParam(name = "page") Optional<Integer> page
```

Khi không có query parameter, Spring cung cấp `Optional.empty()`. Với annotation có thuộc tính `required`, `Optional<T>` được hỗ trợ và tương đương với `required=false`. Không cần lặp lại cả `required=false` và `Optional` trừ khi muốn thể hiện rõ ý đồ cho người đọc.

| Request | Khai báo | Kết quả mong đợi |
| --- | --- | --- |
| `?page=4` | `int page` | `4` |
| Không có `page` | `defaultValue="1"` | `1` |
| Không có `page` | `required=false, Integer` | `null` |
| Không có `page` | `Optional<Integer>` | `Optional.empty()` |
| `?page=abc` | `int page` | Lỗi chuyển đổi, thường HTTP 400 |
| `?page=` | `defaultValue="1"` | Dùng default value |

**Không dùng một primitive với required=false để biểu diễn giá trị vắng mặt.** Nếu cần phân biệt “không gửi”, “gửi rỗng” và “gửi giá trị hợp lệ”, hãy dùng kiểu phù hợp và định nghĩa rõ contract.

### 3.4. Một query parameter có nhiều giá trị

Client có thể gửi cùng tên nhiều lần:

```http
GET /products?tag=reactor&tag=webflux&tag=spring
```

Dùng array hoặc collection:

```java
@GetMapping("/products")
public Mono<List<String>> products(
        @RequestParam(name = "tag", required = false)
        List<String> tags) {

    List<String> safeTags =
            tags == null ? List.of() : List.copyOf(tags);

    return Mono.just(safeTags);
}
```

Với request trên, danh sách có thể là `["reactor", "webflux", "spring"]`. Có thể dùng `String[]` nếu phù hợp. Đối với tham số lặp lại, collection giúp biểu đạt ý định rõ ràng hơn.

### 3.5. Đọc tất cả query parameters

Nếu method cần toàn bộ query map thay vì một key:

```java
@GetMapping("/search")
public Mono<Map<String, List<String>>> search(
        @RequestParam MultiValueMap<String, String> params) {

    Map<String, List<String>> result = new LinkedHashMap<>();
    params.forEach((name, values) ->
            result.put(name, List.copyOf(values)));

    return Mono.just(result);
}
```

Khi `@RequestParam` không chỉ định tên trên tham số `Map<String,String>` hoặc `MultiValueMap<String,String>`, Spring điền tất cả query parameter vào map. `MultiValueMap` giữ nhiều giá trị của cùng một tên; `Map<String,String>` chỉ biểu đạt một giá trị cho mỗi key nên không thích hợp nếu API cho phép lặp.

Đây là lựa chọn hữu ích cho bộ lọc tìm kiếm động, nhưng nếu API có schema ổn định, các tham số tường minh hoặc một DTO thường dễ validate và bảo trì hơn.

### 3.6. Encoding và giá trị rỗng

Query string được mã hóa theo quy tắc URI. Các ký tự đặc biệt, dấu cách và tiếng Việt cần được URL encode đúng ở client. Không tự decode nhiều lần; Spring đã thực hiện xử lý theo cơ chế request mapping.

Phân biệt:

- Không có key: `/products`.
- Key có giá trị rỗng: `/products?keyword=`.
- Key có khoảng trắng hoặc chuỗi đã encode: cần kiểm tra giá trị sau khi decode.
- Key lặp: `?tag=a&tag=b`.

Với kiểu `String`, chuỗi rỗng có thể vẫn là chuỗi rỗng. Với kiểu số hoặc UUID, một chuỗi rỗng sau chuyển đổi có thể được xem như giá trị thiếu nếu converter trả null. Nếu nghiệp vụ cần phân biệt chính xác, dùng `String` hoặc kiểu wrapper, kiểm tra đầu vào rồi chuyển đổi theo quy tắc riêng.

## 4. Dùng @RequestHeader để đọc HTTP headers

### 4.1. Đọc một header

Ví dụ:

```java
@GetMapping("/client-info")
public Mono<String> clientInfo(
        @RequestHeader("Accept-Language") String language,
        @RequestHeader("X-Request-Id") String requestId) {

    return Mono.just(
            "language=" + language + ", requestId=" + requestId);
}
```

Spring bind giá trị header vào tham số method. Header names trong HTTP không phân biệt chữ hoa/chữ thường, vì vậy `X-Request-Id` và `x-request-id` đại diện cùng tên header theo chuẩn HTTP.

Nếu không có header bắt buộc, request thường nhận HTTP 400. Có thể dùng `required=false`, `Optional<T>` hoặc `defaultValue` giống cách xử lý query parameter.

### 4.2. Chuyển đổi kiểu dữ liệu

Header thường đến dưới dạng chuỗi. Nếu tham số Java là kiểu khác `String`, Spring áp dụng hệ thống conversion:

```java
@GetMapping("/poll")
public Mono<String> poll(
        @RequestHeader("Keep-Alive") long keepAlive,
        @RequestHeader(name = "X-Retry", defaultValue = "0")
        int retry) {

    return Mono.just(
            "keepAlive=" + keepAlive + ", retry=" + retry);
}
```

Chuyển đổi tự động giúp tránh việc parse thủ công trong controller. Nếu header không chuyển đổi được sang kiểu đích, Spring báo lỗi binding/conversion và thông thường trả HTTP 400.

### 4.3. Header có nhiều giá trị

Có thể dùng array hoặc collection cho các header có nhiều giá trị:

```java
@GetMapping("/accept")
public Mono<List<String>> accept(
        @RequestHeader("Accept") List<String> acceptValues) {

    return Mono.just(List.copyOf(acceptValues));
}
```

Spring hỗ trợ chuyển đổi một số chuỗi header phân tách bằng dấu phẩy thành array/collection. Tuy nhiên, **không nên tự giả định mọi header đều có thể gộp hoặc split bằng dấu phẩy**. Ý nghĩa danh sách phụ thuộc định nghĩa của từng header.

Nếu cần giữ đầy đủ các giá trị header, có thể dùng `HttpHeaders` hoặc `MultiValueMap<String,String>`:

```java
@GetMapping("/headers")
public Mono<Map<String, List<String>>> headers(
        @RequestHeader HttpHeaders headers) {

    Map<String, List<String>> result =
            new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

    headers.forEach((name, values) ->
            result.put(name, List.copyOf(values)));

    return Mono.just(result);
}
```

Khai báo `@RequestHeader HttpHeaders headers` không có tên header cụ thể để nhận tập headers của request. `HttpHeaders` là cấu trúc phù hợp hơn khi cần truy cập nhiều header, kể cả các giá trị lặp.

**Cảnh báo:** không tự tách header phức tạp theo dấu phẩy nếu grammar của header có thể chứa dấu phẩy bên trong giá trị. Hãy dùng API/formatter phù hợp với header đó. Với header nhạy cảm như Authorization, tránh log nguyên giá trị.

### 4.4. Một số header thường gặp

| Header | Ý nghĩa thường gặp | Cách dùng |
| --- | --- | --- |
| `Accept` | Kiểu nội dung client chấp nhận | Content negotiation |
| `Accept-Language` | Ngôn ngữ client ưu tiên | Locale/response localization |
| `Authorization` | Thông tin xác thực | Để Spring Security hoặc cơ chế auth xử lý; không log token |
| `X-Request-Id` | Correlation ID theo quy ước của ứng dụng | Theo dõi log/tracing; xác thực nguồn nếu dùng cho logic tin cậy |
| `If-None-Match` | Validator cho cache có điều kiện | Xử lý ETag/304 |
| `Content-Type` | Kiểu nội dung request body | Kiểm tra định dạng body |

Các header tùy chỉnh như `X-Request-Id` chỉ là quy ước ứng dụng, không tự có ý nghĩa bảo mật. Không dùng header do client tự gửi để chứng minh danh tính hoặc quyền hạn.

## 5. Dùng @CookieValue để đọc một cookie

### 5.1. Đọc cookie theo tên

Ví dụ request có header:

```http
Cookie: theme=dark; session=opaque-session-value
```

Controller lấy một cookie:

```java
@GetMapping("/theme")
public Mono<String> theme(
        @CookieValue("theme") String theme) {

    return Mono.just("theme=" + theme);
}
```

Spring bind **giá trị của cookie có tên `theme`** vào tham số. Bạn không phải tự parse toàn bộ chuỗi Cookie header.

### 5.2. Cookie bắt buộc, tùy chọn và mặc định

Tương tự các annotation còn lại:

```java
@GetMapping("/session")
public Mono<String> session(
        @CookieValue("session") String sessionId,
        @CookieValue(name = "theme", defaultValue = "light")
        String theme,
        @CookieValue(name = "campaign", required = false)
        String campaign) {

    return Mono.just("session=" + sessionId
            + ", theme=" + theme
            + ", campaign=" + campaign);
}
```

- `session` là bắt buộc theo mặc định; thiếu cookie thì thường nhận HTTP 400.
- `theme` dùng `light` nếu cookie không có hoặc giá trị rỗng theo quy tắc default value; khai báo default ngầm đặt required thành false.
- `campaign` không bắt buộc; nếu thiếu thì giá trị Java có thể là null.

Có thể dùng `Optional<String>` cho cookie tùy chọn nếu muốn biểu diễn việc vắng mặt rõ ràng:

```java
@CookieValue("campaign") Optional<String> campaign
```

### 5.3. Đọc tất cả cookies

`@CookieValue` phù hợp khi cần một cookie đã biết tên. Nếu cần duyệt tất cả cookie, dùng `ServerHttpRequest` hoặc `ServerWebExchange`:

```java
@GetMapping("/cookies")
public Mono<Map<String, List<String>>> cookies(
        ServerHttpRequest request) {

    Map<String, List<String>> result = new TreeMap<>();

    request.getCookies().forEach((name, cookies) ->
            result.put(name, cookies.stream()
                    .map(HttpCookie::getValue)
                    .toList()));

    return Mono.just(result);
}
```

Trong WebFlux, `ServerHttpRequest.getCookies()` trả về cấu trúc nhiều giá trị theo tên cookie, với kiểu `HttpCookie` của Spring. Đây là API phù hợp nếu cần duyệt tất cả cookie hoặc đọc thông tin ở mức request. Không dùng `javax.servlet.http.Cookie` trong controller WebFlux; đó là API Servlet.

### 5.4. Cookie value không chứa cookie attributes

Client thường gửi các cặp `name=value` trong request Cookie header. Những thuộc tính như `Secure`, `HttpOnly`, `SameSite`, `Path` và `Domain` được server thiết lập qua response Set-Cookie để điều khiển cách browser lưu và gửi cookie; chúng **không được gửi lại như các thuộc tính trong request Cookie header**.

Vì vậy `@CookieValue("session")` chỉ đọc giá trị cookie. Nó không cho biết cookie được thiết lập với `HttpOnly` hay `SameSite` nào. Nếu cần thay đổi cookie attributes, hãy tạo response cookie bằng `ResponseCookie`/response header `Set-Cookie`, không sửa giá trị nhận vào rồi kỳ vọng thay đổi thuộc tính browser.

## 6. Type conversion: từ chuỗi HTTP sang kiểu Java

Cả ba annotation đều có thể cần chuyển đổi từ dữ liệu chuỗi sang kiểu tham số:

```java
@GetMapping("/report")
public Mono<String> report(
        @RequestParam("count") int count,
        @RequestHeader("X-Enabled") boolean enabled,
        @CookieValue("version") long version) {

    return Mono.just(count + ":" + enabled + ":" + version);
}
```

Ví dụ trên yêu cầu:

- Query `count` chuyển thành số nguyên.
- Header `X-Enabled` chuyển thành boolean.
- Cookie `version` chuyển thành long.

Spring dùng hệ thống `ConversionService`/converters và formatters. Các kiểu đơn giản phổ biến được hỗ trợ sẵn. Khi tham số là kiểu tùy chỉnh, bạn có thể đăng ký converter hoặc formatter.

### 6.1. Xử lý lỗi chuyển đổi

Nếu client gửi:

```http
GET /report?count=abc
X-Enabled: maybe
Cookie: version=not-a-number
```

Spring không thể chuyển các giá trị đó thành kiểu Java yêu cầu. Request thường được xử lý thành HTTP 400 Bad Request; controller có thể chưa được gọi vì việc resolve method arguments đã thất bại.

Không nên catch mọi lỗi rồi gán giá trị 0 hoặc false một cách im lặng. Điều đó có thể biến request sai thành một yêu cầu hợp lệ về mặt cú pháp nhưng sai nghiệp vụ. Hãy để lỗi binding được báo rõ hoặc xử lý qua exception handler với thông báo phù hợp.

### 6.2. Empty string và null sau conversion

Một chi tiết dễ bỏ sót là chuỗi rỗng có thể được converter biến thành null đối với một số kiểu như `Long` hoặc `UUID`. Spring xem kết quả null sau conversion tương tự giá trị đầu vào bị thiếu đối với tham số required. Từ Spring Framework 5.3, các tham số không-null còn được kiểm tra sau conversion.

Nếu muốn cho phép null, khai báo annotation `required=false` hoặc dùng `@Nullable` phù hợp. Với primitive, không thể nhận null. Với kiểu nghiệp vụ phức tạp, nên phân biệt rõ chuỗi rỗng, không có key và giá trị sai định dạng.

### 6.3. Đăng ký Converter hoặc Formatter tùy chỉnh

Giả sử API nhận query parameter `direction=asc` hoặc `direction=desc` và muốn chuyển thành enum:

```java
public enum SortDirection {
    ASC, DESC
}
```

Đăng ký converter:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                SortDirection.class,
                value -> SortDirection.valueOf(
                        value.trim().toUpperCase(Locale.ROOT)));
    }
}
```

Sau đó controller có thể khai báo:

```java
@GetMapping("/sorted-products")
public Mono<String> sortedProducts(
        @RequestParam("direction") SortDirection direction) {

    return Mono.just(direction.name());
}
```

Đây là ví dụ converter đơn giản. Trong ứng dụng thực tế, hãy quyết định rõ có chấp nhận chữ hoa/thường, khoảng trắng, alias và giá trị không hợp lệ hay không. Không dùng converter để che giấu lỗi bằng một enum mặc định không được client yêu cầu.

## 7. Ví dụ Spring Boot WebFlux hoàn chỉnh

Ví dụ dưới đây kết hợp ba annotation trong một controller. Nó nhận page và các tag từ query, request ID/ngôn ngữ từ header, và theme từ cookie.

### 7.1. Cấu trúc dự án

Ví dụ dành cho Java 17+ và Spring Boot 3.x, dùng dependency management của Spring Boot:

```text
request-binding-demo/
  src/
    main/
      java/demo/
        RequestBindingApplication.java
        RequestMetadataController.java
    test/
      java/demo/
        RequestMetadataControllerTest.java
  build.gradle
```

Trong Gradle, dự án cần các dependency chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đoạn dependency này giả định dự án đã cấu hình plugin và BOM Spring Boot tương thích. Hãy để BOM quản lý version của Spring Framework, Reactor, Jackson và test libraries; không tự thêm một version Spring khác không tương thích.

### 7.2. Application class

Tệp `src/main/java/demo/RequestBindingApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RequestBindingApplication.class, args);
    }
}
```

### 7.3. Controller

Tệp `src/main/java/demo/RequestMetadataController.java`:

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpCookie;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class RequestMetadataController {

    @GetMapping("/api/demo")
    public Mono<DemoResponse> demo(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "tag", required = false)
            List<String> tags,
            @RequestHeader(name = "X-Request-Id", required = false)
            String requestId,
            @RequestHeader(name = "Accept-Language",
                    defaultValue = "vi")
            String language,
            @CookieValue(name = "theme", defaultValue = "light")
            String theme) {

        List<String> safeTags =
                tags == null ? List.of() : List.copyOf(tags);

        return Mono.just(new DemoResponse(
                page, safeTags, requestId, language, theme));
    }

    @GetMapping("/api/required")
    public Mono<String> required(
            @RequestParam("code") int code,
            @RequestHeader("X-Client") String client,
            @CookieValue("session") String session) {

        return Mono.just(
                "code=" + code
                        + ";client=" + client
                        + ";session=" + session);
    }

    @GetMapping("/api/all-headers")
    public Mono<Map<String, List<String>>> allHeaders(
            @RequestHeader HttpHeaders headers) {

        Map<String, List<String>> result =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        headers.forEach((name, values) ->
                result.put(name, List.copyOf(values)));

        return Mono.just(result);
    }

    @GetMapping("/api/all-cookies")
    public Mono<Map<String, List<String>>> allCookies(
            ServerHttpRequest request) {

        Map<String, List<String>> result = new TreeMap<>();

        request.getCookies().forEach((name, cookies) ->
                result.put(name, cookies.stream()
                        .map(HttpCookie::getValue)
                        .toList()));

        return Mono.just(result);
    }

    public record DemoResponse(
            int page,
            List<String> tags,
            String requestId,
            String language,
            String theme) {
    }
}
```

Giải thích các tham số của endpoint `/api/demo`:

- `page` có default là 1; query không cần gửi page.
- `tag` không bắt buộc; nhiều giá trị lặp được bind vào List.
- `X-Request-Id` không bắt buộc; nếu thiếu, response có thể chứa null ở trường requestId.
- `Accept-Language` mặc định là vi.
- Cookie `theme` mặc định là light.

Hai endpoint còn lại minh họa cách nhận mọi headers qua `HttpHeaders` và mọi cookie qua `ServerHttpRequest`. Endpoint `/api/required` cố ý yêu cầu đủ query, header và cookie để minh họa lỗi thiếu tham số.

### 7.4. Chạy và gọi endpoint

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Gọi endpoint với đủ dữ liệu:

```bash
curl -i 'http://localhost:8080/api/demo?page=2&tag=reactor&tag=webflux'   -H 'X-Request-Id: req-42'   -H 'Accept-Language: vi'   -b 'theme=dark'
```

Response JSON chính của ví dụ:

```json
{
  "page": 2,
  "tags": ["reactor", "webflux"],
  "requestId": "req-42",
  "language": "vi",
  "theme": "dark"
}
```

Thử gọi không truyền query/header/cookie:

```bash
curl -i 'http://localhost:8080/api/demo'
```

Kết quả có page 1, tags là mảng rỗng, requestId là null, language là vi và theme là light. Endpoint này cho phép thiếu các trường tùy chọn/default; endpoint `/api/required` thì không.

Gọi endpoint yêu cầu đủ ba nguồn:

```bash
curl -i 'http://localhost:8080/api/required?code=7'   -H 'X-Client: web'   -b 'session=session-123'
```

Nếu đủ cả ba giá trị, body là:

```text
code=7;client=web;session=session-123
```

Nếu thiếu `code`, `X-Client` hoặc cookie `session`, request không thỏa contract required và thường nhận HTTP 400.

### 7.5. Test binding với WebTestClient

Tệp `src/test/java/demo/RequestMetadataControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.MediaType.APPLICATION_JSON;

@WebFluxTest(RequestMetadataController.class)
class RequestMetadataControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bindsQueryHeaderAndCookie() {
        client.get()
                .uri("/api/demo?page=2&tag=reactor&tag=webflux")
                .header("X-Request-Id", "req-42")
                .header("Accept-Language", "vi")
                .cookie("theme", "dark")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.page").isEqualTo(2)
                .jsonPath("$.tags[0]").isEqualTo("reactor")
                .jsonPath("$.tags[1]").isEqualTo("webflux")
                .jsonPath("$.requestId").isEqualTo("req-42")
                .jsonPath("$.language").isEqualTo("vi")
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void usesDefaultsWhenValuesAreAbsent() {
        client.get()
                .uri("/api/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(1)
                .jsonPath("$.tags").isEmpty()
                .jsonPath("$.language").isEqualTo("vi")
                .jsonPath("$.theme").isEqualTo("light");
    }

    @Test
    void rejectsInvalidIntegerConversion() {
        client.get()
                .uri("/api/demo?page=not-a-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void rejectsMissingRequiredQueryHeaderOrCookie() {
        client.get()
                .uri("/api/required")
                .header("X-Client", "web")
                .cookie("session", "session-123")
                .exchange()
                .expectStatus().isBadRequest();

        client.get()
                .uri("/api/required?code=7")
                .cookie("session", "session-123")
                .exchange()
                .expectStatus().isBadRequest();

        client.get()
                .uri("/api/required?code=7")
                .header("X-Client", "web")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Test này dùng `@WebFluxTest` để khởi tạo controller và WebTestClient trong test context. Dependency `spring-boot-starter-test` cung cấp JUnit và test support tương ứng. Nếu dự án có security filter hoặc custom WebFlux configuration, có thể cần import/configure chúng theo test slice của dự án.

Chạy test:

```bash
./gradlew test
```

Các test xác nhận việc bind nhiều query values, header, cookie, giá trị mặc định và lỗi conversion/required. Không cần dựng một server thật cho các test binding cơ bản.

## 8. Khi nào cần truy cập ServerWebExchange trực tiếp?

Ba annotation rất tiện cho giá trị cụ thể đã biết tên. Nếu cần nhiều thông tin hơn hoặc xử lý dữ liệu ở mức request, controller có thể nhận:

```java
@GetMapping("/request-details")
public Mono<String> details(ServerWebExchange exchange) {
    String path = exchange.getRequest().getPath().value();
    String method = exchange.getRequest().getMethod().name();

    return Mono.just(method + " " + path);
}
```

`ServerWebExchange` chứa request, response, session và các thông tin liên quan. Một số trường hợp nên dùng trực tiếp:

- Cần đọc nhiều cookie, headers hoặc query parameters.
- Cần request URI, method, remote address hoặc attributes.
- Cần điều khiển response headers/status hoặc session.
- Cần thao tác với form/multipart theo API WebFlux.
- Cần kiểm tra một header/cookie có nhiều giá trị mà annotation đơn lẻ không biểu đạt đủ.

Không nên nhận exchange rồi tự parse mọi thứ trong mọi controller nếu annotation đã giải quyết rõ ràng. Dùng abstraction hẹp giúp method signature dễ đọc và dễ test.

## 9. Kết hợp với validation và xử lý lỗi

**Type conversion không đồng nghĩa với validation nghiệp vụ.** Chuyển chuỗi `"0"` thành int 0 thành công về kiểu dữ liệu, nhưng page 0 có thể không hợp lệ đối với API của bạn.

Có thể kiểm tra rõ trong service/controller:

```java
@GetMapping("/products")
public Mono<List<ProductDto>> products(
        @RequestParam(defaultValue = "1") int page) {

    if (page < 1) {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "page must be greater than or equal to 1"));
    }

    return productService.findPage(page);
}
```

Đây là **đoạn minh họa**, cần `ProductDto` và `productService` do ứng dụng định nghĩa. Cách khác là dùng Bean Validation với constraint phù hợp và cấu hình method validation tương thích Spring Framework version đang chạy.

Các lỗi thường gặp:

- Thiếu tham số bắt buộc: thường HTTP 400.
- Chuỗi không chuyển đổi được: thường HTTP 400.
- Giá trị chuyển đổi được nhưng sai nghiệp vụ: validation/service cần quyết định response.
- Header/cookie không hợp lệ về logic: phải kiểm tra rõ, không chỉ dựa vào việc Spring bind thành công.

Dùng `@RestControllerAdvice` hoặc cơ chế exception handling của WebFlux để chuẩn hóa response lỗi, tránh trả stack trace hoặc thông tin nội bộ cho client. Không catch mọi exception rồi biến thành HTTP 200.

## 10. Bảo mật khi nhận headers và cookies

### 10.1. Không tin dữ liệu client gửi

Query parameters, headers và cookie values đều là dữ liệu đầu vào không đáng tin. Chúng có thể bị sửa bởi client hoặc được gửi trực tiếp bởi script không phải browser. Cần validate độ dài, format, miền giá trị và quyền sử dụng trước khi đưa vào nghiệp vụ.

### 10.2. Không dùng request ID làm danh tính

Một client có thể tự gửi `X-Request-Id: admin-request` hoặc một chuỗi bất kỳ. Correlation ID hữu ích cho logging, nhưng không chứng minh người gửi là admin hay request đáng tin. Nếu cần danh tính, dùng authentication/authorization đúng chuẩn như Spring Security.

### 10.3. Cookie session cần được bảo vệ

Cookie mang session identifier hoặc thông tin nhạy cảm nên có chính sách phù hợp:

- **HttpOnly:** ngăn JavaScript đọc cookie qua API trình duyệt thông thường; không ngăn server đọc cookie.
- **Secure:** chỉ gửi cookie qua kết nối HTTPS theo chính sách browser.
- **SameSite:** hạn chế một số trường hợp gửi cookie cross-site, góp phần giảm CSRF nhưng không thay thế toàn bộ CSRF defense.
- **Path/Domain:** giới hạn phạm vi cookie được gửi.
- **Max-Age/Expires:** kiểm soát thời gian lưu.

Server có thể tạo cookie an toàn bằng ResponseCookie:

```java
ResponseCookie sessionCookie = ResponseCookie
        .from("session", opaqueSessionId)
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .body("session created");
```

Đây là đoạn minh họa trong handler cần import các kiểu tương ứng và có `opaqueSessionId` do hệ thống session tạo. Không lưu access token nhạy cảm trong cookie có thể bị đọc bởi JavaScript; không log session cookie hoặc giá trị Authorization.

### 10.4. CSRF khi xác thực dựa trên cookie

Browser có thể tự động gửi cookie theo phạm vi domain/path và SameSite policy. Vì vậy, nếu backend dùng cookie để xác thực, cần đánh giá CSRF cho các thao tác thay đổi trạng thái. `@CookieValue` chỉ giúp đọc cookie; nó không xác minh chữ ký, kiểm tra session, chống CSRF hay cấp quyền.

### 10.5. Forwarded headers và proxy

Các header như `Forwarded` hoặc `X-Forwarded-For` có thể được gửi bởi reverse proxy, nhưng cũng có thể bị client giả mạo nếu ứng dụng tin mọi nguồn. Chỉ tin forwarded headers từ proxy đã cấu hình/trusted. Không dùng IP/header do client gửi làm cơ chế xác thực duy nhất.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `@RequestParam` trong WebFlux đọc form fields như MVC | Controller không nhận dữ liệu form như mong đợi | Dùng `@ModelAttribute`/form data API hoặc `@RequestPart` cho multipart |
| Quên tên query/header/cookie | Binding không đúng hoặc tham số không được resolve | Khai báo `name/value` tường minh khi tên API khác tên biến |
| Dùng primitive cho giá trị tùy chọn | Không biểu diễn được null khi thiếu | Dùng wrapper, `Optional` hoặc default value |
| Thiếu required parameter | Handler không được gọi, thường trả 400 | Chọn required, Optional hoặc defaultValue theo contract |
| Gửi chuỗi sai kiểu | Conversion error | Kiểm tra input và trả lỗi 400 có cấu trúc |
| Nghĩ List luôn có đúng một phần tử | Bỏ mất query values lặp | Dùng List/array/MultiValueMap phù hợp |
| Tự split mọi header bằng dấu phẩy | Có thể phá grammar của header | Dùng HttpHeaders hoặc parser theo chuẩn header |
| Dùng @CookieValue để đọc tất cả cookies | Chỉ lấy một cookie theo tên | Dùng ServerHttpRequest.getCookies() |
| Dùng Servlet Cookie trong WebFlux | Trộn API Servlet và reactive stack | Dùng Spring HttpCookie/ServerHttpRequest |
| Tin cookie là dữ liệu đã xác thực | Có nguy cơ giả mạo session/logic | Validate session và quyền ở tầng bảo mật |
| Ghi log Authorization hoặc session cookie | Rò credential | Redact dữ liệu nhạy cảm |
| Nghĩ HttpOnly ngăn server đọc cookie | Hiểu sai thuộc tính cookie | HttpOnly giới hạn JavaScript phía browser, không giới hạn server |
| Tin X-Forwarded-For từ mọi client | Có thể giả mạo địa chỉ nguồn | Chỉ tin proxy được cấu hình |
| Bọc query/header/cookie argument trong Mono tùy tiện | Argument resolver không mong đợi reactive wrapper cho dữ liệu không blocking | Dùng kiểu giá trị thông thường hoặc Optional cho các tham số này |

## 12. Checklist thiết kế endpoint

Trước khi hoàn thành một controller, kiểm tra:

1. Dữ liệu nằm ở query, header, cookie, body hay path? Chọn đúng annotation.
2. Nếu dùng WebFlux, đã nhớ `@RequestParam` chỉ đọc query parameters chưa?
3. Tham số có bắt buộc không? Nếu không, chọn defaultValue, required=false hoặc Optional.
4. Kiểu Java có phản ánh đúng miền giá trị không? Tránh primitive cho tham số nullable.
5. Có giá trị lặp không? Chọn List/array/MultiValueMap/HttpHeaders phù hợp.
6. Type conversion có thể thất bại không? API trả lỗi 400 rõ ràng chưa?
7. Có validation nghiệp vụ sau conversion không?
8. Cookie/session và headers có dữ liệu nhạy cảm không? Đã tránh log và bảo vệ đúng chưa?
9. Nếu cần tất cả dữ liệu, nên dùng map/HttpHeaders/ServerHttpRequest thay vì viết nhiều tham số rời rạc?
10. Test có cover giá trị bình thường, thiếu, rỗng, lặp, sai định dạng và cookie/header bị thiếu chưa?

## 13. Tóm tắt lựa chọn

| Nhu cầu | Cách khai báo nên bắt đầu |
| --- | --- |
| Một query parameter | `@RequestParam("page") int page` |
| Query parameter có default | `@RequestParam(defaultValue = "1") int page` |
| Query parameter tùy chọn | `@RequestParam(required = false) Integer page` hoặc `Optional<Integer>` |
| Nhiều giá trị cùng query key | `@RequestParam("tag") List<String> tags` |
| Toàn bộ query parameters | `@RequestParam MultiValueMap<String,String> params` |
| Một request header | `@RequestHeader("X-Request-Id") String requestId` |
| Header tùy chọn | `@RequestHeader(value="X-Request-Id", required=false) String requestId` |
| Tất cả request headers | `@RequestHeader HttpHeaders headers` |
| Một cookie | `@CookieValue("theme") String theme` |
| Cookie có default | `@CookieValue(value="theme", defaultValue="light") String theme` |
| Tất cả cookies | `ServerHttpRequest.getCookies()` |

## 14. Tài liệu tham khảo

- [Spring Framework – WebFlux Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): danh sách các kiểu method argument được hỗ trợ và phạm vi reactive wrapper.
- [Spring Framework – @RequestParam trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html): query parameters, required/default, Optional, Map và MultiValueMap.
- [Spring Framework – @RequestHeader trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestheader.html): bind một header, nhiều giá trị, HttpHeaders và type conversion.
- [Spring Framework – @CookieValue trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/cookievalue.html): bind cookie theo tên và chuyển đổi kiểu.
- [Spring Framework – Type Conversion trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html): converters, formatters, empty string và null sau conversion.
- [Spring Framework – WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html): tổng quan handler methods và các kiểu argument/return value.

## 15. Ghi nhớ

Ba annotation giải quyết ba nguồn dữ liệu khác nhau: **`@RequestParam` đọc query parameters; `@RequestHeader` đọc request headers; `@CookieValue` đọc một cookie theo tên**. Spring tự bind và chuyển đổi giá trị sang kiểu tham số Java, đồng thời có quy tắc rõ về required, default và Optional.

Khi thiết kế controller WebFlux, hãy đặc biệt nhớ rằng `@RequestParam` không thay thế việc đọc form data/multipart như trong Servlet MVC. Dùng collection khi dữ liệu lặp, dùng `HttpHeaders` hoặc `ServerHttpRequest` khi cần toàn bộ metadata, và luôn validate dữ liệu đến từ client. Với cookie/session, bổ sung bảo vệ HttpOnly, Secure, SameSite, CSRF và xác minh session ở tầng bảo mật.
