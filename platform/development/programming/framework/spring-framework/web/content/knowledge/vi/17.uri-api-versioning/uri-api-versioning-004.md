# MvcUriComponentsBuilder và tạo liên kết tới controller trong Spring MVC

## 1. Mục tiêu và bài toán

Một ứng dụng Spring MVC có các endpoint `GET /books/{id}`, `GET /books/search?q=...` và nhiều trang HTML. Bạn muốn tạo **liên kết** trỏ đến những endpoint đó trong JSON, HTML hoặc redirect. Viết chuỗi `"/books/" + id` ban đầu rất dễ, nhưng khi controller đổi `@RequestMapping`, bổ sung context path, đổi tên tham số, đứng sau reverse proxy hoặc truyền ký tự đặc biệt, các URL tự ghép dễ bị lỗi.

**`MvcUriComponentsBuilder`** (package `org.springframework.web.servlet.mvc.method.annotation`) là công cụ của Spring MVC để **xây URI từ thông tin mapping của controller/method**, thay vì sao chép thủ công đường dẫn đã khai báo trong annotation.

Bài học này giúp bạn:

1. Phân biệt `URI`, `URL`, **URI template**, path variable, query parameter và **link tới endpoint/controller**.
2. Hiểu quan hệ `MvcUriComponentsBuilder` với `UriComponentsBuilder`, `ServletUriComponentsBuilder`, `@RequestMapping`, `@PathVariable` và `@RequestParam`.
3. Tạo link bằng `fromController`, `fromMethodName`, `fromMethodCall(on(...))`, `fromMethod`, `fromMappingName`; biết khi nào mỗi API phù hợp.
4. Hiểu **giới hạn proxy** của `on(...)` — đặc biệt với kiểu trả về `final` như `String`.
5. Xây URI có **base URL tùy chỉnh** bằng `relativeTo` hoặc overload nhận `UriComponentsBuilder`, xử lý context path/proxy và query encoding.
6. Tạo ví dụ **Java 17+, Spring Boot 3.x, Spring Framework 6.x** có controller HTML, API trả link JSON và MockMvc tests.
7. Tránh lỗi open redirect, URI injection, sinh URL nội bộ thay vì HTTPS công khai, chọn nhầm mapping hoặc truyền dữ liệu không được encode.

**Phạm vi:** Spring MVC chạy trên Servlet stack. WebFlux có các tiện ích URI riêng và ngữ cảnh request khác. Bài tập dùng API `MvcUriComponentsBuilder` trong Spring Framework 6.2; các chi tiết có thể thay đổi ở Framework 7 và Spring Boot 4.

## 2. Tại sao không nên nối đường dẫn thủ công?

Giả sử controller:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {
    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail").addObject("id", id);
    }
}
~~~

Đây là đoạn minh họa. Khi viết link theo kiểu:

~~~java
String url = "/books/" + id;
~~~

nó không còn đúng vì class có prefix `/catalog`. Sửa thành `"/catalog/books/" + id` cũng tạo **hai nơi khai báo cùng một route**; sau một lần refactor, link có thể bị bỏ sót.

Một vấn đề khác là **context path**: nếu ứng dụng được deploy dưới `/learning`, link tuyệt đối có thể là `https://example.com/learning/catalog/books/7`, không phải `/catalog/books/7`. Trong môi trường có proxy, ứng dụng bên trong có thể thấy host `localhost:8080` trong khi bên ngoài là `https://learning.example.com`.

Và còn **encoding**: nếu path variable là chuỗi có dấu cách, ký tự `/`, `?`, `#` hoặc query chứa `&`, việc nối URL sai dễ thay đổi cấu trúc đường dẫn/query. Tạo URI theo template và encode thành phần đúng ngữ cảnh sẽ an toàn và dễ bảo trì hơn.

## 3. Nhìn toàn cảnh: controller mapping → URI template → URI hoàn chỉnh

~~~text
@Controller / @RestController
  |
  +-- @RequestMapping("/catalog/books")
        |
        +-- @GetMapping("/{id}")
        |       @PathVariable("id")
        |
        +-- @GetMapping("/search")
                @RequestParam("q"), @RequestParam("page")

MvcUriComponentsBuilder
  |
  +-- đọc metadata mapping từ class/method
  +-- kết hợp base URL (scheme, host, port, context path)
  +-- đóng góp path variables và query parameters
  +-- trả UriComponentsBuilder
        |
        +-- build / buildAndExpand
        +-- encode đúng ngữ cảnh
        +-- toUri() hoặc toUriString()
                |
                v
   https://example.com/catalog/books/7
~~~

`MvcUriComponentsBuilder` **không gửi HTTP request**, không chạy business logic để tìm resource, và không tự bảo đảm đích tồn tại. Nó chỉ xây URI theo metadata mapping của controller trong ứng dụng hiện tại hoặc class được tham chiếu.

Từ đó có hai khái niệm rất khác:

- **Handler mapping**: định nghĩa Spring MVC dùng để match request đến controller. Ví dụ `@GetMapping("/{id}")`.
- **Link generation**: xây một URI được kỳ vọng tương ứng với mapping ấy. Dù dùng cùng annotation, link vẫn cần base URL đúng, các URI variables còn thiếu được điền đầy đủ và client có quyền truy cập.

Không gọi `controller.detail(7)` thật chỉ để lấy URI: sẽ thực thi logic, dựng model, có thể truy vấn DB. Với builder, bạn chỉ cần metadata của method và **giá trị đối số** liên quan đến URL.

## 4. API cốt lõi của `MvcUriComponentsBuilder`

Class nằm trong:

~~~java
import org.springframework.web.servlet.mvc.method.annotation.MvcUriComponentsBuilder;
~~~

Các cách xây link:

