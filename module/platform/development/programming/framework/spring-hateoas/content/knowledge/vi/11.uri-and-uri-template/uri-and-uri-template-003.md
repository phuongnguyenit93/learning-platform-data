# URI tương đối

URI tương đối (relative URI reference) là một tham chiếu URI chưa chứa đầy đủ scheme và authority của đích. Client xác định URI đích bằng cách phân giải tham chiếu đó dựa trên một base URI đã biết. Trong REST API, URI tương đối cho phép server công bố link mà không phải lặp lại scheme và host trong mọi biểu diễn.

Spring HATEOAS hỗ trợ cả link có URI tuyệt đối và link có URI tương đối. Khi tạo link trực tiếp bằng `Link.of(...)`, ứng dụng có thể giữ href như `/orders/42`, `42` hoặc `?page=2`. Client đọc link sẽ phân giải href theo URI của biểu diễn chứa link và các quy tắc URI chuẩn. Nếu dùng `WebMvcLinkBuilder` như `linkTo(methodOn(...))`, URI thường được dựng từ mapping Spring MVC và thông tin request hiện tại; kết quả có thể là URI tuyệt đối.

Bài học này tập trung vào cách hiểu, tạo và sử dụng URI tương đối trong biểu diễn hypermedia. Bạn sẽ phân biệt URI tuyệt đối, root-relative và path-relative; hiểu vai trò của base URI; tạo link tương đối bằng Spring HATEOAS; và tránh các lỗi liên quan đến context path, query string, reverse proxy và kiểm thử.

Sau bài học, bạn có thể:

- Giải thích URI tương đối và cách phân giải nó theo base URI.
- Phân biệt absolute URI, root-relative reference, path-relative reference và query-relative reference.
- Dùng `Link.of(...)` để tạo link có href tương đối.
- Dùng `UriComponentsBuilder` để xây dựng URI tương đối an toàn.
- Hiểu sự khác nhau giữa link thủ công và link sinh từ controller mapping.
- Thiết kế link tương đối hoạt động đúng khi API được triển khai dưới context path hoặc domain khác.
- Kiểm thử href tương đối và kết quả phân giải URI.

## 1. URI tuyệt đối và URI tương đối

Một URI tuyệt đối chứa scheme; với HTTP(S), nó cũng có authority xác định host và có thể có port. Ví dụ:

~~~text
https://api.example.com/orders/42
~~~

URI này cho biết giao thức HTTPS, host `api.example.com` và đường dẫn `/orders/42`. Client có thể dùng trực tiếp URI đó để gửi request.

Một URI tương đối không chứa đầy đủ thông tin này:

~~~text
/orders/42
~~~

Để biết URI đích đầy đủ, client cần một base URI. Nếu base URI là `https://api.example.com/api/orders`, tham chiếu `/orders/42` được phân giải thành:

~~~text
https://api.example.com/orders/42
~~~

Lưu ý rằng dấu gạch chéo đầu tiên khiến tham chiếu bắt đầu từ root của authority. Nó không giữ phần context path `/api`. Đây là một trong những khác biệt quan trọng nhất khi thiết kế link cho ứng dụng được triển khai dưới context path.

### 1.1. URI reference và base URI

Trong thuật ngữ URI, giá trị được đặt trong thuộc tính href thường được xử lý như một URI reference. Nó có thể là URI tuyệt đối hoặc một tham chiếu tương đối. Việc phân giải tuân theo thuật toán chuẩn của URI, thường được thực hiện bằng cách kết hợp tham chiếu với base URI.

Ví dụ base URI:

~~~text
https://api.example.com/api/orders/42
~~~

Các tham chiếu khác nhau tạo ra đích khác nhau:

| Href trong link | Dạng tham chiếu | URI sau khi phân giải |
|---|---|---|
| `https://other.example/items/7` | URI tuyệt đối | `https://other.example/items/7` |
| `/orders/43` | Root-relative | `https://api.example.com/orders/43` |
| `43` | Path-relative | `https://api.example.com/api/orders/43` |
| `../customers/8` | Path-relative | `https://api.example.com/api/customers/8` |
| `?page=2` | Query-relative | `https://api.example.com/api/orders/42?page=2` |
| `#history` | Fragment-relative | `https://api.example.com/api/orders/42#history` |

