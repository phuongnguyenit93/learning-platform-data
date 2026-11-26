# URI tuyệt đối

Một **URI tuyệt đối** (*absolute URI*) là URI có scheme xác định cách định danh hoặc truy cập tài nguyên, ví dụ `https://api.example.test/orders/42`. Trong REST API, URI tuyệt đối thường được dùng khi server công bố liên kết hypermedia cần hoạt động độc lập với địa chỉ trang hoặc tài nguyên mà client đang đứng.

Spring HATEOAS có thể tạo liên kết từ mapping của controller hoặc từ một URI được xây dựng rõ ràng. Hiểu cấu trúc URI tuyệt đối giúp ứng dụng tạo link đúng host, scheme, port, path và query; đồng thời tránh các lỗi thường gặp khi chạy sau reverse proxy, gateway hoặc trong nhiều môi trường triển khai.

## 1. URI tuyệt đối là gì?

URI (*Uniform Resource Identifier*) là chuỗi định danh một tài nguyên. Theo cú pháp URI, một URI tuyệt đối bắt đầu bằng một scheme và dấu hai chấm. Với HTTP API, dạng thường gặp là:

```text
https://api.example.test:8443/v1/orders/42?view=summary#details
```

URI này có thể được phân tích thành các thành phần:

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Chỉ định cơ chế truy cập; API web thường dùng `http` hoặc `https` |
| Authority | `api.example.test:8443` | Xác định máy chủ và cổng |
| Host | `api.example.test` | Tên máy chủ đích |
| Port | `8443` | Cổng kết nối; có thể được lược bỏ khi dùng cổng mặc định |
| Path | `/v1/orders/42` | Đường dẫn định danh tài nguyên trên máy chủ |
| Query | `view=summary` | Tham số bổ sung cho việc chọn hoặc lọc representation |
| Fragment | `details` | Phần định danh vị trí hoặc thành phần ở phía client |

Trong URI HTTP, authority thường chứa host và có thể có port. Cú pháp tổng quát của URI cho phép nhiều dạng khác nhau; không phải mọi URI tuyệt đối đều là HTTP URL. Ví dụ `mailto:team@example.test` và `urn:isbn:...` cũng là URI tuyệt đối nhưng không có authority theo dạng host và port.

Với REST API, ta thường cần một URI tuyệt đối dạng HTTP(S), có scheme và host hợp lệ để client có thể gửi request đến máy chủ.

## 2. Phân biệt URI tuyệt đối và URI tương đối

URI tuyệt đối có scheme, còn URI tương đối được diễn giải dựa trên một URI cơ sở (*base URI*). Ví dụ:

| Dạng | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Tuyệt đối | `https://api.example.test/orders/42` | Có scheme và xác định máy chủ |
| Tương đối theo path | `/orders/42` | Cần biết origin để xác định địa chỉ đầy đủ |
| Tương đối theo thư mục | `orders/42` | Phụ thuộc cả path của URI cơ sở |
| Chỉ query | `?page=2` | Giữ path cơ sở, thay query |
| Chỉ fragment | `#details` | Tham chiếu phần trong tài nguyên hiện tại |

Trong response hypermedia, link tuyệt đối hữu ích khi client ở một origin khác, lưu link để sử dụng về sau hoặc cần mở tài nguyên mà không phải tự suy luận host. Link tương đối cũng hợp lệ trong nhiều hợp đồng web và có thể thuận tiện khi ứng dụng chạy qua nhiều domain hoặc prefix. Việc chọn dạng nào cần nhất quán với cách client phân giải URI và cách API được triển khai.

Ví dụ, nếu response có link tương đối `/orders/42`, client cần một URI cơ sở như `https://api.example.test` để tạo địa chỉ đầy đủ. Nếu response có link tuyệt đối `https://api.example.test/orders/42`, host và scheme đã được chỉ rõ.

## 3. URI khác URL như thế nào?

URI là khái niệm định danh tổng quát. URL (*Uniform Resource Locator*) là dạng URI cung cấp vị trí hoặc cách truy cập tài nguyên. Trong phát triển web, nhiều người dùng hai từ này thay thế nhau vì URI HTTP thường cũng là URL.

Khi làm việc với Spring HATEOAS, `Link` chứa một `href` có giá trị là URI. Giá trị đó có thể là URI tuyệt đối hoặc tương đối. Vì vậy, không nên mặc định mọi link do API trả về đều là URI tuyệt đối; hãy kiểm tra hợp đồng và response thực tế.

