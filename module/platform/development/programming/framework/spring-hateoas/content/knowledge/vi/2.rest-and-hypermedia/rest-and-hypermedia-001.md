# Các ràng buộc REST

REST (Representational State Transfer) là một kiểu kiến trúc cho hệ thống phân tán. REST mô tả cách các thành phần giao tiếp thông qua tài nguyên, biểu diễn tài nguyên và một giao diện thống nhất. Một API dùng HTTP, trả JSON và có các endpoint CRUD chưa chắc đã là REST theo đúng nghĩa. Điểm quyết định là API có tuân thủ các ràng buộc kiến trúc REST hay không.

Trong Spring HATEOAS, các ràng buộc này đặc biệt quan trọng vì thư viện giúp ứng dụng đưa hypermedia vào biểu diễn tài nguyên. Thay vì yêu cầu client tự ghép URL theo quy ước nội bộ của server, response có thể cung cấp những liên kết mô tả các bước tiếp theo mà client được phép thực hiện.

Sau bài học này, bạn có thể:

- Giải thích sáu ràng buộc REST và mục đích của từng ràng buộc.
- Phân biệt tài nguyên, biểu diễn tài nguyên và trạng thái tương tác của client.
- Giải thích vì sao giao diện thống nhất và HATEOAS có vai trò trung tâm trong REST.
- Nhận biết Spring HATEOAS hỗ trợ phần nào của kiến trúc và phần nào vẫn là trách nhiệm thiết kế của ứng dụng.
- Kiểm tra response hypermedia ở mức hợp đồng API.

## REST giải quyết vấn đề gì?

Trong một hệ thống phân tán, client và server có thể được phát triển, triển khai và nâng cấp độc lập. Nếu client phải biết cấu trúc URL nội bộ, cách server lưu dữ liệu hoặc thứ tự cố định của mọi bước nghiệp vụ, hai phía sẽ phụ thuộc chặt vào nhau. Một thay đổi nhỏ ở server có thể buộc nhiều client phải phát hành phiên bản mới.

REST giảm sự phụ thuộc đó bằng cách đặt ra các quy tắc giao tiếp có thể áp dụng rộng rãi:

- Tài nguyên được nhận diện bằng định danh, thường là URI.
- Client và server trao đổi các biểu diễn của tài nguyên.
- Thông điệp mang đủ thông tin để bên nhận hiểu cách xử lý.
- Client khám phá các chuyển tiếp khả dụng thông qua hypermedia.
- Các thành phần được tách biệt và có thể giao tiếp qua những lớp trung gian.

Ví dụ, một hệ thống đơn hàng có thể cung cấp tài nguyên `/orders/42`. URI nhận diện đơn hàng số 42; JSON trả về là biểu diễn của đơn hàng tại thời điểm response được tạo. Khi đơn hàng đang chờ thanh toán, response có thể chứa liên kết `payment`. Khi đơn hàng đã thanh toán, liên kết đó có thể biến mất và một liên kết khác như `shipment` có thể xuất hiện. Client dựa vào các liên kết được cung cấp để khám phá bước tiếp theo.

REST là kiểu kiến trúc, không phải tên gọi khác của JSON, HTTP hay CRUD. JSON là một định dạng biểu diễn; HTTP là một giao thức có thể dùng để triển khai giao diện REST; CRUD chỉ mô tả một số thao tác dữ liệu và không tự bảo đảm có hypermedia.

## Sáu ràng buộc của REST

REST gồm sáu ràng buộc. Năm ràng buộc đầu tạo nên nền tảng kiến trúc; ràng buộc cuối là tùy chọn.

| Ràng buộc | Ý nghĩa | Lợi ích chính |
| --- | --- | --- |
| Client–server | Tách trách nhiệm giao diện người dùng khỏi lưu trữ và xử lý dữ liệu | Hai phía có thể phát triển độc lập |
| Stateless | Mỗi request chứa đủ ngữ cảnh để server xử lý; server không giữ trạng thái phiên tương tác của client giữa các request | Dễ mở rộng và phục hồi request |
| Cacheable | Response phải chỉ rõ có thể cache hay không | Giảm độ trễ và tải lên server |
| Uniform interface | Các thành phần giao tiếp qua một giao diện thống nhất, có ngữ nghĩa rõ ràng | Giảm phụ thuộc vào cách triển khai cụ thể |
| Layered system | Client không cần biết request đi qua bao nhiêu lớp trung gian | Dễ bổ sung gateway, proxy, cache và lớp bảo mật |
| Code-on-demand (tùy chọn) | Server có thể gửi mã thực thi cho client | Có thể mở rộng hành vi client khi cần |