Các ví dụ trên giả định base URI chính xác như đã nêu. Cùng một href có thể dẫn đến URI khác khi base URI thay đổi.

### 1.2. Base URI đến từ đâu?

Client cần biết URI cơ sở của biểu diễn trước khi phân giải href tương đối. Với một phản hồi HTTP, base URI thường được xác định từ URI dùng để lấy biểu diễn; định dạng hoặc cơ chế bao ngoài có thể quy định base URI khác. Client cần tuân theo quy tắc của giao thức và định dạng biểu diễn đang sử dụng.

Ví dụ client gửi request:

~~~http
GET https://api.example.com/api/orders/42 HTTP/1.1
Accept: application/hal+json
~~~

Nếu response chứa:

~~~json
{
  "_links": {
    "next": {
      "href": "43"
    }
  }
}
~~~

Client phân giải `43` dựa trên base URI của biểu diễn để thu được URI tiếp theo. Client không nên lấy URL của trang giao diện web đang hiển thị rồi dùng làm base URI cho API response, vì hai URI có thể thuộc những không gian đường dẫn khác nhau.

### 1.3. URI tương đối không phải URI template

Hai khái niệm này giải quyết hai vấn đề khác nhau:

- URI tương đối cần base URI để xác định đích.
- URI template chứa biến hoặc biểu thức cần được mở rộng trước khi hoặc trong lúc sử dụng.

Ví dụ:

~~~text
orders/42
/orders/{id}
~~~

`orders/42` là tham chiếu đường dẫn tương đối. `/orders/{id}` là mẫu URI có biến `id`; sau khi cung cấp giá trị cho biến, kết quả vẫn có thể là một URI tương đối.

Không nên coi dấu ngoặc nhọn trong URI template là cú pháp để phân giải base URI. Đây là hai bước riêng biệt: mở rộng template để thay biến, sau đó phân giải URI reference nếu kết quả là tương đối.

## 2. Các dạng URI tương đối thường gặp

Cần hiểu rõ vị trí của dấu gạch chéo đầu tiên và cách URI được phân giải.

### 2.1. Root-relative reference

Root-relative reference bắt đầu bằng dấu `/`:

~~~text
/orders/42
~~~

Nó giữ scheme và authority của base URI nhưng thay toàn bộ path từ root. Nếu base là:

~~~text
https://api.example.com/service/v1/orders
~~~

thì `/orders/42` được phân giải thành:

~~~text
https://api.example.com/orders/42
~~~

Dạng này dễ đọc và không phụ thuộc vào đường dẫn hiện tại của tài nguyên. Tuy nhiên, nó bỏ qua context path như `/service/v1`. Nếu ứng dụng được triển khai dưới context path, link root-relative cần bao gồm context path công khai hoặc được tạo theo cách phù hợp với cấu hình triển khai.

### 2.2. Path-relative reference

Path-relative reference không bắt đầu bằng dấu `/`:

~~~text
42
../customers/8
orders/42
~~~

URI được phân giải tương đối với thư mục của base URI. Ví dụ:

| Base URI | Href | Kết quả |
|---|---|---|
| `https://api.example.com/api/orders/42` | `43` | `https://api.example.com/api/orders/43` |
| `https://api.example.com/api/orders/42` | `../customers/8` | `https://api.example.com/api/customers/8` |
| `https://api.example.com/api/` | `orders/42` | `https://api.example.com/api/orders/42` |

Path-relative link có thể giữ context path khi base URI được chọn phù hợp. Nhưng nó cũng nhạy với dấu gạch chéo cuối và cấu trúc đường dẫn của base URI. Cần kiểm thử với đúng URI của representation thay vì suy đoán base là thư mục ứng dụng.

### 2.3. Query-relative reference

Một tham chiếu chỉ chứa query string có thể trỏ đến một biến thể khác của cùng path:

~~~text
?page=2&size=20
~~~

Với base URI:

~~~text
https://api.example.com/api/orders?status=OPEN&page=1
~~~

tham chiếu `?page=2&size=20` tạo URI:

~~~text
https://api.example.com/api/orders?page=2&size=20
~~~

