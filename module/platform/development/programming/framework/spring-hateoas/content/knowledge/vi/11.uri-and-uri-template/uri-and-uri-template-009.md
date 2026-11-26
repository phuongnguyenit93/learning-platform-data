# Mở rộng template

Một REST API thường cung cấp các liên kết có tham số thay đổi theo yêu cầu. Ví dụ, client có thể tìm đơn hàng theo trạng thái, chọn trang và kích thước trang, hoặc mở chi tiết một đơn hàng theo mã. Nếu server chỉ trả về một URI cố định cho từng trường hợp, client phải tự ghép query parameter hoặc thay thế đoạn đường dẫn. Cách làm đó khiến client phụ thuộc vào cấu trúc URI và dễ tạo URL sai.

URI Template cho phép biểu diễn một URI có các biến chưa được gán giá trị. Server có thể công bố template trong liên kết hypermedia; client hoặc ứng dụng có thể mở rộng template bằng các giá trị cụ thể để tạo URI hoàn chỉnh. Spring HATEOAS hỗ trợ liên kết dạng template thông qua Link và cung cấp cách mở rộng bằng các giá trị biến.

Bài học này tập trung vào cách đọc cú pháp URI Template, cách tạo templated link trong Spring HATEOAS, cách gọi Link.expand, cách xử lý biến path và query, cũng như cách kiểm thử kết quả mở rộng.

## 1. URI và URI Template

URI (Uniform Resource Identifier) là định danh dùng để tham chiếu một tài nguyên. Một URI cụ thể có thể là:

~~~text
https://api.example.com/api/orders/42
~~~

URI trên trỏ đến đơn hàng có mã 42. Khi cần tham chiếu đến nhiều đơn hàng khác nhau, phần mã có thể được thay bằng một biến:

~~~text
https://api.example.com/api/orders/{id}
~~~

Đây là URI Template. Biến id chưa có giá trị cụ thể. Khi mở rộng với id = 42, template tạo ra URI:

~~~text
https://api.example.com/api/orders/42
~~~

Template cũng có thể chứa biến query:

~~~text
https://api.example.com/api/orders{?status,page,size}
~~~

Khi được mở rộng với status = PENDING, page = 0 và size = 20, URI kết quả có thể là:

~~~text
https://api.example.com/api/orders?status=PENDING&page=0&size=20
~~~

URI Template được mô tả trong RFC 6570. Nó định nghĩa cú pháp biểu thức để chèn biến vào các phần khác nhau của URI, chẳng hạn path, query hoặc fragment. Template không phải một URI hoàn chỉnh để gửi nguyên trạng trong mọi ngữ cảnh; ứng dụng cần mở rộng các biến cần thiết trước khi gọi endpoint.

## 2. Vì sao API công bố URI Template?

Giả sử API có endpoint tìm kiếm đơn hàng:

~~~http
GET /api/orders?status=PENDING&page=0&size=20
~~~

Nếu client phải tự tạo query string, client cần biết tên tham số, cách mã hóa giá trị và quy tắc phân trang. Khi server đổi tên tham số hoặc thêm một tham số lọc, nhiều client có thể phải cập nhật.

Server có thể công bố template:

~~~text
/api/orders{?status,page,size,sort}
~~~

Client đọc template để biết các biến có thể cung cấp. Server vẫn kiểm soát endpoint và ý nghĩa tham số; client chỉ điền giá trị vào các vị trí đã công bố.

URI Template hữu ích khi:

- Một liên kết có thể dẫn đến nhiều URI tùy giá trị biến.
- API hỗ trợ lọc, phân trang hoặc sắp xếp bằng query parameter.
- Client cần tạo URI tài nguyên con dựa trên một mã định danh.
- Server muốn công bố cách tham chiếu tài nguyên mà không buộc client ghép chuỗi URL.

Template giúp giảm phụ thuộc vào cấu trúc URI, nhưng không thay thế tài liệu ngữ nghĩa. Client vẫn cần hiểu ý nghĩa của rel và các biến mà template công bố.

## 3. Cú pháp biểu thức URI Template thường gặp