### 1. Client–server

Client chịu trách nhiệm trình bày thông tin và tương tác với người dùng. Server chịu trách nhiệm quản lý tài nguyên, áp dụng quy tắc nghiệp vụ và lưu trữ dữ liệu. Hai phía chỉ cần thống nhất hợp đồng giao tiếp.

Nhờ sự tách biệt này, có thể thay giao diện web bằng ứng dụng di động mà không phải viết lại toàn bộ nghiệp vụ server. Ngược lại, server có thể thay đổi cách lưu trữ hoặc triển khai nội bộ mà không buộc client thay đổi, miễn là hợp đồng giao tiếp vẫn được giữ.

Spring HATEOAS hỗ trợ tạo biểu diễn tài nguyên có liên kết, nhưng không tự tạo ra sự tách biệt kiến trúc. Ứng dụng vẫn cần giữ controller, service, domain và lớp giao diện ở các vai trò phù hợp.

### 2. Stateless

Mỗi request phải mang đủ thông tin để server hiểu và xử lý request đó. Server không dựa vào một phiên hội thoại được lưu riêng cho client để đoán request hiện tại thuộc bước nào.

Ví dụ, request lấy đơn hàng có thể gửi thông tin xác thực trong header `Authorization`. Server xác thực request, đọc dữ liệu đơn hàng và trả response. Request kế tiếp cũng phải tự mang thông tin cần thiết.

Stateless không có nghĩa server không được lưu dữ liệu. Server vẫn lưu đơn hàng, tài khoản, trạng thái thanh toán và các dữ liệu nghiệp vụ lâu dài. Điều bị hạn chế là trạng thái phiên tương tác của client được dùng ngầm giữa các request.

Lợi ích của stateless:

- Bất kỳ instance server phù hợp nào cũng có thể xử lý request tiếp theo.
- Có thể mở rộng số instance mà ít phụ thuộc vào session affinity.
- Request dễ được thử lại và kiểm tra độc lập hơn.

Đổi lại, request có thể phải gửi lại một phần ngữ cảnh và server cần xác thực mỗi request. Vì vậy, cần cân nhắc kích thước request, cơ chế xác thực và tính an toàn khi retry.

### 3. Cacheable

Response phải cho biết dữ liệu có thể được lưu cache hay không. Client, proxy hoặc cache trung gian có thể dùng response đã lưu thay vì gửi request mới đến server, nếu các chỉ thị HTTP cho phép.

HTTP cung cấp các header thường dùng:

- `Cache-Control: max-age=60` cho phép cache response trong khoảng thời gian được chỉ định.
- `Cache-Control: no-store` yêu cầu không lưu response vào cache.
- `ETag` cung cấp mã nhận diện một phiên bản biểu diễn; client có thể gửi `If-None-Match` để kiểm tra phiên bản.
- `Last-Modified` và `If-Modified-Since` hỗ trợ kiểm tra thay đổi dựa trên thời điểm.
- `Vary` cho biết những header request nào làm thay đổi response và cần được xét khi chọn bản cache.

Cache cần được thiết kế theo tính chất dữ liệu. Danh mục công khai ít thay đổi có thể phù hợp với cache lâu hơn. Dữ liệu cá nhân hoặc response có liên kết phụ thuộc quyền của người dùng cần chính sách cache thận trọng; không nên để cache dùng chung trả biểu diễn của người này cho người khác.

Spring HATEOAS tập trung vào mô hình tài nguyên và liên kết. Chính sách cache vẫn được quyết định bằng HTTP và cấu hình của ứng dụng, chẳng hạn qua header response, ETag hoặc cơ chế cache ở tầng phù hợp.

### 4. Uniform interface — giao diện thống nhất

Đây là ràng buộc có ảnh hưởng trực tiếp nhất đến cách thiết kế API REST. Các thành phần tương tác thông qua một giao diện nhất quán thay vì dựa vào chi tiết triển khai riêng của từng server. Giao diện thống nhất có bốn khía cạnh.