Query trong tham chiếu thay thế query hiện tại. Nó không tự động hợp nhất query parameter cũ. Nếu cần giữ filter như `status=OPEN`, link mới phải chứa filter đó:

~~~text
?status=OPEN&page=2&size=20
~~~

Đối với phân trang, việc bảo toàn filter và sort là trách nhiệm của server khi tạo link next. Client nên theo href nguyên vẹn thay vì tự nối thêm query parameter.

### 2.4. Fragment-relative reference

Một tham chiếu bắt đầu bằng `#` xác định fragment:

~~~text
#history
~~~

Fragment thường được xử lý ở phía client và không được gửi như một phần của HTTP request đến server. Nó hữu ích cho điều hướng trong tài liệu hoặc một số ứng dụng phía trình duyệt, nhưng không phải lựa chọn phổ biến để điều hướng đến tài nguyên REST khác.

### 2.5. Network-path reference

Một tham chiếu bắt đầu bằng hai dấu gạch chéo:

~~~text
//cdn.example.com/assets/book.json
~~~

nó giữ scheme của base URI nhưng thay authority. Ví dụ, với base HTTPS, kết quả là:

~~~text
https://cdn.example.com/assets/book.json
~~~

Dạng này có thể hữu ích trong một số tình huống web, nhưng API nên dùng có chủ đích vì nó có thể đưa client sang host khác. Client cần áp dụng chính sách tin cậy và bảo mật cho host đích.

## 3. Phân giải URI tương đối bằng Java

Java cung cấp `java.net.URI` với phương thức `resolve(...)` để phân giải một URI reference theo base URI.

Ví dụ:

~~~java
URI base = URI.create(
    "https://api.example.com/api/orders/42"
);

URI target = base.resolve("43");

System.out.println(target);
// https://api.example.com/api/orders/43
~~~

Với root-relative reference:

~~~java
URI target = base.resolve("/orders/43");

// https://api.example.com/orders/43
~~~

Với tham chiếu đến thư mục cha:

~~~java
URI target = base.resolve("../customers/8");

// https://api.example.com/api/customers/8
~~~

Điều này cho thấy server có thể gửi href tương đối nhưng client cần biết base URI để chuyển thành URI đích đầy đủ.

### 3.1. Kiểm tra URI trước khi sử dụng

Khi xử lý link nhận từ API khác, client có thể kiểm tra URI sau khi phân giải:

~~~java
URI base = URI.create(responseUri);
URI target = base.resolve(link.getHref());

if (!"https".equalsIgnoreCase(target.getScheme())) {
    throw new IllegalArgumentException("Unsupported URI scheme");
}
~~~

Ví dụ trên chỉ kiểm tra scheme để minh họa. Ứng dụng thực tế có thể cần kiểm tra host được phép, port, scheme và các chính sách truy cập khác. Không nên giả định mọi link nhận được đều an toàn hoặc thuộc cùng API.

### 3.2. Chuẩn hóa và so sánh URI

Không nên so sánh hai URI bằng cách chỉ so sánh chuỗi trước khi xem xét chuẩn hóa. Các URI có thể khác cách viết nhưng biểu diễn cùng đích theo quy tắc URI. Tuy nhiên, không nên tùy tiện chuẩn hóa path hoặc giải mã ký tự vì có thể làm thay đổi ý nghĩa của URI.

Hãy dùng các API URI phù hợp và chỉ áp dụng canonicalization theo hợp đồng rõ ràng. Trong hầu hết client hypermedia, cách đơn giản và an toàn là theo href do server cung cấp thay vì phân tích và dựng lại đường dẫn.

## 4. Tạo link tương đối bằng Spring HATEOAS

Spring HATEOAS biểu diễn liên kết bằng lớp `Link`. Khi đã có href tương đối, có thể tạo link trực tiếp bằng `Link.of(...)`.

### 4.1. Tạo root-relative link

~~~java
Link self = Link.of("/orders/42").withSelfRel();

Link collection = Link.of("/orders")
    .withRel("orders");

Link customer = Link.of("/customers/8")
    .withRel("customer");
~~~

Các href được giữ ở dạng root-relative. Khi serialize HAL, server có thể trả về:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "orders": {
      "href": "/orders"
    },
    "customer": {
      "href": "/customers/8"
    }
  }
}
~~~

