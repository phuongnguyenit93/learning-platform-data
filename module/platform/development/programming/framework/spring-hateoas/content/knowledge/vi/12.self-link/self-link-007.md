# Self link và canonical URL

Trong REST API, **self link** là liên kết có quan hệ self, trỏ đến chính tài nguyên đang được biểu diễn. Nó cho client biết URI mà client có thể dùng để tham chiếu lại tài nguyên. Với Spring HATEOAS, self link thường được tạo bằng phương thức withSelfRel() và dựa trên mapping của controller.

**Canonical URL** là URI ưu tiên để định danh hoặc truy cập một tài nguyên khi tài nguyên đó có nhiều URI tương đương, chẳng hạn alias, đường dẫn cũ hoặc nhiều cách định tuyến. Trong hypermedia, có thể công bố URI ưu tiên bằng relation chuẩn canonical. Self link và canonical link có thể trỏ đến cùng một URI, nhưng chúng trả lời hai câu hỏi khác nhau: self chỉ ra tài nguyên hiện tại; canonical chỉ ra URI được xem là phiên bản chuẩn khi có nhiều URI thay thế.

Trong Spring HATEOAS, hai loại link này được biểu diễn bằng Link và LinkRelation. Khi serialize HAL JSON, relation trở thành key trong _links. Bài học này giải thích cách chọn và tạo self link, khi nào nên công bố canonical URL, cách xử lý alias và redirect, cùng cách kiểm thử hợp đồng hypermedia.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của relation self và canonical.
- Phân biệt URI của request hiện tại với URI chuẩn của tài nguyên.
- Tạo self link bằng linkTo, methodOn và withSelfRel().
- Công bố canonical link bằng IanaLinkRelations.CANONICAL.
- Thiết kế alias, redirect và URI ổn định cho tài nguyên.
- Kiểm thử self link và canonical link trong HAL JSON.

## Self link là gì?

Self link là liên kết có relation self, trỏ đến tài nguyên mà response đang mô tả. Đây là một trong những link cơ bản của hypermedia vì nó cho client biết URI để truy cập lại tài nguyên hiện tại.

Ví dụ response của một đơn hàng:

~~~json
{
  "id": 42,
  "description": "Bàn phím cơ",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
~~~

Trong ví dụ, self là relation và href là URI của đơn hàng. Client có thể theo link này để tải lại biểu diễn mới nhất hoặc tham chiếu tài nguyên trong luồng tương tác.

Self link không phải một trường dữ liệu nghiệp vụ như id hay status. Nó thuộc phần hypermedia của representation. Việc có self link giúp client không cần tự ghép /orders/ với ID để tạo URI.

### Tạo self link trong Spring HATEOAS

Spring HATEOAS cung cấp WebMvcLinkBuilder để tạo link từ mapping của controller. Cách thường dùng là kết hợp linkTo, methodOn và withSelfRel():

~~~java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderResponse> toModel(OrderResponse order) {
    return EntityModel.of(order,
        linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
}
~~~

Trong đó:

- methodOn(OrderController.class).one(order.id()) tạo lời gọi mô phỏng để Spring HATEOAS đọc mapping và tham số của method.
- linkTo(...) xây URI theo mapping đó.
- withSelfRel() gắn relation chuẩn self cho link.

methodOn không gửi HTTP request và không thực thi nghiệp vụ của controller như một lần gọi API thật. Nó cung cấp thông tin method để link builder suy ra URI.

Nếu mapping controller thay đổi, link được tạo từ mapping sẽ theo đường dẫn mới. Điều này giảm lỗi do lặp lại chuỗi URL ở nhiều nơi.

### Self link ở item và collection

Self link có thể xuất hiện ở nhiều cấp:

- EntityModel<T> thường có self link đến item.
- CollectionModel<T> thường có self link đến collection.
- PagedModel<T> có self link đến trang hiện tại, bao gồm các tham số phân trang liên quan.

Ví dụ collection đơn hàng:

~~~java
CollectionModel<EntityModel<OrderResponse>> all() {
    List<EntityModel<OrderResponse>> items = orderService.findAll().stream()
        .map(order -> EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()))
        .toList();

    return CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
~~~

Link self của collection trỏ đến endpoint danh sách; link self của từng item trỏ đến endpoint chi tiết tương ứng. Client cần đọc đúng cấp để không nhầm URI của collection với URI của một item.

## Canonical URL là gì?

Một tài nguyên có thể được truy cập bằng nhiều URI. Điều này có thể xảy ra khi:

- API cung cấp alias thân thiện như /customers/me bên cạnh /customers/42.
- Đường dẫn cũ vẫn được hỗ trợ sau khi API đổi cấu trúc.
- Một tài nguyên có cả URI lồng nhau và URI độc lập.
- Hệ thống có nhiều host hoặc route tương đương qua gateway.
- Một nội dung có các URL khác nhau do tham số không làm thay đổi danh tính tài nguyên.

Canonical URL là URI được công bố như địa chỉ ưu tiên trong số các URI tương đương. Relation canonical của IANA được dùng để chỉ ra phiên bản hoặc URI được ưu tiên của tài nguyên.

Ví dụ, khách hàng hiện tại có thể truy cập qua alias /customers/me, trong khi URI chuẩn của khách hàng là /customers/42:

~~~json
{
  "id": 42,
  "name": "Nguyễn An",
  "_links": {
    "self": {
      "href": "https://api.example.com/customers/me"
    },
    "canonical": {
      "href": "https://api.example.com/customers/42"
    }
  }
}
~~~

Ở đây:

- self phản ánh URI đang được dùng để truy cập biểu diễn hiện tại.
- canonical công bố URI ổn định được chọn làm địa chỉ chuẩn của tài nguyên.

Đây là một cách thiết kế hợp lệ khi API muốn giữ alias nhưng vẫn giúp client biết URI chuẩn. Nếu alias không cần thiết, API có thể chuyển hướng sang URI chuẩn thay vì duy trì hai địa chỉ trong thời gian dài.

## Phân biệt self link và canonical link

Hai relation này có thể cùng trỏ đến một URI, nhưng semantics không giống nhau:

| Khía cạnh | self | canonical |
| --- | --- | --- |
| Ý nghĩa | URI tham chiếu đến tài nguyên đang được biểu diễn | URI được ưu tiên khi có nhiều URI tương đương |
| Mục đích | Cho client biết tài nguyên hiện tại ở đâu | Cho client biết địa chỉ chuẩn của tài nguyên |
| Có bắt buộc không? | Thường được công bố trong representation tài nguyên | Tùy API; hữu ích khi có alias hoặc URI thay thế |
| Có thể trỏ đến cùng URI? | Có | Có |
| Ví dụ | /customers/me | /customers/42 |

Nếu tài nguyên chỉ có một URI ổn định, self link thường là đủ. Không cần thêm canonical link trùng hệt chỉ để tăng số lượng link. Canonical có ý nghĩa nhất khi API thực sự muốn công bố một URI ưu tiên giữa nhiều URI có thể truy cập cùng tài nguyên.

### Canonical không phải redirect

Canonical link chỉ là thông tin hypermedia về URI được ưu tiên. Nó không tự chuyển request, không buộc client phải đi theo và không thay thế cơ chế redirect HTTP.

Nếu API muốn mọi request đến alias được chuyển sang URI chuẩn, server có thể trả redirect như 301 Moved Permanently hoặc 308 Permanent Redirect tùy ngữ nghĩa và yêu cầu giữ method. Nếu API muốn tiếp tục phục vụ alias nhưng chỉ gợi ý URI chuẩn, có thể trả response bình thường kèm relation canonical.

Hai cách này có tác động khác nhau đến client và cache. Hãy chọn chính sách rõ ràng, tránh vừa chuyển hướng vừa công bố alias như thể đó là địa chỉ lâu dài nếu điều đó gây khó hiểu cho người tiêu thụ API.

### Canonical trong API và canonical cho trang web

Relation canonical cũng được dùng trong HTML hoặc HTTP Link header để chỉ ra phiên bản ưu tiên của một tài nguyên web. Trong REST API, ý nghĩa cốt lõi vẫn là công bố URI chuẩn. Tuy nhiên, client API có thể dùng relation để điều hướng hoặc lưu tham chiếu; không nên mặc định mọi client sẽ xử lý nó giống trình thu thập dữ liệu tìm kiếm.

Canonical không phải cơ chế versioning. Nếu /v1/customers/42 và /v2/customers/42 đại diện cho hai hợp đồng API khác nhau, việc chọn version mặc định cần được xác định bằng chính sách versioning. Không dùng canonical để che giấu khác biệt không tương thích giữa các phiên bản.

## Công bố canonical link bằng Spring HATEOAS

Spring HATEOAS cung cấp hằng số IanaLinkRelations.CANONICAL để tạo relation chuẩn:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link canonical = Link.of("/customers/42")
    .withRel(IanaLinkRelations.CANONICAL);
~~~

Có thể dùng link builder để tạo canonical URI dựa trên mapping controller:

~~~java
Link canonical = linkTo(methodOn(CustomerController.class)
    .one(customer.id()))
    .withRel(IanaLinkRelations.CANONICAL);
~~~

Trong thực tế, canonical link nên được tạo từ một quy tắc định danh ổn định. Nếu cùng tài nguyên có nhiều alias, tất cả alias nên công bố cùng một canonical URI để client có kết quả nhất quán.

## Ví dụ: alias và canonical URL cho khách hàng hiện tại

Giả sử API hỗ trợ hai endpoint:

- /customers/me: lấy khách hàng gắn với danh tính đã xác thực.
- /customers/{id}: lấy khách hàng theo định danh công khai.

Endpoint /customers/me là alias thuận tiện. URI chuẩn của tài nguyên vẫn là /customers/{id}.

DTO và service:

~~~java
import java.util.Optional;

public record CustomerResponse(Long id, String name) {}

public interface CustomerService {
    CustomerResponse findCurrent(String username);
    Optional<CustomerResponse> findById(Long id);
}
~~~

Controller có thể trả self link đến alias hiện tại và canonical link đến URI theo ID:

~~~java
import java.security.Principal;
import java.util.Optional;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/customers")
class CustomerController {

    private final CustomerService customerService;

    CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/me")
    EntityModel<CustomerResponse> current(Principal principal) {
        CustomerResponse customer =
            customerService.findCurrent(principal.getName());

        return EntityModel.of(customer,
            linkTo(methodOn(CustomerController.class).current(null))
                .withSelfRel(),
            linkTo(methodOn(CustomerController.class).one(customer.id()))
                .withRel(IanaLinkRelations.CANONICAL));
    }

    @GetMapping("/{id}")
    EntityModel<CustomerResponse> one(@PathVariable Long id) {
        CustomerResponse customer = customerService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        return EntityModel.of(customer,
            linkTo(methodOn(CustomerController.class).one(id)).withSelfRel());
    }
}
~~~

Ví dụ giả định service đã kiểm tra danh tính hiện tại và trả DTO phù hợp. current(null) là lời gọi mô phỏng để tạo link; tham số Principal không tham gia vào URI. Trong một số cấu hình, có thể dùng phương thức builder khác để tạo link đến endpoint không có tham số URI; điều quan trọng là link được sinh từ mapping thay vì ghép chuỗi thủ công.

Response HAL của /customers/me có thể có dạng:

~~~json
{
  "id": 42,
  "name": "Nguyễn An",
  "_links": {
    "self": {
      "href": "https://api.example.com/customers/me"
    },
    "canonical": {
      "href": "https://api.example.com/customers/42"
    }
  }
}
~~~

Client có thể tiếp tục dùng self link để gọi lại alias, hoặc dùng canonical link khi cần lưu URI chuẩn của tài nguyên. Endpoint theo ID cũng công bố self link đến URI chuẩn của nó.

Trong code production, nếu việc gọi current(null) không phù hợp với chữ ký controller hoặc cấu hình tham số, có thể dùng phương thức builder phù hợp với mapping hoặc tạo link từ method không phụ thuộc principal. Không truyền thông tin xác thực của người dùng vào URI.

## Thiết kế URI chuẩn ổn định

Canonical URL chỉ hữu ích nếu nó thực sự ổn định. Hãy chọn định danh không phụ thuộc thuộc tính có thể thay đổi như tên hiển thị, email hoặc trạng thái.

~~~text
Không ổn định: /customers/nguyen-an
Ổn định hơn:  /customers/42
Hoặc:        /customers/8f2c6d80-6c6d-4a22-9c4d-7d4d20a0d101
~~~

Một số nguyên tắc:

- Dùng ID công khai có vòng đời ổn định.
- Không để canonical URI phụ thuộc vào tên hiển thị hoặc thông tin cá nhân có thể đổi.
- Giữ nhất quán chữ hoa/chữ thường, dấu gạch, dấu slash cuối và encoding.
- Xác định host, scheme và prefix bên ngoài khi ứng dụng chạy sau reverse proxy hoặc API gateway.
- Nếu đổi cấu trúc URI, công bố canonical URI mới và duy trì alias/redirect theo chính sách tương thích.
- Không tái sử dụng URI cũ cho tài nguyên khác nếu client có thể giữ tham chiếu cũ.

### URI tuyệt đối và reverse proxy

Self hoặc canonical link có thể là URI tương đối hoặc tuyệt đối tùy hợp đồng API và cấu hình. URI tuyệt đối gồm scheme, host và path; URI tương đối có thể được client phân giải dựa trên URI của response.

Trong môi trường production, ứng dụng có thể chạy sau reverse proxy. Nếu Spring không nhận biết đúng forwarded headers, link tạo ra có thể dùng host nội bộ, port nội bộ hoặc scheme http thay vì địa chỉ HTTPS công khai.

Hãy cấu hình forwarded headers và proxy đáng tin cậy theo môi trường triển khai. Dùng link builder để lấy URI từ request context; không tự tin cậy Host hoặc forwarded header do client tùy ý gửi nếu hạ tầng chưa xác thực chúng.

## Canonical URL và các biến thể biểu diễn

Một tài nguyên có thể có nhiều representation tùy media type, ngôn ngữ hoặc tham số trình bày. Cần phân biệt:

- Nhiều URI cùng trỏ đến một tài nguyên.
- Một URI cung cấp nhiều representation qua content negotiation.
- Nhiều tài nguyên khác nhau có dữ liệu tương tự.

Nếu cùng một URI trả JSON hoặc XML theo header Accept, self link vẫn có thể trỏ đến URI đó; Content-Type của response cho biết representation hiện tại. Nếu API công bố URI thay thế cho định dạng khác, relation alternate có thể phù hợp hơn canonical.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42",
      "type": "application/hal+json"
    },
    "alternate": {
      "href": "/orders/42.xml",
      "type": "application/xml"
    }
  }
}
~~~