**Nhận diện tài nguyên.** Mỗi tài nguyên có định danh, thường là URI. Ví dụ `/orders/42` nhận diện một đơn hàng. URI nhận diện tài nguyên; nó không nhất thiết là tên của một bảng cơ sở dữ liệu hay đường dẫn đến một đối tượng nội bộ.

**Thao tác trên tài nguyên thông qua biểu diễn.** Client nhận biểu diễn tài nguyên và gửi biểu diễn phù hợp để yêu cầu thay đổi. Với HTTP, các method như `GET`, `POST`, `PUT`, `PATCH` và `DELETE` thể hiện ngữ nghĩa thao tác. Server có thể thay đổi cấu trúc lưu trữ mà không cần để client biết.

**Thông điệp tự mô tả.** Request và response phải mang thông tin để bên nhận hiểu cách xử lý. Method, URI, status code, header `Content-Type`, `Accept` và các metadata liên quan đều góp phần tạo nên ý nghĩa của thông điệp. Chẳng hạn, `Content-Type: application/hal+json` cho biết body dùng định dạng HAL JSON.

**HATEOAS — hypermedia là động cơ của trạng thái ứng dụng.** Response cung cấp liên kết để client khám phá các chuyển tiếp có thể thực hiện tiếp theo. Client hiểu ý nghĩa của quan hệ liên kết (link relation), sau đó theo URL được server cung cấp thay vì tự tạo URL từ một quy tắc đường dẫn ngầm định.

HATEOAS giúp giảm phụ thuộc vào cấu trúc URI. Nếu server thay đổi đường dẫn của tài nguyên nhưng vẫn cung cấp liên kết đúng quan hệ, client được thiết kế để đi theo liên kết có thể tiếp tục hoạt động mà không cần biết đường dẫn mới từ trước.

### 5. Layered system — hệ thống phân lớp

Client giao tiếp với giao diện của hệ thống và không cần biết request được xử lý trực tiếp bởi ứng dụng hay đi qua một số lớp trung gian. Các lớp đó có thể gồm reverse proxy, API gateway, bộ cân bằng tải, cache, lớp xác thực hoặc dịch vụ trung gian.

Mỗi lớp có thể bổ sung một trách nhiệm riêng. Ví dụ, gateway xác thực token và giới hạn tốc độ; cache phục vụ response còn hiệu lực; ứng dụng nghiệp vụ xử lý đơn hàng. Client vẫn sử dụng cùng hợp đồng HTTP.

Ràng buộc này giúp hệ thống dễ tổ chức và mở rộng. Tuy nhiên, mỗi lớp trung gian có thể làm tăng độ trễ và tạo thêm điểm cần quan sát, cấu hình hoặc xử lý lỗi. Các lớp cũng phải giữ đúng ngữ nghĩa của HTTP và không làm sai lệch hợp đồng response.

### 6. Code-on-demand — mã theo yêu cầu (tùy chọn)

Server có thể gửi mã thực thi để client tải và chạy, qua đó mở rộng hành vi của client. JavaScript được tải từ server về trình duyệt là ví dụ quen thuộc.

Đây là ràng buộc tùy chọn. Nhiều API REST không sử dụng code-on-demand mà vẫn có thể tuân thủ REST. Với API doanh nghiệp, việc gửi mã thực thi thường không cần thiết và phải được cân nhắc về bảo mật, quyền thực thi cũng như khả năng kiểm soát phiên bản.

## HATEOAS và Spring HATEOAS

HATEOAS là phần của giao diện thống nhất cho phép client khám phá trạng thái tương tác thông qua hypermedia. Một response không chỉ mang dữ liệu mà còn có thể mô tả các liên kết có ý nghĩa trong ngữ cảnh hiện tại.

Ví dụ, một đơn hàng có thể có các quan hệ:

| Quan hệ liên kết | Ý nghĩa |
| --- | --- |
| `self` | Liên kết đến chính tài nguyên đơn hàng |
| `orders` | Liên kết đến tập hợp đơn hàng |
| `payment` | Bước thanh toán hiện khả dụng |
| `cancel` | Hành động hủy hiện khả dụng |
| `shipment` | Thông tin hoặc bước tiếp theo về giao hàng |