Client sẽ phân giải các href theo base URI của biểu diễn. Nếu API nằm dưới context path, cần bảo đảm root-relative href bao gồm đúng phần path công khai.

### 4.2. Tạo path-relative link

Có thể tạo link không có dấu gạch chéo đầu:

~~~java
Link sibling = Link.of("43").withRel("next");
~~~

Nếu biểu diễn hiện tại được lấy từ:

~~~text
https://api.example.com/api/orders/42
~~~

thì client phân giải href `43` thành:

~~~text
https://api.example.com/api/orders/43
~~~

Cách này hữu ích khi các tài nguyên thành viên nằm cùng một collection path. Tuy nhiên, nó phụ thuộc vào base URI của representation. Nếu URI hiện tại hoặc cách triển khai thay đổi, kết quả phân giải cũng có thể thay đổi.

### 4.3. Tạo query-relative link

Ví dụ link sang trang tiếp theo:

~~~java
Link next = Link.of("?status=OPEN&page=2&size=20")
    .withRel("next");
~~~

Đây là link tương đối chỉ chứa query. Nó thay thế query hiện tại khi client phân giải. Server phải giữ mọi filter và sort cần thiết trong href.

Nếu endpoint dùng query parameter phức tạp, tránh ghép chuỗi thủ công. Dùng builder để encode giá trị và tạo query nhất quán.

## 5. Xây URI tương đối với UriComponentsBuilder

Spring Framework cung cấp `UriComponentsBuilder` để xây dựng URI theo từng thành phần. Khi bắt đầu bằng `fromPath(...)`, kết quả có thể vẫn là URI tương đối vì chưa có scheme và host.

Ví dụ tạo href root-relative:

~~~java
String href = UriComponentsBuilder
    .fromPath("/orders/{id}")
    .queryParam("view", "summary")
    .encode()
    .buildAndExpand(orderId)
    .toUriString();

Link self = Link.of(href).withSelfRel();
~~~

Kết quả có dạng:

~~~text
/orders/42?view=summary
~~~

Có thể tạo query link mà không nối chuỗi:

~~~java
String nextHref = UriComponentsBuilder
    .fromPath("/orders")
    .queryParam("status", status)
    .queryParam("page", nextPage)
    .queryParam("size", pageSize)
    .queryParam("sort", "createdAt,desc")
    .encode()
    .build()
    .toUriString();

Link next = Link.of(nextHref).withRel("next");
~~~

Khi dùng `fromPath`, không có scheme hoặc host được thêm tự động. Đây là cách phù hợp khi hợp đồng yêu cầu một path reference. Nếu cần URI tuyệt đối, cần cung cấp scheme và authority hoặc dùng link builder dựa trên request.

Các import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.web.util.UriComponentsBuilder;
~~~

### 5.1. Encode path và query parameter

Không nên nối trực tiếp dữ liệu người dùng vào URI:

~~~java
// Tránh cách ghép chuỗi không kiểm soát
String href = "/orders?customer=" + customerName;
~~~

Nếu tên khách hàng có dấu cách, dấu &, dấu # hoặc ký tự đặc biệt, URI có thể bị phân tích sai. Hãy dùng builder:

~~~java
String href = UriComponentsBuilder
    .fromPath("/orders")
    .queryParam("customer", customerName)
    .encode()
    .build()
    .toUriString();
~~~

Builder giúp encode thành phần URI theo đúng vai trò của nó. Không encode toàn bộ URI sau khi đã ghép vì việc đó có thể encode cả dấu phân cách như `/`, `?` và `&`.

### 5.2. Xây dựng path-relative URI

Nếu hợp đồng cần path-relative href, dùng `fromPath` mà không có dấu gạch chéo đầu:

~~~java
String href = UriComponentsBuilder
    .fromPath("43")
    .queryParam("view", "summary")
    .encode()
    .build()
    .toUriString();

Link next = Link.of(href).withRel("next");
~~~

Kết quả:

~~~text
43?view=summary
~~~

Chỉ chọn dạng này khi base URI của representation được kiểm soát và quy tắc phân giải đã được kiểm thử. Root-relative link thường dễ đọc hơn, nhưng cần tính đến context path khi triển khai.