Một URI tuyệt đối không tự bảo đảm tài nguyên tồn tại hoặc người gọi có quyền truy cập. Nó chỉ cung cấp định danh đầy đủ theo cú pháp URI. Server vẫn phải xử lý xác thực, phân quyền, định tuyến và phản hồi HTTP như bình thường.

## 4. Cấu trúc và cách diễn giải URI HTTP(S)

Một URI HTTP(S) thường có dạng:

```text
scheme://authority/path?query#fragment
```

Trong đó:

- `scheme` thường là `http` hoặc `https`.
- `authority` có thể gồm user information, host và port. Không nên đưa username, password hoặc token vào URI.
- `path` thường chứa các segment phân cấp, ví dụ `/v1/orders/42`.
- `query` chứa các cặp tham số, ví dụ `?status=PENDING&page=0`.
- `fragment` được xử lý phía client và không được gửi trong HTTP request đến server.

Ví dụ:

```text
https://api.example.test/v1/orders/42?status=PENDING&page=0
```

Client kết nối qua HTTPS đến host `api.example.test`, truy cập path `/v1/orders/42` và gửi query gồm `status=PENDING` cùng `page=0`. Fragment nếu có sẽ không tham gia vào request HTTP như path hoặc query.

## 5. Tạo URI tuyệt đối bằng Java

Java cung cấp `java.net.URI` để biểu diễn, phân tích và kiểm tra URI. Có thể tạo URI từ chuỗi:

```java
import java.net.URI;

URI orderUri = URI.create(
        "https://api.example.test/v1/orders/42?view=summary");

System.out.println(orderUri.isAbsolute()); // true
System.out.println(orderUri.getScheme()); // https
System.out.println(orderUri.getHost());   // api.example.test
System.out.println(orderUri.getPath());   // /v1/orders/42
System.out.println(orderUri.getQuery());  // view=summary
```

`isAbsolute()` kiểm tra URI có scheme hay không. Nếu cần xác nhận một địa chỉ HTTP(S) dùng được cho API, chỉ kiểm tra `isAbsolute()` là chưa đủ: cần kiểm tra scheme được chấp nhận và host có giá trị.

Một hàm kiểm tra đơn giản có thể như sau:

```java
import java.net.URI;
import java.util.Locale;

static URI requireAbsoluteHttpUri(String value) {
    URI uri = URI.create(value);
    String scheme = uri.getScheme();

    boolean httpScheme = scheme != null
            && (scheme.toLowerCase(Locale.ROOT).equals("http")
                || scheme.toLowerCase(Locale.ROOT).equals("https"));

    if (!httpScheme || uri.getHost() == null) {
        throw new IllegalArgumentException("Expected an absolute HTTP(S) URI");
    }

    return uri;
}
```

Hàm này kiểm tra dạng cơ bản của URI API. Ứng dụng thực tế có thể cần thêm chính sách về HTTPS bắt buộc, port, domain được phép hoặc địa chỉ nội bộ. Không nên dùng một phép kiểm tra cú pháp làm cơ chế bảo vệ khỏi SSRF hay truy cập host không đáng tin cậy; các kiểm soát đó cần được thiết kế riêng theo ngữ cảnh sử dụng URI.

## 6. Xây URI có tham số bằng UriComponentsBuilder

Trong Spring, `UriComponentsBuilder` giúp xây dựng URI theo từng thành phần. Cách này an toàn và dễ bảo trì hơn việc nối chuỗi, đặc biệt khi path segment hoặc query parameter chứa ký tự cần encode.

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("v1", "orders", "{id}")
        .queryParam("view", "{view}")
        .encode()
        .buildAndExpand(orderId, "full")
        .toUri();
```

Nếu `orderId` là `42`, URI kết quả có dạng:

```text
https://api.example.test/v1/orders/42?view=full
```

Các phương thức có vai trò khác nhau:

- `fromUriString(...)` thiết lập URI cơ sở.
- `pathSegment(...)` thêm từng segment của path; builder xử lý ranh giới segment.
- `queryParam(...)` thêm tham số query.
- `encode()` yêu cầu encode các giá trị theo quy tắc URI.
- `buildAndExpand(...)` thay các biến URI bằng giá trị thực.
- `toUri()` chuyển kết quả thành `java.net.URI`.

Nên encode theo từng thành phần thay vì encode toàn bộ chuỗi URI. Các ký tự như `/`, `?`, `&`, `#` có ý nghĩa cấu trúc; nếu dữ liệu đầu vào chứa chúng, builder cần đặt chúng vào đúng path segment hoặc query value và encode phù hợp.

## 7. Công bố URI tuyệt đối trong Spring HATEOAS