Không nên gắn canonical cho mọi biến thể chỉ vì chúng mô tả cùng dữ liệu. Canonical nói URI nào được ưu tiên; alternate nói có một cách biểu diễn hoặc tài nguyên thay thế.

### Query parameters và canonical policy

Query parameters có thể thay đổi ngữ nghĩa của tài nguyên được yêu cầu. Ví dụ /orders?page=0&size=20 và /orders?page=1&size=20 là hai trang khác nhau của cùng collection. Self link của mỗi trang cần giữ đúng page và size hiện tại.

Ngược lại, tham số theo dõi không làm thay đổi nội dung, như một số tracking parameter, có thể không cần nằm trong canonical URI nếu chính sách API xác định chúng là phụ trợ. Không loại bỏ query parameters một cách máy móc: filter, sort, page, locale hoặc tham số ảnh hưởng đến representation có thể là phần thiết yếu của URI hiện tại.

## Self link, canonical và khả năng tiến hóa API

Self link giúp client luôn biết URI của tài nguyên trong response hiện tại. Canonical link giúp API công bố URI chuẩn khi nhiều route cùng đại diện một tài nguyên. Kết hợp hai relation có thể hỗ trợ thay đổi cấu trúc route mà vẫn giữ client hoạt động.

Ví dụ, API có thể giữ /customers/me cho trải nghiệm tiện lợi trong khi canonical URI vẫn là /customers/42. Sau này, API có thể ngừng alias và trả redirect sang URI chuẩn. Client đã được thiết kế để đọc canonical link có thể cập nhật tham chiếu theo hợp đồng.