Các liên kết nghiệp vụ như `payment` hay `cancel` chỉ nên xuất hiện khi hành động tương ứng khả dụng trong trạng thái hiện tại. Server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ khi nhận request; việc client nhìn thấy một liên kết không thay thế kiểm tra bảo mật ở server.

Spring HATEOAS cung cấp các kiểu dữ liệu và công cụ để xây dựng biểu diễn hypermedia:

- `RepresentationModel` là lớp cơ sở cho mô hình có thể chứa liên kết.
- `EntityModel<T>` bọc một tài nguyên hoặc DTO cùng các liên kết.
- `CollectionModel<T>` biểu diễn một tập hợp tài nguyên.
- `PagedModel<T>` hỗ trợ biểu diễn tập hợp có phân trang.
- `Link` biểu diễn một liên kết cùng quan hệ của nó.
- `WebMvcLinkBuilder`, `linkTo` và `methodOn` giúp tạo liên kết dựa trên mapping của controller.
- `RepresentationModelAssembler` giúp tập trung việc chuyển đổi đối tượng miền thành representation model.

Thêm dependency `spring-boot-starter-hateoas` vào ứng dụng Spring Boot để tích hợp Spring HATEOAS. Khi cấu hình HAL được sử dụng, tài nguyên có liên kết thường được trả về dưới dạng `application/hal+json`.

### Ví dụ: tạo liên kết cho tài nguyên đơn hàng

Giả sử ứng dụng có DTO đơn hàng và service cung cấp dữ liệu:

```java
import java.util.List;
import java.util.Optional;

public record Order(Long id, String description, String status) {}

public interface OrderService {
    Optional<Order> findById(Long id);
    List<Order> findAll();
}
```

Controller có thể dùng `EntityModel` và `CollectionModel` để trả về dữ liệu kèm liên kết:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        List<EntityModel<Order>> items = orderService.findAll().stream()
            .map(order -> EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()))
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

`linkTo(methodOn(...))` lấy mapping từ chữ ký controller để tạo URI. Cách này giúp tránh lặp lại chuỗi đường dẫn trong nhiều nơi của ứng dụng. `withSelfRel()` tạo quan hệ chuẩn `self`; `withRel("orders")` tạo quan hệ có tên `orders`.

Với HAL JSON, response cho `GET /orders/42` có dạng khái quát như sau (host và port phụ thuộc môi trường chạy):

```json
{
  "id": 42,
  "description": "Bàn phím cơ",
  "status": "PENDING_PAYMENT",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "orders": {
      "href": "http://localhost:8080/orders"
    }
  }
}
```

Client có thể đọc `_links.self.href` để truy cập lại đơn hàng và `_links.orders.href` để đi đến tập hợp. Client không cần tự ghép chuỗi `/orders/` với mã đơn hàng.

### Liên kết và mô tả hành động

Một liên kết HAL thông thường gồm URI và quan hệ liên kết. Nó cho client biết có một đích đến với ý nghĩa nhất định, nhưng bản thân liên kết HAL cơ bản không mô tả đầy đủ HTTP method hay các trường đầu vào của một biểu mẫu.

Khi hợp đồng cần mô tả rõ hành động, method và dữ liệu đầu vào, Spring HATEOAS hỗ trợ affordances. Affordance gắn mô tả khả năng tương tác với một liên kết. Các định dạng như HAL-FORMS có thể biểu diễn template, method và các thuộc tính đầu vào để client hiểu cách thực hiện hành động.

Ví dụ, response của một đơn hàng đang chờ thanh toán có thể công bố affordance `pay` với phương thức `POST` và thông tin cần thiết cho thao tác thanh toán. Khi đơn hàng đã thanh toán, server có thể không công bố affordance đó nữa. Cách biểu diễn cụ thể phụ thuộc media type và cấu hình hypermedia mà API lựa chọn.

Không nên gắn một liên kết `cancel` cố định vào mọi đơn hàng nếu có đơn hàng không thể hủy. Liên kết hoặc affordance nên phản ánh trạng thái hiện tại. Dù vậy, server phải xác minh lại trạng thái, quyền truy cập và dữ liệu đầu vào tại thời điểm xử lý lệnh vì trạng thái có thể thay đổi sau khi response được gửi.