Spring HATEOAS dùng `Link` để biểu diễn quan hệ giữa tài nguyên. Có thể tạo link từ một URI đã có:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

Link self = Link.of(
        "https://api.example.test/v1/orders/42")
        .withSelfRel();

EntityModel<OrderRepresentation> model = EntityModel.of(
        orderRepresentation,
        self);
```

`Link.of(...)` nhận URI dưới dạng chuỗi và `withSelfRel()` gắn relation `self`. Trong ứng dụng thực tế, URI thường được tạo từ mapping controller hoặc `UriComponentsBuilder` thay vì viết cố định như ví dụ.

Với Spring MVC, `WebMvcLinkBuilder` tạo link dựa trên mapping của controller:

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    return EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel());
}
```

Khi được gọi trong ngữ cảnh request Spring MVC, `linkTo(methodOn(...))` có thể dùng thông tin request hiện tại để tạo link với scheme, host, port và context path phù hợp. Điều này giúp link phản ánh địa chỉ mà ứng dụng đang được truy cập, bao gồm mapping của controller.

Các link được tạo theo request context cần được kiểm tra khi ứng dụng chạy sau reverse proxy hoặc API gateway. Nếu proxy kết thúc TLS hoặc thay đổi host/prefix bên ngoài, server nội bộ có thể nhìn thấy scheme, host hoặc port khác với địa chỉ công khai. Hãy cấu hình xử lý forwarded headers chỉ từ proxy đáng tin cậy để Spring nhận diện đúng địa chỉ bên ngoài. Nếu không có request context, chẳng hạn tạo link trong tác vụ nền, hãy dùng base URI công khai lấy từ cấu hình ứng dụng.

## 8. URI tuyệt đối và địa chỉ triển khai

Không nên rải domain cố định như `https://api.example.test` trong nhiều assembler. Dev, staging và production có thể dùng host khác nhau; một API cũng có thể được đặt sau gateway với prefix riêng.

Có thể cấu hình base URI theo môi trường:

```properties
api.public-base-uri=https://api.example.test
```

Sau đó inject giá trị cấu hình vào thành phần tạo link và dùng `UriComponentsBuilder` để tạo URI. Ví dụ:

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;

URI orderUri = UriComponentsBuilder
        .fromUriString(publicBaseUri)
        .pathSegment("v1", "orders", "{id}")
        .encode()
        .buildAndExpand(order.getId())
        .toUri();
```

Trong ví dụ, `publicBaseUri` đến từ cấu hình ứng dụng. Việc tách base URI giúp triển khai cùng một mã nguồn ở nhiều môi trường mà không phải sửa assembler. Với link phụ thuộc vào request hiện tại, ưu tiên cơ chế tạo link từ controller mapping và cấu hình forwarded headers phù hợp.

Không lấy host từ một header tùy ý do client gửi lên để tạo link tuyệt đối. Nếu ứng dụng tin cậy header `Host` hoặc `Forwarded` mà không giới hạn nguồn gửi, client có thể tác động đến URI server phát ra. Chỉ chấp nhận forwarded headers từ reverse proxy được quản lý và cấu hình đúng chuỗi proxy.

## 9. URI tuyệt đối và URI template

URI tuyệt đối là một địa chỉ cụ thể có scheme, ví dụ `https://api.example.test/orders/42`. URI template chứa biến hoặc biểu thức cần được thay thế, ví dụ:

```text
https://api.example.test/orders/{id}
```

Template giúp mô tả một mẫu địa chỉ có thể tạo ra nhiều URI cụ thể. Khi cần gửi request đến một resource, client phải có giá trị cho biến và mở rộng template theo quy tắc tương ứng. Spring HATEOAS có hỗ trợ link template cho các trường hợp API muốn công bố tham số chưa được xác định, chẳng hạn biểu thức query cho tìm kiếm. Không nên nhầm một template chưa mở rộng với URI tuyệt đối cụ thể đã sẵn sàng để gọi.

Ví dụ, URI template `https://api.example.test/orders/{id}` sau khi thay `id` bằng `42` trở thành URI tuyệt đối `https://api.example.test/orders/42`.

## 10. Encoding và chuẩn hóa URI

URI chỉ cho phép một tập ký tự nhất định ở dạng trực tiếp. Các ký tự ngoài tập cho phép hoặc ký tự có ý nghĩa cấu trúc trong một thành phần cần được percent-encode. Ví dụ, khoảng trắng trong query value thường được encode thành `%20`; ký tự `&` trong query có ý nghĩa phân tách tham số nên cần được encode nếu nó là một phần của giá trị.