Khi thay đổi URI:

1. Xác định URI chuẩn mới và semantics của tài nguyên.
2. Công bố canonical link mới trong response alias hoặc response chuyển tiếp.
3. Duy trì URI cũ bằng alias hoặc redirect trong thời gian chuyển đổi phù hợp.
4. Kiểm thử link từ các entry point và client đã biết.
5. Chỉ ngừng alias khi chính sách tương thích cho phép.

Canonical link không thay thế versioning hoặc quản lý breaking changes. Nếu schema response hoặc semantics thay đổi không tương thích, cần có chiến lược phiên bản API riêng.

## Bảo mật khi công bố self và canonical

Self link và canonical link là URI công khai trong response. Không xem việc client không biết URI là một lớp bảo vệ.

- Luôn xác thực và phân quyền ở server cho từng request.
- Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào URI.
- Không công bố canonical URI vượt qua ranh giới tenant hoặc quyền truy cập.
- Đảm bảo alias /me chỉ phân giải theo principal đã xác thực, không nhận ID của người khác từ client.
- Không dùng canonical link để vô tình tiết lộ định danh nội bộ hoặc đường dẫn quản trị.

Nếu cùng một tài nguyên có URI riêng theo tenant, hãy xác định canonical URI trong đúng phạm vi tenant và kiểm tra quyền trước khi tạo response.