| Cách gọi | Nguồn metadata | Ưu điểm | Cần lưu ý |
| --- | --- | --- | --- |
| `fromController(BookController.class)` | Mapping cấp class | Dễ lấy base URL của một controller | Chưa biết method/variable cụ thể |
| `fromMethodName(BookController.class, "detail", 7L)` | Class + tên method + arguments | Không tạo proxy; dùng được với return type `String` | Tên method dạng chuỗi, overload trùng có thể mơ hồ |
| `fromMethodCall(on(BookController.class).detail(7L))` | Method invocation được ghi lại bởi proxy | Gần giống tham chiếu method có kiểm tra kiểu khi biên dịch | Return type/class/method phải hỗ trợ proxy |
| `fromMethod(BookController.class, method, args)` | Java Reflection `Method` | Rõ method khi đã có reflection | Verbose, cần `Method` chính xác |
| `fromMappingName("BC#detail")` | Tên mapping đăng ký trong MVC | Hữu ích khi định danh mapping rõ ràng | Tên phụ thuộc quy ước/naming strategy, mapping phải có |
| `relativeTo(base).withMethodName(...)` | Base URL cung cấp riêng + metadata controller | Dùng ngoài request, multi-tenant/locale base | Base phải được kiểm soát, tránh tạo link độc hại |

Các `fromXxx` không trả ngay `String` trong mọi trường hợp: phần lớn trả **`UriComponentsBuilder`** để bạn có thể tiếp tục `build()`, `buildAndExpand(...)`, `encode()`, `toUri()`.

### Vai trò của `UriComponentsBuilder` và `UriComponents`

~~~java
UriComponentsBuilder builder = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "detail", 7L);

UriComponents components = builder.build();
URI uri = components.encode().toUri();
~~~

Đây là **đoạn minh họa**, cần class `BookController` có handler detail như trên và import `UriComponentsBuilder`, `UriComponents`, `URI`. Đường dẫn sẽ dựa vào mapping `/catalog/books/{id}`, và `id=7` được cung cấp từ tham số của method.

Phân biệt hai thời điểm:

1. `UriComponentsBuilder` là đối tượng **đang ghép các thành phần URI**.
2. `UriComponents` là cấu trúc đã build nhưng có thể vẫn chứa URI variables chưa expand.
3. `buildAndExpand(...)` hoặc `expand(...)` điền biến còn lại.
4. `encode()` đảm bảo những ký tự cần encode được chuyển sang percent encoding theo quy tắc của API đang sử dụng.
5. `toUri()` trả `java.net.URI` phù hợp dùng cho `Location`, link JSON hoặc các API nhận URI.

Trong nhiều link có số ID đơn giản, `build().encode().toUri()` là đủ. Khi giá trị biến có ký tự reserved, đọc kỹ phần **URI encoding** phía dưới; encoding một URI sau khi mọi dữ liệu đã expand **khác** encoding URI template trước khi expand.

## 5. `fromController`: lấy URI tới mapping cấp class

Giả sử:

~~~java
@Controller
@RequestMapping("/catalog/books")
class BookController {
    // ...
}
~~~

Từ một HTTP request hiện tại:

~~~java
URI base = MvcUriComponentsBuilder
        .fromController(BookController.class)
        .build()
        .toUri();
~~~

Nếu request công khai là `https://shop.example.com/` và ứng dụng không có context path, base thường tương ứng:

~~~text
https://shop.example.com/catalog/books
~~~

**Đây là mapping cấp class, không phải URL chi tiết sách.** Nếu class khai báo nhiều route alternatives, Javadoc lưu ý `fromController` chỉ chọn **mapping đầu tiên**. Nó không thể tự quyết định một ID/method nghiệp vụ khi class chứa nhiều endpoint.

Ví dụ khai báo class mapping `/stores/{storeId}/books`, từ class-level URI sẽ còn biến `{storeId}`; phải expand:

~~~java
URI uri = MvcUriComponentsBuilder
        .fromController(StoreBookController.class)
        .buildAndExpand(42L)
        .encode()
        .toUri();
~~~

Đoạn này là **minh họa** với class `StoreBookController` chưa định nghĩa trong demo. Số `42` là ví dụ cho biến class-level `storeId`. Không gọi `toUri()` với template variables chưa được điền, trừ khi API thực sự cần một URI template chứ không phải URI cụ thể.

## 6. `fromMethodName`: tạo link theo method và tham số

Ví dụ Spring MVC controller:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail")
                .addObject("id", id);
    }

    @GetMapping("/search")
    public ModelAndView search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0") int page) {
        return new ModelAndView("book-search")
                .addObject("q", q)
                .addObject("page", page);
    }
}
~~~

Liên kết tới sách số 7:

~~~java
URI detail = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

Liên kết tới danh sách tìm kiếm:

~~~java
URI search = MvcUriComponentsBuilder
        .fromMethodName(BookController.class, "search", "spring", 0)
        .build()
        .encode()
        .toUri();
~~~

Với base URL `http://localhost:8080` và context path rỗng, hai kết quả dự kiến:

~~~text
http://localhost:8080/catalog/books/7
http://localhost:8080/catalog/books/search?q=spring&page=0
~~~

**Đây là các kết quả minh họa khi server nhận request với scheme/host/port tương ứng**, không phải stdout của một chương trình `main`; thứ tự query parameters có thể theo Spring contribution/order thực tế. Không hardcode domain trong unit test khi không kiểm soát request host.

### Tên tham số và `@RequestParam`

Những tham số method được đánh dấu `@PathVariable` và `@RequestParam` chủ yếu quyết định phần URI mà `MvcUriComponentsBuilder` có thể đóng góp. Tham số `Model`, `HttpServletRequest`, `Principal`, `BindingResult` và service nội bộ **không tự biến thành query string** chỉ vì method có chúng.

**Dùng tên annotation tường minh** là một thói quen tốt:

~~~java
@GetMapping("/{id}")
public ModelAndView detail(@PathVariable("id") long id) { /* ... */ }
~~~

Điều này giảm sự phụ thuộc vào Java parameter metadata (`-parameters`) khi Spring tìm tên biến, nhất là với build đặc biệt.

### Hạn chế tên method dạng String

`fromMethodName(BookController.class, "detail", 7L)` dùng tên **method Java**, không phải URL segment hay tên `@GetMapping`. Nếu đổi tên method, đoạn String có thể không được Java compiler bắt lỗi; thường chỉ phát hiện khi chạy/test. Nếu class có nhiều overload tên `detail`, Javadoc có thể ném `IllegalArgumentException` vì không tìm được duy nhất method phù hợp. Khi đó:
- Đặt tên method khác nhau cho rõ ràng;
- Dùng `fromMethod(Class, Method, args)` với reflection chính xác;
- Hoặc dùng `fromMethodCall(on(...))` nếu signature proxy hỗ trợ.