Một số nguyên tắc thực hành:

- Dùng `pathSegment(...)` để thêm từng segment thay vì nối dữ liệu vào path bằng chuỗi.
- Dùng `queryParam(...)` để thêm query parameter và để builder encode giá trị.
- Không encode toàn bộ URI sau khi đã tạo vì có thể biến dấu phân cách cấu trúc thành dữ liệu.
- Không tự decode rồi encode nhiều lần; điều đó có thể tạo double encoding như `%252F` thay vì `%2F`.
- Dùng `URI.normalize()` nếu cần loại bỏ các segment tương đối `.` hoặc `..` theo quy tắc URI, nhưng không xem thao tác này là kiểm tra quyền truy cập.

Ví dụ, nếu mã đơn hàng có ký tự đặc biệt, hãy truyền nó như một path variable hoặc path segment để builder encode đúng vị trí. Tránh tự ghép `"/orders/" + id` khi `id` có thể chứa ký tự phân cách.

## 11. Kiểm thử URI tuyệt đối và link HATEOAS

Kiểm thử nên xác nhận URI được tạo có scheme và host đúng, path/query được encode đúng, và link được công bố trong response có quan hệ phù hợp. Với Java, có thể kiểm tra trực tiếp `URI`:

```java
URI uri = buildOrderUri("42");

assertThat(uri.isAbsolute()).isTrue();
assertThat(uri.getScheme()).isEqualTo("https");
assertThat(uri.getHost()).isEqualTo("api.example.test");
assertThat(uri.getPath()).isEqualTo("/v1/orders/42");
```

Trong kiểm thử controller với `MockMvc`, hãy xác nhận link `self` được serialize đúng:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value("https://api.example.test/orders/42"));
```

Giá trị mong đợi phụ thuộc host, context path và cấu hình test. Nếu ứng dụng tạo link từ request context, hãy thiết lập host/proxy headers trong test theo cách triển khai thực tế. Ngoài ra, nên có kiểm thử khi ứng dụng đặt dưới context path hoặc chạy sau gateway để phát hiện link sai origin hoặc thiếu prefix.

## 12. Lỗi thường gặp

**Nghĩ rằng `isAbsolute()` bảo đảm URI là HTTP URL hợp lệ:** URI như `mailto:team@example.test` cũng tuyệt đối. Với REST API, cần kiểm tra scheme HTTP(S) và host theo chính sách.

**Hard-code host trong assembler:** domain có thể thay đổi giữa môi trường. Hãy dùng request context hoặc base URI từ cấu hình.

**Tạo link sai khi chạy sau proxy:** server có thể nhìn thấy host nội bộ hoặc scheme HTTP dù bên ngoài là HTTPS. Cấu hình forwarded headers từ proxy đáng tin cậy và kiểm thử URI được sinh ra.

**Nối chuỗi để tạo path và query:** dữ liệu có ký tự đặc biệt có thể làm sai cấu trúc URI. Dùng `UriComponentsBuilder` và encode theo thành phần.

**Nhầm fragment với query:** fragment không được gửi trong HTTP request đến server. Dùng query cho tham số API cần server xử lý.

**Nhầm URI template với URI hoàn chỉnh:** template còn biến cần mở rộng trước khi gọi như một địa chỉ cụ thể, trừ khi API cố ý công bố link template để client điền tham số.

## 13. Checklist tạo URI tuyệt đối

- URI có scheme và host hợp lệ khi hợp đồng yêu cầu HTTP(S) tuyệt đối.
- Scheme phù hợp với môi trường, ưu tiên HTTPS cho API công khai.
- Authority không chứa thông tin xác thực nhạy cảm.
- Path segment và query parameter được xây dựng bằng API phù hợp, không nối chuỗi tùy tiện.
- Giá trị động được encode đúng thành phần và không bị double encoding.
- Base URI lấy từ request context đáng tin cậy hoặc cấu hình môi trường.
- Forwarded headers chỉ được tin cậy khi đến từ proxy được quản lý.
- Link trong `RepresentationModel` hoặc `EntityModel` có relation đúng và `href` có thể phân giải.
- Kiểm thử host, scheme, context path, query và trường hợp chạy sau gateway.

URI tuyệt đối cung cấp địa chỉ đầy đủ cho tài nguyên, còn Spring HATEOAS giúp công bố địa chỉ đó dưới dạng liên kết có ý nghĩa. Khi xây URI theo từng thành phần, chọn đúng nguồn base URI và kiểm thử trong môi trường triển khai thực tế, API có thể phát ra các hypermedia link đáng tin cậy cho client.