## 6. Link tương đối và link sinh từ controller mapping

Spring HATEOAS có thể tạo link dựa trên mapping Spring MVC:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Các import chính cho link builder:

~~~java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Cách này giúp URI bám theo mapping của controller, tránh lặp lại đường dẫn. Trong request MVC, link builder thường dựa vào thông tin request hiện tại để tạo URI đầy đủ, bao gồm scheme, host và context path mà ứng dụng nhìn thấy. Kết quả cụ thể phụ thuộc vào request và cấu hình proxy/header của ứng dụng.

Ngược lại:

~~~java
Link self = Link.of("/orders/" + orderId).withSelfRel();
~~~

tạo một root-relative href theo giá trị được cung cấp. Nó không tự thêm scheme, host hoặc context path.

| Cách tạo | Đặc điểm | Khi phù hợp |
|---|---|---|
| `Link.of("/orders/42")` | Giữ href root-relative | Hợp đồng muốn dùng path từ root |
| `Link.of("42")` | Giữ href path-relative | Đích nằm tương đối với URI hiện tại |
| `UriComponentsBuilder.fromPath(...)` | Xây path/query mà không bắt buộc có host | Tạo href tương đối có query |
| `linkTo(methodOn(...))` | Sinh URI từ mapping và request MVC | Muốn link bám theo controller mapping |

Không nên chuyển mọi link sang tương đối chỉ vì muốn triển khai được trên nhiều domain. Hãy quyết định dạng URI dựa trên hợp đồng client, context path, proxy và khả năng xác định base URI của client.

## 7. Context path và reverse proxy

Một ứng dụng có thể được triển khai ở nhiều môi trường:

~~~text
Local:       http://localhost:8080/orders
Staging:     https://staging.example.com/api/orders
Production:  https://api.example.com/v2/orders
~~~

Nếu link được hard-code thành:

~~~text
https://staging.example.com/api/orders/42
~~~

thì link có thể sai khi triển khai production. URI tương đối có thể giúp tránh gắn cứng domain và scheme.

Tuy nhiên, root-relative link:

~~~text
/orders/42
~~~

vẫn không tự giữ `/api` hoặc `/v2`. Nếu API được công bố dưới context path, href phải phản ánh path công khai hoặc được phân giải theo base URI có cấu trúc phù hợp.

### 7.1. Chọn root-relative hay path-relative?

Root-relative phù hợp khi API có một root path ổn định và client có thể giữ context path từ base URI hoặc href được tạo có đầy đủ context path.

Path-relative có thể giữ đường dẫn triển khai khi link được phân giải từ một URI hiện tại nằm trong đúng collection path. Nhưng nó nhạy với URI của tài nguyên hiện tại, dấu gạch chéo cuối và cách client chọn base URI.

Một cách chọn thực tế:

- Dùng URI tuyệt đối nếu client cần một đích độc lập với base URI hoặc tài nguyên ở host khác.
- Dùng root-relative nếu muốn cố định đường dẫn từ root của host hiện tại.
- Dùng path-relative khi quan hệ đường dẫn giữa tài nguyên nguồn và đích là một phần ổn định của hợp đồng.
- Dùng query-relative khi chuyển đến một biến thể khác của cùng path và server đã giữ đủ filter/sort.

### 7.2. Forwarded headers khi tạo URI tuyệt đối

Khi ứng dụng chạy sau reverse proxy, request nội bộ có thể mang host hoặc scheme khác với URL công khai. Nếu `linkTo(...)` tạo URI tuyệt đối dựa trên request mà ứng dụng không xử lý forwarded headers đúng cách, link có thể trỏ đến địa chỉ nội bộ.

Nếu muốn link tuyệt đối, cấu hình ứng dụng và proxy để xử lý các header như `Forwarded` hoặc `X-Forwarded-Host`, `X-Forwarded-Proto` và prefix tương ứng theo cách đáng tin cậy. Chỉ tin các header này từ proxy được kiểm soát. Nếu dùng relative href, vẫn phải kiểm tra context path và base URI mà client sẽ sử dụng.

### 7.3. Tránh tạo link ra ngoài host ngoài ý muốn