## 7. `fromMethodCall(on(...))`: liên kết bằng proxy theo kiểu method call

Spring hỗ trợ cách gọi giống một invocation thật:

~~~java
import static org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder.on;

URI uri = MvcUriComponentsBuilder
        .fromMethodCall(on(BookController.class).detail(7L))
        .build()
        .encode()
        .toUri();
~~~

Chú ý: `on(BookController.class).detail(7L)` là lời gọi trên một **proxy ghi lại invocation** để builder trích thông tin method và arguments. Nó **không chạy** thân method `detail`, không truy vấn database và không render template. Không nên nhầm nó với `new BookController().detail(7L)`.

### 7.1. Lợi ích

- Refactor tên method thường được compiler phát hiện ở call site.
- Kiểu tham số được Java compiler kiểm tra: `detail(7L)` tương thích `long`.
- Với method có nhiều tham số, mã thường dễ liên hệ tới controller method hơn kiểu tên String.

### 7.2. Giới hạn kỹ thuật rất quan trọng: return type `final`

Javadoc Spring Framework 6.2 cảnh báo method dùng với `fromMethodCall` có một ràng buộc về **proxy return type**. Một method trả kiểu **`String`** để dùng làm view name thường **không phù hợp**, vì `String` là class `final`, không tạo proxy subclass theo cơ chế này.

Ví dụ không nên làm:

~~~java
@GetMapping("/page")
public String page() {
    return "page-template";
}

// Không dùng từ proxy trong ví dụ này:
MvcUriComponentsBuilder.fromMethodCall(
        on(PageController.class).page());
~~~

Đoạn trên là **mẫu minh họa không phù hợp**, không phải hướng dẫn chạy. Một số code biên dịch được nhưng thất bại khi tạo proxy/invocation record. **Không có nghĩa method trả `String` là sai trong Spring MVC**: đó là return type hợp lệ để render view; chỉ phương pháp link generation bằng `fromMethodCall(on(...))` bị hạn chế.

Các hướng giải quyết:

1. Nếu muốn giữ controller trả `String`, dùng `fromMethodName(PageController.class, "page")`, không đổi hành vi controller.
2. Nếu thiết kế handler phù hợp, trả một kiểu **không final** như `ModelAndView`, cho phép builder proxy theo pattern Spring docs.
3. Với method không tiện proxy, có thể dùng `fromMethod` với Reflection `Method` chính xác.

**Ngoài return type**, class/method không thể proxy (ví dụ class/method `final` trong một số hình thức proxy) cũng gây hạn chế. Không nên đổi một API public chỉ vì mong muốn tạo link “trông đẹp” bằng proxy; hãy chọn builder API tương thích với thiết kế hiện tại.

### 7.3. Class-level `@PathVariable` còn thiếu

Theo ví dụ chính thức:

~~~java
@Controller
@RequestMapping("/hotels/{hotel}")
public class BookingController {

    @GetMapping("/bookings/{booking}")
    public ModelAndView getBooking(
            @PathVariable("booking") Long booking) {
        return new ModelAndView("booking");
    }
}
~~~

Ở đây **method parameter chỉ cung cấp `booking`**, chưa cung cấp `hotel` khai báo ở class-level. Cần điền biến còn lại:

~~~java
URI uri = MvcUriComponentsBuilder
        .fromMethodCall(
                on(BookingController.class).getBooking(21L))
        .buildAndExpand(42L)  // hotel
        .encode()
        .toUri();
~~~

Với host `https://example.com`, link sau khi mở rộng thường là:

~~~text
https://example.com/hotels/42/bookings/21
~~~

Đây là điểm quan trọng: **builder không tự suy đoán mọi biến** từ browser URL, service hay model. Khi phương thức không có argument cho biến class-level, bạn vẫn phải `buildAndExpand` bằng giá trị còn thiếu.

## 8. `fromMethod` và `fromMappingName`: dùng khi nào?

### 8.1. `fromMethod` dùng Reflection `Method`

Nếu thư viện của bạn có sẵn `java.lang.reflect.Method`, có thể xây URI từ method chính xác:

~~~java
Method javaMethod = BookController.class
        .getMethod("detail", long.class);

URI uri = MvcUriComponentsBuilder
        .fromMethod(BookController.class, javaMethod, 7L)
        .build()
        .encode()
        .toUri();
~~~

Đây là đoạn minh họa trong một method Java `throws ReflectiveOperationException`, cần import `java.lang.reflect.Method` và `java.net.URI`. `getMethod` chỉ tìm public method với signature được chọn, vì vậy phân biệt được các overload nếu bạn truyền đúng parameter types.

**Không lưu cache một `Method` của controller cũ qua lần triển khai phiên bản khác** mà không kiểm soát. Metadata reflection vẫn phụ thuộc Java bytecode/controller mapping thực tế. Cũng không lấy tên Java method trực tiếp từ query parameter rồi phản chiếu tùy ý: chọn method theo contract server.

### 8.2. `fromMappingName` dựa trên tên mapping

Spring MVC có thể đăng ký mapping name theo cấu hình mặc định hoặc qua thuộc tính `name` của `@RequestMapping`/`@GetMapping`. Ví dụ annotation:

~~~java
@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping(path = "/{id}", name = "details")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail");
    }
}
~~~

Ở naming strategy mặc định, tên mapping có thể kết hợp **chữ viết hoa đầu của tên controller** và **tên explicit của method** theo dạng `BC#details` (với `BookController` → `BC`). Cách này hữu ích khi muốn định danh handler bằng một tên được đăng ký, nhưng tên cụ thể phải kiểm tra trong `HandlerMapping` runtime. Với nhiều class tên tương tự, customize naming strategy hoặc mapping trùng, có thể mơ hồ.

Một ví dụ khái niệm về builder (phụ thuộc mapping name đã tồn tại):

~~~java
MvcUriComponentsBuilder.MethodArgumentBuilder builder =
        MvcUriComponentsBuilder.fromMappingName("BC#details");

// Dùng builder.arg(index, value) để gắn tham số method
// theo chỉ số trước khi tạo URI.
~~~