## Kiểm thử hợp đồng hypermedia

Kiểm thử API hypermedia cần xác minh cả dữ liệu và liên kết. Nếu chỉ kiểm tra mã trạng thái hoặc các trường JSON, test có thể bỏ sót việc server vô tình xóa hoặc đổi quan hệ liên kết mà client đang sử dụng.

Ví dụ với Spring MVC Test:

```java
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
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderResponseContainsNavigationLinks() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists());
    }
}
```

Test trên giả định dữ liệu đơn hàng mã 42 đã được chuẩn bị trong môi trường test. Trong dự án thực tế, nên bổ sung test cho các trạng thái nghiệp vụ khác nhau, chẳng hạn liên kết `cancel` chỉ xuất hiện khi đơn hàng có thể hủy, hoặc affordance thanh toán chỉ xuất hiện khi đơn hàng đang chờ thanh toán.

Một bộ kiểm thử hợp đồng hypermedia nên xem xét:

1. Response có đúng media type mà API công bố hay không.
2. Mỗi tài nguyên có liên kết `self` phù hợp hay không.
3. Các quan hệ liên kết quan trọng có mặt và trỏ đến đúng tài nguyên hay không.
4. Liên kết hoặc affordance có phản ánh trạng thái nghiệp vụ và quyền hiện tại hay không.
5. Client có thể đi theo liên kết để thực hiện luồng nghiệp vụ mà không phải tự dựng URI hay không.
6. Những thay đổi về URI có giữ nguyên quan hệ liên kết và ngữ nghĩa hợp đồng mà client phụ thuộc hay không.

## Những nhầm lẫn thường gặp

**Dùng HTTP và JSON đồng nghĩa với REST.** HTTP và JSON là công nghệ thường gặp khi triển khai API REST, nhưng một API chỉ trả JSON tại các endpoint cố định có thể thiếu giao diện thống nhất và HATEOAS.

**Stateless nghĩa là server không lưu dữ liệu.** Server vẫn lưu trạng thái nghiệp vụ. Stateless nói về việc mỗi request phải tự mang ngữ cảnh cần thiết, không dựa vào trạng thái phiên client được lưu ngầm.

**Có URL trong response là đã có HATEOAS.** Liên kết cần có quan hệ và ngữ nghĩa để client hiểu mục đích. Nếu client vẫn phải biết trước mọi đường dẫn và tự quyết định cách ghép URL, hypermedia chưa thực sự điều khiển quá trình khám phá.

**Link tự mô tả đầy đủ một lệnh.** Link HAL cơ bản chủ yếu cung cấp đích đến và quan hệ. Khi cần mô tả method và dữ liệu đầu vào, hãy xem xét affordances và media type phù hợp như HAL-FORMS.

**Có affordance là server đã bảo đảm quyền thực hiện.** Affordance mô tả khả năng được công bố trong response. Server vẫn phải kiểm tra xác thực, phân quyền, trạng thái và quy tắc nghiệp vụ khi nhận request.

**Spring HATEOAS tự động làm API trở thành REST.** Thư viện cung cấp công cụ tạo representation model, link và affordance. Kiến trúc chỉ đạt được mục tiêu khi ứng dụng thiết kế đúng các ràng buộc REST và client thực sự sử dụng hypermedia.

## Kết luận

Sáu ràng buộc REST tạo nên một kiến trúc giao tiếp có tính phân tách, khả năng mở rộng và hợp đồng rõ ràng. Trong đó, giao diện thống nhất và HATEOAS giúp client khám phá tài nguyên cũng như các chuyển tiếp nghiệp vụ từ response của server. Spring HATEOAS hỗ trợ hiện thực hóa phần này bằng representation model, link builder, assembler và affordance.

Khi thiết kế API, hãy bắt đầu từ tài nguyên và ngữ nghĩa nghiệp vụ, xác định biểu diễn cùng quan hệ liên kết cần công bố, rồi kiểm thử các liên kết như một phần của hợp đồng API. Cách tiếp cận này giúp client phụ thuộc vào ý nghĩa của API thay vì phụ thuộc vào cấu trúc URL và chi tiết triển khai của server.