Một root-relative link như `/orders/42` giữ authority của base URI. Một URI tuyệt đối hoặc network-path reference có thể chuyển client sang host khác.

Khi client tự động theo link, cần có chính sách phù hợp về host được phép, scheme, xác thực và chuyển tiếp credential. Không nên gửi token hoặc cookie nhạy cảm đến host khác chỉ vì một link xuất hiện trong response.

## 8. Tích hợp link tương đối vào EntityModel

Giả sử controller trả về biểu diễn đơn hàng:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Có thể tạo `EntityModel` với link tương đối:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    Order order = service.getRequired(id);

    OrderRepresentation content = new OrderRepresentation(
        order.getId(),
        order.getStatus().name(),
        order.getTotal()
    );

    Link self = Link.of(
        UriComponentsBuilder.fromPath("/orders/{id}")
            .encode()
            .buildAndExpand(id)
            .toUriString()
    ).withSelfRel();

    Link collection = Link.of("/orders")
        .withRel("orders");

    return EntityModel.of(content, self, collection);
}
~~~

Các link này giữ dạng root-relative. Nếu API được triển khai dưới context path `/api`, hãy bảo đảm đường dẫn công khai có context path, ví dụ `/api/orders/{id}`, hoặc chọn một chiến lược relative path dựa trên base URI được kiểm soát.

Các import liên quan trong ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.util.UriComponentsBuilder;
~~~

Trong ứng dụng thực tế, có thể chuyển phần tạo link vào assembler để mọi endpoint tạo biểu diễn đơn hàng theo cùng quy tắc.

### 8.1. Collection với link next tương đối

Một collection phân trang có thể phát link next dạng query-relative:

~~~java
Link next = Link.of(
    UriComponentsBuilder.fromPath("/orders")
        .queryParam("status", status)
        .queryParam("page", nextPage)
        .queryParam("size", pageSize)
        .encode()
        .build()
        .toUriString()
).withRel(IanaLinkRelations.NEXT);
~~~

Import relation chuẩn:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
~~~

Nếu dùng `PagedResourcesAssembler`, Spring Data Web thường tạo link phân trang từ request hiện tại. Khi tự tạo link, cần giữ filter, sort và các tham số có ý nghĩa trong cùng collection.

### 8.2. Không phụ thuộc href là tuyệt đối

Một client hypermedia đúng nên xử lý cả link tuyệt đối và link tương đối. Client không nên giả định href luôn bắt đầu bằng `https://`, cũng không nên nối base URI bằng chuỗi.

Ví dụ trong Java:

~~~java
URI base = URI.create(responseUri);
URI target = base.resolve(link.getHref());
~~~

Cách này tuân theo quy tắc phân giải URI. Việc kiểm tra scheme/host sau khi resolve vẫn phụ thuộc vào chính sách bảo mật của client.

## 9. Kiểm thử URI tương đối

Kiểm thử nên xác nhận cả chuỗi href được serialize và URI đích sau khi phân giải theo base URI phù hợp.

### 9.1. Kiểm thử giá trị href trong HAL

Ví dụ endpoint trả link root-relative:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService service;

    @Test
    void returnsRootRelativeSelfLink() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(order(id));

        mvc.perform(get("/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value("/orders/" + id));
    }
}
~~~

Fixture `order(id)` là dữ liệu kiểm thử của ứng dụng. Ví dụ giả định controller tạo link bằng `Link.of(...)`; nếu dùng `linkTo(methodOn(...))`, href có thể là URI tuyệt đối dựa trên request.

Các import thường dùng:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

### 9.2. Kiểm thử phân giải URI

Có thể kiểm tra riêng cách URI tương đối được phân giải:

~~~java
@Test
void resolvesPathRelativeLinkAgainstRepresentationUri() {
    URI base = URI.create(
        "https://api.example.com/api/orders/42"
    );

    URI target = base.resolve("43");

    assertEquals(
        URI.create("https://api.example.com/api/orders/43"),
        target
    );
}
~~~

Với root-relative href:

~~~java
URI target = base.resolve("/orders/43");

assertEquals(
    URI.create("https://api.example.com/orders/43"),
    target
);
~~~

Kiểm thử này giúp phát hiện lỗi mất context path do dấu gạch chéo đầu tiên.