`fromMappingName` **không tra cứu một đường dẫn từ database**; nó tra mapping đã được đăng ký với `RequestMappingHandlerMapping`. Nếu không tìm được mapping hoặc tên không duy nhất, có thể phát sinh exception. Khi làm ứng dụng thông thường, `fromMethodName` hoặc `fromMethodCall` thường dễ kiểm tra hơn.

## 9. Base URL và cách dùng `relativeTo`

Khi đang xử lý một request Servlet thông thường, các static `fromXxx` của `MvcUriComponentsBuilder` thường lấy scheme, host, port, context path và servlet path từ **request hiện tại** nhờ các tiện ích Servlet URI.

Nhưng sẽ có lúc không có request đang active:
- Job nền sinh email xác nhận.
- Batch sinh tài liệu.
- Service tạo callback URL ngoài một request.
- Liên kết cần thêm locale prefix đã bị middleware loại khỏi request.
- Ứng dụng cần cố định public origin được quản trị thay vì phụ thuộc raw Host header.

Khi đó hãy dùng base URL **được cấu hình và tin cậy**:

~~~java
UriComponentsBuilder publicBase =
        UriComponentsBuilder.fromUriString(
                "https://docs.example.com/app");

URI uri = MvcUriComponentsBuilder
        .relativeTo(publicBase)
        .withMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

Giả sử `BookController` có class mapping `/catalog/books` và method mapping `/{id}`, kết quả:

~~~text
https://docs.example.com/app/catalog/books/7
~~~

Đây là đoạn minh họa trong một method, cần import `UriComponentsBuilder` và `URI`. Các instance-based `withController`, `withMethodName`, `withMethodCall`, `withMethod` giúp tái dùng base URL do bạn chọn. Tương đương, một số overload static `fromMethodName(base, ...)` hoặc `fromController(base, ...)` nhận chính base builder.

**Lưu ý:** base path `/app` ở đây là prefix public URL mà bạn **chủ động** thêm. Nếu nó đã có trong context path, thêm lần nữa có thể dẫn đến `/app/app/...`. Trong ứng dụng nhiều reverse proxy hoặc path rewrite, thiết kế rõ ràng “ai sở hữu prefix” trước khi build URL.

### Tạo base từ context path hiện hành

Khi muốn base theo request nhưng thêm đoạn locale:

~~~java
UriComponentsBuilder base =
        ServletUriComponentsBuilder.fromCurrentContextPath()
                .path("/vi");

URI uri = MvcUriComponentsBuilder.relativeTo(base)
        .withMethodName(BookController.class, "detail", 7L)
        .build()
        .encode()
        .toUri();
~~~

Đây là đoạn minh họa trong **request thread có ServletRequestAttributes**, không dùng nguyên trong background job nếu không có request. Nó có thể tạo đường dẫn kiểu `/vi/catalog/books/7` dựa trên context hiện hành. Đảm bảo prefix locale `/vi` thật sự được route/gateway chấp nhận, đừng thêm một path “có vẻ hợp lý” mà không tồn tại.

## 10. Encoding: path variable và query parameter không giống nối String

Spring URI builder hỗ trợ URI templates với hai cách encode rất đáng chú ý:

- **`UriComponentsBuilder#encode()` trước khi expand biến**: encode template và **encode nghiêm ngặt giá trị biến**, kể cả reserved characters có thể làm thay đổi cấu trúc.
- **`UriComponents#encode()` sau khi expand biến**: encode theo URI component, có thể **giữ lại reserved characters hợp lệ** trong một component (ví dụ dấu chấm phẩy trong path).

Đối với input của người dùng, thường muốn biến được coi như **opaque data** thay vì cú pháp URI. Ví dụ thuần `UriComponentsBuilder`:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/catalog/books/{id}")
        .queryParam("q", "{q}")
        .encode() // QUAN TRỌNG: encode template trước khi expand
        .buildAndExpand("a/b", "Java & Spring")
        .toUri();
~~~

Kết quả:

~~~text
/catalog/books/a%2Fb?q=Java%20%26%20Spring
~~~

Trong đó:
- `/` nằm trong `id` được encode thành `%2F`, vì nó **là dữ liệu của biến**, không phải ranh giới hai path segments.
- `&` trong `q` được encode `%26`, tránh trở thành dấu phân tách query parameters.
- Dấu cách thành `%20`.

`MvcUriComponentsBuilder` giúp gắn controller method arguments vào URL. Tuy nhiên nếu bạn cần **đảm bảo reserved characters trong biến được encode nghiêm ngặt**, kiểm tra cách API đã đóng góp/expand args trước khi gọi `encode()` và viết test URI cụ thể. Đừng giả định `build().encode()` sau mọi argument substitution sẽ encode mọi reserved character. Với tài nguyên định danh bằng số hoặc slug đã validate thì vấn đề đơn giản hơn; với free-form input chứa `/`, `&`, `?`, `#` cần chọn pipeline URI template/encoding phù hợp.

**Tránh double encoding:** nếu input đã chứa `%2F`, encode thêm lần nữa có thể tạo `%252F`. Nên định nghĩa contract: truyền **raw logical values** vào URI builder, encode đúng một lần tại điểm tạo URI.

### Link trong HTML template

Với Thymeleaf trong Spring MVC, đôi khi biểu thức link template đơn giản hơn:

~~~html
<a th:href="@{/catalog/books/{id}(id=${bookId})}">
  Xem sách
</a>

<a th:href="@{/catalog/books/search(q=${query},page=0)}">
  Tìm kiếm
</a>
~~~

Thymeleaf xử lý URI template và context path theo tích hợp template engine. `MvcUriComponentsBuilder` phù hợp khi bạn muốn dựa trên **Java controller mapping**; Thymeleaf link expression phù hợp với template HTML tĩnh rõ route. Cả hai vẫn phải dùng input hợp lệ và kiểm tra authorization cho endpoint đích.

### Không ghép query raw

Ví dụ cần tránh:

~~~java
String unsafe = "/search?q=" + userInput;
~~~

Nếu `userInput` chứa `&admin=true`, nó có thể biến thành query parameter mới, không còn là một giá trị `q`. Dùng URI template + component encoding (và server-side validation) thay vì nối String.

## 11. Tên route, ngữ cảnh URI và phiên bản API