## Kiểm thử self link và canonical link

Kiểm thử cần xác minh relation và URI đích. Với endpoint chuẩn, self link thường trỏ đến item. Với endpoint alias, self link có thể trỏ đến alias còn canonical link trỏ đến URI chuẩn.

Ví dụ với Spring MVC Test:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void currentCustomerExposesSelfAndCanonicalLinks() throws Exception {
        mockMvc.perform(get("/customers/me")
                .principal(() -> "customer-user")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/customers/me")))
            .andExpect(jsonPath("$._links.canonical.href")
                .value(endsWith("/customers/42")));
    }
}
~~~

Test giả định cấu hình test xác thực principal customer-user và dữ liệu ánh xạ đến khách hàng ID 42. Nếu host hoặc prefix thay đổi theo môi trường, kiểm tra phần path hoặc phân tích URI thay vì cố định toàn bộ host.

Nên bổ sung test cho:

1. Endpoint chuẩn /customers/42 có self link đến chính tài nguyên.
2. Endpoint alias /customers/me công bố canonical link đến URI chuẩn.
3. Alias và URI chuẩn trả cùng tài nguyên trong phạm vi quyền phù hợp.
4. Redirect hoạt động đúng nếu API chọn chuyển hướng alias.
5. Query parameters có ý nghĩa được giữ trong self link của collection hoặc trang.
6. Link tuyệt đối dùng đúng scheme, host và prefix sau reverse proxy.
7. Người dùng không có quyền không thể truy cập tài nguyên bằng cách thay URI.

## Những sai lầm thường gặp

**Nghĩ self và canonical luôn giống nhau.** Chúng có thể trỏ cùng URI, nhưng self xác định tài nguyên hiện tại còn canonical chỉ ra URI ưu tiên giữa nhiều URI tương đương.

**Nghĩ canonical link tự chuyển hướng request.** Canonical chỉ công bố URI được ưu tiên. Muốn chuyển hướng, server phải trả status redirect phù hợp.

**Tạo link bằng cách nối chuỗi.** Cách này dễ sai khi mapping, path variable, context path hoặc proxy thay đổi. Dùng linkTo, methodOn và URI builder.

**Dùng tên hoặc email làm canonical ID.** Các thuộc tính đó có thể đổi hoặc chứa thông tin cá nhân. Hãy dùng định danh ổn định và công khai phù hợp.

**Bỏ query parameters quan trọng khỏi self link.** Filter, sort và page có thể làm thay đổi kết quả. Self link phải tham chiếu đúng representation hoặc truy vấn hiện tại.

**Coi canonical là cơ chế bảo mật.** URI có thể bị chia sẻ hoặc đoán được. Server vẫn phải kiểm tra quyền truy cập cho từng request.

**Dùng canonical để giải quyết versioning.** Canonical không thay thế chính sách versioning và không làm các thay đổi schema không tương thích trở nên an toàn.

## Kết luận

Self link cho client biết URI của tài nguyên đang được biểu diễn. Canonical link công bố URI ưu tiên khi tài nguyên có nhiều URI tương đương. Trong Spring HATEOAS, dùng withSelfRel() cho self link và IanaLinkRelations.CANONICAL cho canonical link; tạo URI bằng mapping controller để tránh phụ thuộc vào chuỗi đường dẫn viết tay.

Khi API chỉ có một URI ổn định, self link thường là đủ. Khi có alias hoặc route thay thế, canonical link giúp client nhận biết địa chỉ chuẩn. Hãy xác định rõ chính sách redirect, giữ URI ổn định, cấu hình proxy đúng và kiểm thử cả relation lẫn URI để hợp đồng hypermedia có thể tiến hóa an toàn.