Các import cho ví dụ phân giải URI:

~~~java
import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertEquals;
~~~

### 9.3. Kiểm thử context path và proxy

Nếu ứng dụng triển khai dưới context path hoặc reverse proxy, nên có kiểm thử tích hợp với cấu hình tương ứng. Xác nhận:

- Href tương đối có giữ đúng phần path công khai không.
- Link tuyệt đối có scheme, host và port công khai chính xác không.
- Query parameter filter/sort được giữ khi theo link next.
- Client phân giải href theo URI của response.
- Link đến host khác không nhận credential ngoài chính sách cho phép.

MockMvc có thể kiểm tra serialization trong ứng dụng MVC, nhưng không thay thế kiểm thử proxy hoặc gateway ở môi trường triển khai.

## 10. Lỗi thường gặp khi sử dụng URI tương đối

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Nhầm `/orders/42` với `orders/42` | URI được phân giải đến path khác | Xác định rõ root-relative hay path-relative |
| Quên base URI | Client không biết đích đầy đủ | Resolve href theo URI của representation |
| Dùng root-relative khi API có context path | Link bỏ mất `/api` hoặc `/v2` | Đưa context path vào href hoặc chọn path-relative phù hợp |
| Ghép URI bằng chuỗi | Query và ký tự đặc biệt bị lỗi | Dùng UriComponentsBuilder |
| Dùng query-relative nhưng bỏ filter | Client chuyển sang tập kết quả khác | Giữ filter và sort trong href |
| Coi URI template là URI tương đối | Mở rộng biến sai thứ tự hoặc sai bước | Tách bước expand template và resolve URI |
| Giả định linkTo luôn tạo root-relative | Href có thể là absolute URI | Kiểm tra hành vi dựa trên request và cấu hình |
| Tin forwarded headers từ mọi nguồn | Có thể tạo link tuyệt đối với host giả mạo | Chỉ tin header từ proxy được kiểm soát |
| Coi relative link luôn cùng host sau resolve | Network-path hoặc absolute reference có thể đổi host | Kiểm tra scheme và authority nếu cần |

## 11. Quy trình thiết kế link tương đối

Khi quyết định dùng URI tương đối cho một link, hãy thực hiện theo trình tự:

1. Xác định URI của biểu diễn chứa link và base URI mà client sẽ dùng.
2. Chọn loại tham chiếu: root-relative, path-relative, query-relative hoặc URI tuyệt đối.
3. Kiểm tra kết quả resolve trong trường hợp có context path và trailing slash.
4. Dùng `Link.of(...)` để giữ href tương đối hoặc `UriComponentsBuilder.fromPath(...)` để xây dựng path/query.
5. Dùng `linkTo(methodOn(...))` khi muốn tạo link từ mapping Spring MVC và request hiện tại.
6. Bảo toàn filter, sort và các tham số cần thiết trong link phân trang.
7. Kiểm tra URI sau khi resolve và áp dụng chính sách host/scheme phù hợp.
8. Kiểm thử serialization HAL, base URI, context path và reverse proxy.

## 12. Kết luận

URI tương đối cho phép biểu diễn hypermedia tham chiếu tài nguyên mà không phải lặp lại scheme và authority. Tuy nhiên, href chỉ xác định đích khi được phân giải theo base URI. Root-relative reference bắt đầu từ root của host, path-relative reference phụ thuộc đường dẫn hiện tại, còn query-relative reference thay query của cùng path.

Trong Spring HATEOAS, `Link.of(...)` có thể giữ href tương đối; `UriComponentsBuilder.fromPath(...)` giúp tạo path và query có encode; `linkTo(methodOn(...))` tạo link theo mapping Spring MVC và ngữ cảnh request. Khi chọn đúng dạng URI, kiểm tra context path và giữ quy tắc phân giải rõ ràng, API có thể công bố link linh hoạt qua nhiều môi trường triển khai mà client vẫn điều hướng đúng.

## Tài liệu tham khảo

- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): URI reference, base URI và thuật toán phân giải.
- [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/): tạo link, link builder và tích hợp Spring MVC.
- [Spring Framework — UriComponentsBuilder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): xây dựng và encode URI components.
- [Java URI API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): `resolve` và xử lý URI reference.