Trong module “URI và phiên bản API”, link generation đặc biệt có giá trị khi endpoint có prefix:

~~~java
@RestController
@RequestMapping("/api/v1/books")
public class BookApiV1Controller {
    @GetMapping("/{id}")
    public BookDto detail(@PathVariable long id) { /* ... */ }
}
~~~

Đây là code mô tả, chưa là file biên dịch độc lập; `BookDto` cần định nghĩa. Dùng `fromMethodName` để xây link từ mapping `/api/v1/books/{id}`. Khi chuyển đường dẫn sang `/api/v2/books/{id}`, liên kết mới đi theo metadata code, nhưng **không tự migrate các client đang giữ URL cũ**.

Các quy tắc thiết kế:
- **Phiên bản URI là một phần API contract**. Builder chỉ phản chiếu mapping hiện tại; cần giữ backward compatibility hoặc redirect/deprecation policy cho v1 nếu client còn dùng.
- Nếu controller có cả `@RequestMapping(path={"/v1/books","/v2/books"})`, builder có thể gặp **nhiều mapping alternatives**; nó không biết client nên chọn version nào. Tránh pattern mơ hồ cho link công khai hoặc đưa version vào base/path một cách tường minh.
- Mappings dùng **HTTP headers** hoặc **media type versioning** có thể tạo cùng path cho nhiều handler. Builder tạo URI không tự thêm `Accept`, `Content-Type` hoặc authorization header.
- Link tới `GET` không tự thể hiện `POST` payload. Nếu muốn HATEOAS với HTTP method/media type, cần format/link relation riêng; `MvcUriComponentsBuilder` chỉ tạo URI.
- Link generation không thay server routing tests; route có thể yêu cầu regex/converter/validator mà dữ liệu builder tạo ra chưa chắc thỏa.

## 12. Ví dụ Spring Boot 3.x chạy được

Ứng dụng demo xây các link theo mapping của controller hiển thị sách, trả lại URL trong JSON để dễ quan sát và có hai template Thymeleaf đơn giản.

### 12.1. Tạo project

Chọn **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies:

- `spring-boot-starter-web` — Spring MVC, Jackson và embedded Servlet container.
- `spring-boot-starter-thymeleaf` — render hai view HTML.
- `spring-boot-starter-test` — JUnit 5 và MockMvc.

Package chính là `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/BookController.java
src/main/java/com/example/demo/BookLinkController.java
src/main/resources/templates/book-detail.html
src/main/resources/templates/book-search.html
src/test/java/com/example/demo/BookLinksTest.java
~~~

**Các file Java dưới đây là code Java 17 có thể đưa trực tiếp vào một project Spring Boot 3.x đúng dependencies.** Các URL `http://localhost:8080` chỉ áp dụng khi chạy server ở cổng mặc định và không có context path tùy chỉnh.

### 12.2. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.3. `BookController.java`: mapping làm nguồn tạo URI

~~~java
package com.example.demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.ModelAndView;

@Controller
@RequestMapping("/catalog/books")
public class BookController {

    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable("id") long id) {
        return new ModelAndView("book-detail")
                .addObject("id", id);
    }

    @GetMapping("/search")
    public ModelAndView search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0")
            int page) {

        return new ModelAndView("book-search")
                .addObject("q", q)
                .addObject("page", page);
    }
}
~~~

Handler `detail` và `search` đều trả **`ModelAndView`**, thay vì `String`, để minh họa tương thích với cơ chế proxy của `fromMethodCall(on(...))`. Trong ứng dụng HTML thông thường, bạn vẫn có thể trả `String` view name và chọn `fromMethodName` để dựng link.

Các endpoint chạy:
- `GET /catalog/books/7` — render `book-detail.html`.
- `GET /catalog/books/search?q=spring&page=0` — render `book-search.html`.

### 12.4. `BookLinkController.java`: tạo link bằng hai API

~~~java
package com.example.demo;

import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder;

import static org.springframework.web.servlet.mvc.method.annotation
        .MvcUriComponentsBuilder.on;

@RestController
@RequestMapping("/api/links")
public class BookLinkController {

    @GetMapping("/books/{id}")
    public Links links(@PathVariable("id") long id) {

        URI byMethodName = MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "detail", id)
                .build()
                .encode()
                .toUri();

        URI byMethodCall = MvcUriComponentsBuilder
                .fromMethodCall(
                        on(BookController.class).detail(id))
                .build()
                .encode()
                .toUri();

        URI search = MvcUriComponentsBuilder
                .fromMethodName(BookController.class, "search",
                        "spring", 0)
                .build()
                .encode()
                .toUri();

        return new Links(
                byMethodName.toString(),
                byMethodCall.toString(),
                search.toString());
    }

    public record Links(String byMethodName,
                        String byMethodCall,
                        String search) {}
}
~~~

**Giải thích thật kỹ:**

1. Controller đang nhận request `GET /api/links/books/7`; nó **không hardcode** path `/catalog/books/{id}` ở bất kỳ chỗ nào trong `BookLinkController`.
2. `fromMethodName(...)` lấy mapping của `BookController.detail`, đóng góp `id=7`.
3. `fromMethodCall(on(...).detail(id))` dùng proxy để **ghi nhận method + argument**, không chạy handler detail; output path tương đương phương án trước.
4. `BookController.detail` trả `ModelAndView` là non-final, tránh vấn đề `String` final trong builder proxy.
5. Link search sử dụng `@GetMapping("/search")` và `@RequestParam("q")`, `@RequestParam("page")`, không tự nối `?q=`.
6. Mặc định static builder có thể lấy **base URL từ request Servlet hiện tại**. Nếu ứng dụng đứng sau proxy chưa xử lý forwarded headers đúng, response có thể dùng host/port nội bộ.
7. `Links` là Java record cho JSON; Jackson serialize các field `byMethodName`, `byMethodCall`, `search`.

### 12.5. `book-detail.html` và `book-search.html`

**`src/main/resources/templates/book-detail.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Chi tiết sách</title>
</head>
<body>
  <h1>Chi tiết sách</h1>
  <p>ID: <span th:text="${id}">0</span></p>
  <a th:href="@{/catalog/books/search(q='spring',page=0)}">
    Tìm kiếm sách
  </a>
</body>
</html>
~~~

**`src/main/resources/templates/book-search.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Tìm kiếm sách</title>
</head>
<body>
  <h1>Tìm kiếm</h1>
  <p>Truy vấn: <span th:text="${q}">query</span></p>
  <p>Trang: <span th:text="${page}">0</span></p>