URI Template dùng dấu ngoặc nhọn để biểu diễn biến và toán tử để xác định cách mở rộng. Một số dạng thường gặp:

| Cú pháp | Ý nghĩa | Ví dụ sau khi mở rộng |
| --- | --- | --- |
| {id} | Chèn biến vào vị trí hiện tại | /orders/42 |
| {/id} | Thêm dấu slash trước biến | /orders/42 |
| {?page,size} | Bắt đầu query string với các biến | /orders?page=0&size=20 |
| {&sort,status} | Bổ sung biến vào query string hiện có | /orders?page=0&sort=createdAt |
| {#section} | Thêm fragment | /orders#summary |
| {+path} | Mở rộng biến theo quy tắc cho phép giữ reserved character | /files/a/b |

Trong API REST, hai dạng được sử dụng thường xuyên là biến path và biến query:

~~~text
/api/orders/{id}
/api/orders{?status,page,size,sort}
~~~

Biến path thường đại diện cho định danh của một tài nguyên. Biến query thường dùng để lọc, sắp xếp hoặc phân trang một collection.

Toán tử ảnh hưởng đến cách giá trị được mã hóa. Với biểu thức query thông thường, các ký tự đặc biệt trong giá trị được percent-encode để không bị hiểu nhầm là dấu phân cách cấu trúc URI. Vì vậy, ứng dụng nên dùng thư viện mở rộng template thay vì nối chuỗi thủ công.

## 4. Tạo templated Link bằng Spring HATEOAS

Trong Spring HATEOAS, Link biểu diễn một liên kết hypermedia. Khi href chứa URI Template, Link có thể được đánh dấu là templated. HAL sẽ biểu diễn thông tin này bằng thuộc tính templated: true.

Ví dụ tạo liên kết tìm kiếm:

~~~java
import org.springframework.hateoas.Link;

Link searchLink = Link
        .of("/api/orders{?status,page,size,sort}")
        .withRel("search");
~~~

Có thể thêm link vào EntityModel:

~~~java
import org.springframework.hateoas.EntityModel;

EntityModel<OrderSummary> model = EntityModel.of(summary)
        .add(searchLink);
~~~

Trong ví dụ, rel search mô tả mục đích của liên kết. URI Template cho biết client có thể cung cấp status, page, size và sort. Link không tự gọi endpoint và cũng không tự kiểm tra các giá trị có hợp lệ với nghiệp vụ hay không.

Một phản hồi HAL minh họa:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "search": {
      "href": "https://api.example.com/api/orders{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Thuộc tính templated cho client biết href là template. Client cần mở rộng các biến trước khi gửi yêu cầu đến URI kết quả. Client không nên xem dấu ngoặc nhọn là ký tự thuộc query string của endpoint.

## 5. Mở rộng template bằng Link.expand

Spring HATEOAS cung cấp phương thức expand trên Link để thay các biến trong URI Template bằng giá trị cụ thể. Có thể truyền một map với tên biến và giá trị tương ứng:

~~~java
import java.util.Map;

import org.springframework.hateoas.Link;

Link searchTemplate = Link
        .of("/api/orders{?status,page,size,sort}")
        .withRel("search");

Link concreteLink = searchTemplate.expand(Map.of(
        "status", "PENDING",
        "page", 0,
        "size", 20,
        "sort", "createdAt,desc"
));

System.out.println(concreteLink.getHref());
~~~

Kết quả là một Link đã được mở rộng. Các biến được thay bằng giá trị tương ứng và query string được tạo theo quy tắc của URI Template. Sau khi mở rộng đầy đủ, link không còn cần cờ templated cho các biến đã được thay thế.

Có thể kiểm tra trạng thái của link:

~~~java
boolean templated = searchTemplate.isTemplated();
boolean expanded = concreteLink.isTemplated();
~~~

Trong ví dụ, searchTemplate là templated; concreteLink là URI cụ thể sau khi các biến đã được mở rộng. Phương thức expand tạo ra một link mới để sử dụng, không gửi HTTP request và không thay đổi trạng thái tài nguyên trên server.

Khi mở rộng, hãy cung cấp đúng tên biến đã xuất hiện trong template. Tên biến là một phần của hợp đồng điều hướng. Nếu template công bố page, client không nên truyền p hoặc pageNumber thay thế trừ khi API định nghĩa một template khác.

## 6. Mở rộng biến path

Biến path thường dùng để xác định một tài nguyên cụ thể. Ví dụ:

~~~java
Link orderTemplate = Link
        .of("/api/orders/{id}")
        .withRel("item");

Link orderLink = orderTemplate.expand(Map.of("id", 42));
~~~

Template /api/orders/{id} được mở rộng thành /api/orders/42. Client có thể dùng link item để tham chiếu đến một đơn hàng cụ thể.

Với một template có nhiều biến:

~~~java
Link itemTemplate = Link
        .of("/api/orders/{orderId}/items/{itemId}")
        .withRel("item");

Link itemLink = itemTemplate.expand(Map.of(
        "orderId", 42,
        "itemId", 3
));
~~~

URI kết quả:

~~~text
/api/orders/42/items/3
~~~

Giá trị biến cần được mã hóa đúng ngữ cảnh URI. Nếu định danh chứa dấu cách hoặc ký tự đặc biệt, hãy dùng cơ chế mở rộng của thư viện để tránh làm hỏng cấu trúc path. Không tự thay chuỗi {id} bằng một chuỗi tùy ý vì ký tự /, ?, # hoặc % có thể làm thay đổi cách URI được phân tích.

## 7. Mở rộng biến query

Biến query thường được dùng cho collection search:

~~~java
Link template = Link
        .of("/api/orders{?status,page,size}")
        .withRel("search");

Link pendingOrders = template.expand(Map.of(
        "status", "PENDING",
        "page", 0,
        "size", 20
));
~~~

Kết quả tương ứng:

~~~text
/api/orders?status=PENDING&page=0&size=20
~~~

Nếu giá trị query chứa ký tự cần mã hóa, ví dụ tên khách hàng có dấu cách hoặc ký tự &, thư viện sẽ mã hóa giá trị theo quy tắc của template. Điều này ngăn một giá trị dữ liệu vô tình trở thành dấu phân cách giữa các tham số.

Ví dụ, một giá trị tìm kiếm có thể là:

~~~java
Link search = Link.of("/api/orders{?customerName}")
        .withRel("search");

Link expanded = search.expand(Map.of(
        "customerName", "An & Bình"
));
~~~

Giá trị được mở rộng phải được percent-encode theo URI Template. Khi đọc URI kết quả, server giải mã query parameter theo quy tắc HTTP framework.

Một template có thể có nhiều biến tùy chọn. Nếu client không cần lọc theo trạng thái, nó có thể mở rộng template với page và size mà không cung cấp status. Các biến không có giá trị sẽ được xử lý theo quy tắc mở rộng của biểu thức; client nên kiểm thử các tổ hợp biến mà API dự kiến hỗ trợ.

## 8. Tạo template từ mapping Spring MVC

Khi liên kết được tạo từ mapping của controller, Spring HATEOAS có thể suy ra đường dẫn và metadata tham số từ phương thức được tham chiếu. Ví dụ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

// Method này nằm trong OrderController đã có orderAssembler và orderService.
@GetMapping("/api/orders")
public CollectionModel<EntityModel<OrderDto>> search(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Integer size
) {
    return orderAssembler.toCollectionModel(
            orderService.search(status, page, size)
    );
}

Link searchLink = linkTo(methodOn(OrderController.class)
        .search(null, null, null))
        .withRel("search");
~~~

Khi tạo link từ methodOn, các tham số null có thể được giữ như biến template theo metadata của mapping. Cách này giúp liên kết bám theo phương thức controller khi đường dẫn thay đổi. Cần kiểm tra href thực tế và cờ templated trong phiên bản Spring HATEOAS của dự án, đặc biệt khi method có nhiều tham số tùy chọn hoặc có quy tắc ánh xạ phức tạp.

Nếu cần kiểm soát chính xác tập biến được công bố, có thể tạo Link với template tường minh như các ví dụ trước. Dù dùng cách nào, hãy bảo đảm template chỉ công bố các tham số mà endpoint thực sự hỗ trợ.

## 9. Kết hợp template với RepresentationModelAssembler

Assembler có thể thêm một link template vào representation để client khám phá chức năng tìm kiếm:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
public class OrderSummaryAssembler {

    public EntityModel<OrderSummary> toModel(OrderSummary summary) {
        Link search = Link
                .of("/api/orders{?status,page,size,sort}")
                .withRel("search");

        return EntityModel.of(summary)
                .add(search);
    }
}
~~~

Đoạn mã minh họa tập trung vào việc công bố template. Trong ứng dụng thực tế, URI cơ sở cần được tạo theo cấu hình request và mapping của controller, đặc biệt khi ứng dụng chạy sau reverse proxy hoặc có context path. Tránh hard-code hostname vào assembler.

Nếu link template phụ thuộc vào một resource cha, hãy tạo href từ mapping hoặc URI builder phù hợp để giữ đúng định danh cha. Ví dụ, template collection dòng hàng của đơn hàng 42 có thể là /api/orders/42/items{?page,size}. Khi client mở rộng page và size, định danh đơn hàng vẫn được giữ nguyên.

## 10. Template không thay thế affordance

URI Template cho biết các biến có thể được chèn vào URI. Nó không tự mô tả đầy đủ phương thức HTTP, schema request body hoặc điều kiện nghiệp vụ của thao tác.

Ví dụ template:

~~~text
/api/orders{?status,page,size}
~~~

cho biết client có thể cung cấp các query variable. Nó không nói endpoint hỗ trợ GET hay POST, không xác định status có những giá trị nào và không mô tả quyền cần thiết.

Nếu client cần khám phá cách thực hiện một thao tác, API có thể công bố affordance hoặc hợp đồng media type phù hợp. Affordance có thể mô tả phương thức HTTP và dữ liệu đầu vào. Server vẫn phải kiểm tra xác thực, phân quyền, trạng thái tài nguyên và tính hợp lệ của các tham số khi nhận request.

Không nên nhầm việc một template có biến status với việc client được phép đặt trạng thái đơn hàng thành bất kỳ giá trị nào. Tên biến chỉ mô tả chỗ điền dữ liệu vào URI; quy tắc nghiệp vụ do endpoint và service quyết định.

## 11. Quy tắc mã hóa và bảo vệ URI

Mở rộng URI Template cần tuân theo ngữ cảnh của từng biến:

- Biến path đại diện cho một đoạn định danh; không để dữ liệu đầu vào tự ý tạo thêm segment.
- Biến query là giá trị của tham số; các ký tự như &, =, # và dấu cách cần được mã hóa đúng.
- Không ghép query string bằng nối chuỗi vì dễ tạo URL sai hoặc lỗi injection ở tầng URI.
- Không giải mã rồi mã hóa lặp nhiều lần; điều đó có thể làm thay đổi giá trị hoặc tạo double encoding.
- Không đưa dữ liệu bí mật như access token, mật khẩu hoặc thông tin cá nhân nhạy cảm vào URI vì URI thường xuất hiện trong log, lịch sử trình duyệt và hệ thống giám sát.

Template được server công bố cũng cần được xem là dữ liệu đầu vào từ xa. Client nên chỉ theo các URI phù hợp với chính sách bảo mật của ứng dụng, chẳng hạn kiểm soát scheme, host hoặc phạm vi domain nếu API có thể trả liên kết đến hệ thống khác.

## 12. Kiểm thử URI Template và Link.expand

Kiểm thử nên xác nhận template có đúng biến, mở rộng đúng giá trị và tạo URI an toàn.

Ví dụ kiểm thử Link trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;

class OrderLinkTemplateTest {

    @Test
    void expandsSearchTemplate() {
        Link template = Link
                .of("/api/orders{?status,page,size}")
                .withRel("search");

        assertThat(template.isTemplated()).isTrue();

        Link expanded = template.expand(Map.of(
                "status", "PENDING",
                "page", 0,
                "size", 20
        ));

        assertThat(expanded.isTemplated()).isFalse();
        assertThat(expanded.getHref())
                .contains("/api/orders?")
                .contains("status=PENDING")
                .contains("page=0")
                .contains("size=20");
        assertThat(expanded.getRel()).isEqualTo(template.getRel());
    }
}
~~~

Ví dụ kiểm thử link trong phản hồi HAL bằng MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
            .value(org.hamcrest.Matchers.containsString(
                    "{?status,page,size,sort}"
            )));
~~~

Các test này là ví dụ minh họa; cần đặt chúng trong test class của dự án và cung cấp controller, assembler cùng dependency cần thiết. Nên kiểm thử thêm:

- Template path có một biến và nhiều biến.
- Template query với một số biến được bỏ qua.
- Giá trị chứa dấu cách, dấu &, dấu tiếng Việt hoặc ký tự đặc biệt.
- Template có nhiều biến nhưng client chỉ cung cấp một phần.
- Link giữ nguyên rel sau khi mở rộng.
- Href HAL có templated: true trước khi mở rộng.
- URI sau mở rộng không còn biến bắt buộc chưa được thay thế.

Không nên chỉ kiểm tra một chuỗi URL tuyệt đối nếu hostname và context path thay đổi theo môi trường. Có thể kiểm tra phần path, query parameter và trạng thái templated; với các trường hợp mã hóa, xác nhận giá trị sau khi URI được phân tích hoặc giải mã theo đúng quy tắc.

## 13. Những lỗi thường gặp

**Tự ghép URI bằng chuỗi.** Nối chuỗi có thể làm sai dấu ?, &, dấu phân cách hoặc encoding. Dùng Link.expand hoặc URI builder phù hợp.

**Nhầm template với URI hoàn chỉnh.** Href có biến chưa mở rộng không phải lúc nào cũng có thể gửi trực tiếp như một request. Hãy mở rộng các biến cần thiết.

**Không công bố cờ templated.** Client cần biết href là template. Khi dùng Spring HATEOAS Link với URI Template, hãy kiểm tra HAL output có templated: true.

**Sai tên biến.** Template công bố page nhưng client mở rộng bằng pageNumber sẽ không thay đúng biến. Tên biến cần nhất quán giữa server và client.

**Mã hóa giá trị sai ngữ cảnh.** Dữ liệu chứa dấu /, ?, &, # hoặc dấu cách có thể làm thay đổi URI nếu tự thay chuỗi. Dùng cơ chế mở rộng template của thư viện.

**Coi template là hợp đồng hành động đầy đủ.** Template mô tả biến URI, không mô tả đầy đủ phương thức HTTP, request body hoặc quyền. Dùng affordance và hợp đồng endpoint khi cần thêm thông tin.

**Hard-code host trong assembler.** Hostname, scheme và context path có thể khác theo môi trường. Tạo link theo mapping hoặc ngữ cảnh request.

## 14. Ghi nhớ

URI Template là mẫu URI có biến chưa được gán giá trị. Cú pháp biểu thức như {id}, {?page,size} và {&sort} cho biết cách mở rộng biến trong path hoặc query. Spring HATEOAS cho phép tạo templated Link và mở rộng bằng Link.expand với map giá trị.

Một templated link trong HAL có thuộc tính templated: true. Client đọc rel và href, cung cấp các biến cần thiết rồi mở rộng template để có URI cụ thể. Việc mở rộng chỉ tạo URI; nó không gửi request, không cấp quyền và không thay thế affordance mô tả phương thức hoặc dữ liệu đầu vào.

Hãy tạo template theo đúng tham số endpoint hỗ trợ, dùng thư viện để xử lý encoding, tránh nối chuỗi URI thủ công và kiểm thử cả template lẫn URI sau khi mở rộng. Khi kết hợp Link, RepresentationModelAssembler và controller mapping, Spring HATEOAS giúp API công bố cách tham chiếu tài nguyên linh hoạt mà không buộc client tự đoán cấu trúc URL.