</body>
</html>
~~~

Hai template sử dụng `th:text` để escape dữ liệu hiển thị. URI link builder **không** có trách nhiệm HTML-escape toàn bộ dữ liệu ở mọi chỗ; khi đưa URL vào HTML attribute, template engine vẫn cần dùng thuộc tính an toàn như `th:href` (hoặc HTML attribute escaping đúng ngữ cảnh).

### 12.6. Gọi endpoint bằng curl

Chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper nhưng đã cài Maven, dùng `mvn spring-boot:run`.

Gọi:

~~~bash
curl -i http://localhost:8080/api/links/books/7
~~~

Kết quả JSON kỳ vọng với cấu hình mặc định và request host `localhost:8080`:

~~~json
{
  "byMethodName": "http://localhost:8080/catalog/books/7",
  "byMethodCall": "http://localhost:8080/catalog/books/7",
  "search": "http://localhost:8080/catalog/books/search?q=spring&page=0"
}
~~~

Giá trị trong ví dụ là **hình thức dữ liệu dự kiến**, không phải output thực nghiệm đã chạy trong workspace. Vị trí cổng, context path, proxy và cấu hình `server.forward-headers-strategy` có thể khiến absolute URLs khác.

Mở link trong browser:

~~~text
http://localhost:8080/catalog/books/7
http://localhost:8080/catalog/books/search?q=spring&page=0
~~~

Nếu controller đổi `@RequestMapping("/catalog/books")` thành `@RequestMapping("/library/books")`, link do builder sinh cũng đổi theo metadata mapping (miễn code ứng dụng và tests đều phản ánh controller mới).

## 13. MockMvc: kiểm chứng link thực tế và khớp mapping

Test cần kiểm tra:
- Link theo tên method và proxy call trùng nhau.
- Path được sinh từ `@RequestMapping`, không từ một string hand-written.
- Query parameters có tên đúng.
- Một link trả về có thể dùng để gọi endpoint tương ứng.
- Sau khi đổi mapping, test cập nhật theo **contract API mong muốn**, chứ không chỉ kiểm tra hai builder cùng sai như nhau.

**`src/test/java/com/example/demo/BookLinksTest.java`**

~~~java
package com.example.demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void generatesLinksFromControllerMetadata() throws Exception {
        mockMvc.perform(get("/api/links/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.byMethodName")
                        .value("http://localhost/catalog/books/7"))
                .andExpect(jsonPath("$.byMethodCall")
                        .value("http://localhost/catalog/books/7"))
                .andExpect(jsonPath("$.search")
                        .value("http://localhost/catalog/books/search?q=spring&page=0"));
    }

    @Test
    void generatedDestinationHasWorkingControllerMapping()
            throws Exception {

        mockMvc.perform(get("/catalog/books/7"))
                .andExpect(status().isOk())
                .andExpect(view().name("book-detail"))
                .andExpect(model().attribute("id", 7L));
    }

    @Test
    void searchMappingBindsNamedQueryParameters() throws Exception {
        mockMvc.perform(get("/catalog/books/search")
                        .param("q", "spring")
                        .param("page", "0"))
                .andExpect(status().isOk())
                .andExpect(view().name("book-search"))
                .andExpect(model().attribute("q", "spring"))
                .andExpect(model().attribute("page", 0));
    }
}
~~~

**Về host trong MockMvc:** MockMvc builder `get("/...")` thường tạo mock request với scheme `http`, host `localhost`, port mặc định 80. Bởi vậy test mong đợi `http://localhost/...`. Khi chạy server thật mặc định cổng 8080, link tuyệt đối chứa `:8080`. Nếu project có custom mock request defaults, forward headers hoặc context path, test phải khai báo base/expected host theo cấu hình đó.

Test trên chủ yếu xác minh link generation và MVC mappings; không kết nối TCP thật. Đối với production, bổ sung **HTTP integration test qua reverse proxy** để đảm bảo public scheme/host/context path không bị rò rỉ domain nội bộ.

Chạy:

~~~bash
./mvnw test
~~~

Nếu có Spring Security trong project thật, MockMvc test cho các route HTML/API có thể cần authentication theo policy; những ví dụ ở đây không thêm Security để tập trung vào URI builder.

## 14. Link tuyệt đối sau reverse proxy: Forwarded và X-Forwarded-*

Với load balancer TLS termination:

~~~text
Client: https://api.example.com
           |
           v
Reverse proxy: HTTPS -> HTTP
           |
           v
Spring Boot: http://127.0.0.1:8080
~~~

Nếu builder chỉ nhìn request server-side đã bị proxy viết lại, nó có thể tạo URI sai `http://127.0.0.1:8080/catalog/books/7`, trong khi client cần `https://api.example.com/catalog/books/7`.

Proxy có thể gửi:
- `Forwarded: proto=https;host=api.example.com` theo RFC 7239.
- Hoặc `X-Forwarded-Proto: https`, `X-Forwarded-Host: api.example.com`, `X-Forwarded-Port: 443`, `X-Forwarded-Prefix: /app`.

Tài liệu Spring lưu ý `MvcUriComponentsBuilder`/`ServletUriComponentsBuilder` không tự tin tưởng/đọc trực tiếp các forwarded headers theo cách đầy đủ. Nên cấu hình xử lý **ở trước** URI building, như `ForwardedHeaderFilter` hoặc cơ chế container trusted proxy.

Trong Spring Boot 3.x, một cách bật xử lý forwarded headers ở framework level là:

~~~properties
server.forward-headers-strategy=framework
~~~

**Cực kỳ quan trọng về bảo mật:** chỉ bật khi có **reverse proxy đáng tin** ở trust boundary, nơi nó:
1. Xóa mọi `Forwarded` và `X-Forwarded-*` do client từ internet tự gửi.
2. Gắn header **mới**, chính xác theo public scheme/host/port/prefix.
3. Không cho app nhận trực tiếp traffic tùy ý bypass reverse proxy nếu app tin những header này.

Nếu bất kỳ client nào có thể tự đưa `X-Forwarded-Host: evil.example` và server tin nó, link tuyệt đối được trả trong email hoặc `Location` có thể bị **host header poisoning**. Với email/password-reset links, tốt hơn dùng một **public base URL** do server cấu hình và allowlist, không tự lấy Host header không xác thực.

Nếu không dùng forwarded headers để generate URL, có thể chủ động cung cấp base URI trong `relativeTo` được lấy từ trusted configuration. Không bật `ForwardedHeaderFilter` và native proxy handling hai lần một cách tùy tiện; có thể tạo context path/scheme sai hoặc trùng prefix.

## 15. `Location`, redirects và link trong JSON

Một API POST tạo resource thường cần header **`Location`** trỏ tới GET endpoint của resource vừa tạo. Ví dụ minh họa:

~~~java
@PostMapping("/books")
public ResponseEntity<Void> create(@RequestBody CreateBookRequest request) {
    Book saved = bookService.create(request);
    URI location = MvcUriComponentsBuilder
            .fromMethodName(BookController.class, "detail", saved.id())
            .build()
            .encode()
            .toUri();

    return ResponseEntity.created(location).build();
}
~~~

Đây là một **handler minh họa**, không thuộc runnable project ở phần 12. Cần service/DTO chưa định nghĩa, import `ResponseEntity`, `URI`, annotation MVC, và handler get-detail tương ứng. `ResponseEntity.created(location)` thường trả **201 Created** với header `Location`. Controller vẫn phải validate input, authorize request và xử lý transaction khi tạo sách.

**Không được** nhầm `Location` với `Content-Location`; ý nghĩa HTTP khác nhau. Builder chỉ dựng URI, không xác nhận resource đã được commit vào database.

### Relative URI hay absolute URI?

Một link như `/catalog/books/7` là **path-relative-to-origin**, còn `https://api.example.com/catalog/books/7` là absolute URI có scheme/authority. Cả hai có use case riêng:
- Với HTML nội bộ cùng host, root-relative paths dễ tránh rò rỉ internal host.
- Với JSON/HATEOAS, thông báo/email và `Location`, absolute URI thường tiện cho client nằm ngoài origin, nhưng phải có trusted public base.
- Nếu ứng dụng chạy dưới context path, root-relative URI phải chứa prefix đúng.
- Nếu API phục vụ nhiều domains/tenants, chọn public origin dựa trên cấu hình tenant được validate, không nhận arbitrary Host header.

Dùng `UriComponentsBuilder.fromPath("/...")` khi bạn chủ ý muốn xây relative path độc lập request; dùng `MvcUriComponentsBuilder` khi mục tiêu chính là liên kết theo **metadata của controller**.

## 16. An toàn khi dựng link

`MvcUriComponentsBuilder` không phải encoder/sanitizer phổ quát và không tạo quyền truy cập. Các nguyên tắc:

### 16.1. Không cho client điều khiển toàn bộ base URL

~~~java
// MẪU PHẢN DIỆN: không dùng URL untrusted làm base
UriComponentsBuilder base =
        UriComponentsBuilder.fromUriString(userSuppliedBaseUrl);
~~~

Nếu user kiểm soát scheme/host của base, link trả về có thể trỏ website độc hại. Nếu server dùng URL đó gọi ra bên ngoài, còn có rủi ro **SSRF**. Dùng allowlist host/scheme hoặc public origin do operator cấu hình.

### 16.2. Không dùng link builder thay authorization

Tạo URI `/admin/reports/7` không chứng minh người nhận có quyền đọc báo cáo. Authorization phải đặt tại endpoint GET, độc lập với việc link có xuất hiện trong UI/JSON hay không. Khi trả link tới resource private, cân nhắc hiển thị theo quyền và không phát lộ ID/metadata không cần thiết.

### 16.3. Không dùng query data thô làm cú pháp URI

Query text chứa `&`, `=`, `#`, dấu cách, Unicode cần encode đúng. Tránh manual concatenation và double-encoding. Với Path ID dạng UUID/long, validate type thường giúp giảm rủi ro reserved characters; nhưng không coi type validation là permission check.

### 16.4. Xử lý Redirect an toàn

Một URI tạo từ mapping **nội bộ được phép** thường dễ kiểm soát hơn redirect tới URL tùy ý do client đưa vào. Khi `Location` cần absolute base, hãy xác minh scheme/host trước. Tránh redirect kiểu `return "redirect:" + userInput;` vì dễ thành **open redirect**.

### 16.5. Không suy luận request method từ URI

URI `/api/books/7` không nói bạn phải GET hay DELETE. `MvcUriComponentsBuilder` đọc mapping để tạo path/query, nhưng nếu response cần mô tả HTTP method, media type, request body hay link relation, hãy cung cấp metadata riêng phù hợp (HAL/JSON:API/REST documentation...). Điều này đặc biệt quan trọng với API versioning bằng headers.

## 17. Lỗi thường gặp và quy trình debug

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh / sửa |
| --- | --- | --- |
| Link bị thiếu `/catalog` | Manual concatenation bỏ quên class-level mapping | Dùng `fromMethodName` hoặc builder theo controller |
| Link host `localhost:8080` thay vì HTTPS public | Proxy termination, forwarded headers chưa được xử lý | Trusted proxy config / `server.forward-headers-strategy` / `relativeTo` |
| Link bị lặp `/app/app` | Context path và base custom cùng thêm prefix | Chọn một nơi sở hữu base path |
| `fromMethodCall` fail với `String` | String final, proxy không tạo được | Chuyển sang `fromMethodName` hoặc return type phù hợp |
| `fromMethodName` không tìm thấy method | Java method name sai, overload mơ hồ | Kiểm tra method signature, dùng `fromMethod` |
| URI còn `{id}` | Chưa đóng góp/expand variable | `buildAndExpand` với biến còn thiếu |
| Query bị tách làm nhiều param | Ghép input chứa `&` chưa encode | URI template và encoding theo ngữ cảnh |
| Link sai port sau proxy | `X-Forwarded-Port`/Host/Proto không tin cậy hoặc sai | Chẩn đoán request wrapper và proxy headers |
| Generated URL gây open redirect | Base URL lấy thô từ client | Whitelist public origins và loại bỏ spoofed headers |
| Link tới 404 mặc dù builder không lỗi | Route phụ thuộc params/media type/auth hoặc mapping đã đổi | Test endpoint thực và contract version |
| `fromController` chọn đường bất ngờ | Controller có nhiều class-level mappings | Chọn method/mapping rõ ràng |
| Không tạo được link trong background job | Không có request-bound base URL | `relativeTo` từ trusted config |
| Unicode/space bị double encode | Dữ liệu đầu vào đã encoded | Truyền raw values, encode đúng một lần |
| Link tới version sai | Mapping alternatives/header versioning | Định nghĩa version contract rõ, kiểm thử |
| `@RequestParam` thiếu hoặc sai tên | Tên parameter/annotation chưa tường minh | Đặt `@RequestParam("q")` và test query |
| Link trong HTML thành XSS | Chèn URI/user data không escape trong attribute | Dùng Thymeleaf `th:href`, escaping và URL validation |

### Quy trình debug

1. Đọc **controller class-level `@RequestMapping`** và **method-level `@GetMapping`/`@PostMapping`**; xác định template và mọi URI variables.
2. Ghi nhận builder API đã dùng: `fromController`, `fromMethodName`, `fromMethodCall` hay `relativeTo`.
3. Kiểm tra argument được đánh dấu `@PathVariable`, `@RequestParam`; bổ sung class-level path variables qua `buildAndExpand`.
4. In/debug URI thực tế gồm scheme, host, port, contextPath và percent encoding — không chỉ path substring.
5. Kiểm tra forwarded headers tại gateway và sau filter nếu app đứng sau proxy; xóa header giả do client đưa tới.
6. Thử GET đúng URL trong môi trường test; nếu 404/405/401 hãy xem routing/auth chứ không chỉ builder.
7. Tạo MockMvc test khẳng định link và test destination mapping; thêm integration test qua reverse proxy với domain/HTTPS thật.
8. Review versioning, tenant prefixes, query encoding và authority security khi URL dùng trong email/`Location`.

## 18. Câu hỏi ôn tập

**1. Vì sao dùng `MvcUriComponentsBuilder` thay vì nối `"/books/" + id`?**

Vì builder dựa trên metadata `@RequestMapping` cấp class/method và tham số route, giảm trùng lặp hardcoded path khi code refactor, đồng thời kết hợp base URL theo request hoặc base tùy chỉnh.

**2. `fromMethodName` và `fromMethodCall` khác nhau như thế nào?**

`fromMethodName` tham chiếu tên Java method dạng chuỗi, không cần return-type proxy. `fromMethodCall` dùng proxy ghi invocation, có hỗ trợ kiểm tra signature khi biên dịch nhưng bị giới hạn về kiểu method/return type có thể proxy.

**3. Vì sao `String` return type có thể gây lỗi với `on(...)`?**

`String` là `final`; builder proxy không thể tạo subclass của kiểu này theo giới hạn được Spring documentation nêu. `String` vẫn hoàn toàn hợp lệ để render view; khi đó dùng `fromMethodName`.

**4. Nếu class route có `/hotels/{hotel}` nhưng method chỉ có `@PathVariable booking`, cần làm gì?**

`fromMethodName`/`fromMethodCall` nhận booking từ argument; dùng `buildAndExpand(hotelId)` để điền class-level variable còn thiếu.

**5. Đang tạo link trong background job thì có dùng base URL request hiện tại được không?**

Không nên, vì thường không tồn tại request context. Dùng `relativeTo` hoặc overload nhận base `UriComponentsBuilder` từ public URL tin cậy.

**6. Vì sao link ở production thành `http://localhost:8080` thay vì `https://example.com`?**

App đứng sau proxy HTTPS nhưng thông tin public scheme/host chưa được đưa đến request mà builder nhìn thấy. Xử lý forwarded headers ở trust boundary hoặc cấu hình public base cố định.

**7. Nếu input query là `Java & Spring` thì nối `?q=` có an toàn không?**

Không. Dấu `&` mang nghĩa phân cách query parameter. Dùng URI templates và encode component/variable đúng trước khi tạo URI.

**8. Builder tạo thành công link admin có nghĩa user được phép mở link không?**

Không. Link generation không thay authentication/authorization ở endpoint đích.

## 19. Checklist thực hành

1. Xem `MvcUriComponentsBuilder` là công cụ **dựng URI từ controller mapping**, không phải REST client, route validator hay authorization layer.
2. Với method trả `String` hoặc proxy khó tạo, ưu tiên `fromMethodName`; với kiểu tương thích proxy, có thể dùng `fromMethodCall(on(...))`.
3. Đặt tên `@PathVariable` và `@RequestParam` rõ, điền đầy đủ biến còn thiếu bằng `buildAndExpand`.
4. Khi cần class URL, dùng `fromController` nhưng hiểu rằng nhiều class mappings có thể gây mơ hồ.
5. Khi không có request hoặc cần trusted public origin, dùng `relativeTo` hay overload base URL — không tin user-supplied base.
6. Kiểm soát encoding path/query theo ngữ cảnh, ưu tiên template `encode()` trước expansion cho dữ liệu biến chứa reserved characters.
7. Không hardcode URL version ở nhiều chỗ; giữ contract API v1/v2 và test generated links sau refactor.
8. Với reverse proxy, xử lý forwarded headers an toàn và rõ ràng, tránh Host poisoning/context path lặp.
9. Khi dùng link trong HTML, dùng `th:href` và escaping; khi dùng Location, kiểm tra absolute URI và quyền của resource mới.
10. Test cả generated link và destination handler; kiểm tra path, query, port, context path, proxy và special characters.

## Tài liệu chính thức

- [Spring Framework 6.2 — URI Links và Links to Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html)
- [Spring Framework 6.2 — MvcUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.html)
- [Spring Framework 6.2 — MethodArgumentBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/MvcUriComponentsBuilder.MethodArgumentBuilder.html)
- [Spring Framework 6.2 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Spring Framework 6.2 — Servlet MVC Controller Mappings](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework 6.2 — ForwardedHeaderFilter và security considerations](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Boot 3.5 — Common Application Properties (`server.forward-headers-strategy`)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
