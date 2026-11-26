# Không kiểm thử representation

Một API Spring HATEOAS có thể tạo đúng `EntityModel`, `CollectionModel` hoặc `PagedModel` trong bộ nhớ nhưng vẫn trả về representation sai cho client. Serializer có thể đổi tên relation, bỏ link, serialize embedded resource không đúng cấu trúc, chọn sai media type hoặc tạo URI khác với contract. Nếu chỉ kiểm thử service hay assembler mà không kiểm tra HTTP response thực tế, những lỗi này có thể lọt tới môi trường chạy.

Anti-pattern xuất hiện khi nhóm phát triển chỉ kiểm tra status code, DTO hoặc object model mà controller trả về, nhưng không xác minh representation hypermedia sau khi Spring MVC và message converter xử lý. Client không nhận một Java object; client nhận status, header, content type và payload đã serialize. Vì vậy, cần kiểm thử những gì client thực sự nhìn thấy.

Bài học này tập trung vào kiểm thử representation trong Spring HATEOAS bằng MockMvc, cách kiểm tra HAL links, embedded resources, pagination, URI template và affordance, cũng như cách phân chia unit test, MVC test và contract test để phát hiện lỗi đúng tầng.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao kiểm thử assembler chưa đủ để xác nhận hypermedia contract.
- Phân biệt unit test, MVC/integration test và consumer contract test.
- Kiểm tra status, content type và cấu trúc HAL bằng MockMvc.
- Xác minh relation, href, embedded resource và metadata phân trang.
- Kiểm tra link có điều kiện theo trạng thái hoặc quyền người dùng.
- Kiểm tra URI template và affordance khi API công bố chúng.
- Tránh assertion quá chặt khiến test hỏng khi route hợp lệ thay đổi.
- Thiết kế fixture và test case cho representation rỗng, lỗi hoặc thiếu link.
- Dùng test để phát hiện sự khác biệt giữa contract được tài liệu hóa và response thực tế.

## Vì sao kiểm thử representation là bắt buộc?

Giả sử assembler tạo model:

~~~java
EntityModel<OrderResponse> model = EntityModel.of(
    response,
    linkTo(methodOn(OrderController.class).one(orderId)).withSelfRel(),
    linkTo(methodOn(CustomerController.class).one(customerId))
        .withRel("customer")
);
~~~

Một unit test có thể xác nhận model có link `self` và `customer`. Nhưng response HTTP còn đi qua nhiều thành phần:

- Controller mapping và content negotiation.
- Spring HATEOAS message converter.
- Jackson module và serializer dành cho hypermedia.
- Cấu hình relation provider, CURIE hoặc media type.
- Servlet request context dùng để tạo link.
- Filter bảo mật và logic điều kiện theo principal.
- Cấu hình proxy hoặc forwarded header ảnh hưởng URI được tạo.

Lỗi ở bất kỳ lớp nào cũng có thể làm representation gửi tới client khác với model trong bộ nhớ. Ví dụ:

- `EntityModel` có link `customer`, nhưng JSON lại serialize relation thành tên khác.
- Controller trả đúng object nhưng response không có `Content-Type: application/hal+json`.
- Link được tạo thành URI nội bộ hoặc thiếu prefix reverse proxy.
- `PagedModel` có metadata page nhưng thiếu relation `next` khi còn trang.
- Link `cancel` vẫn xuất hiện cho người dùng không có quyền.
- Một collection được serialize dưới key relation trong `_embedded` không đúng tên đã cấu hình bằng `@Relation`.

Test representation kiểm tra toàn bộ đường đi từ request HTTP tới payload đã serialize. Đây là bằng chứng quan trọng cho contract mà client sử dụng.

## Ba tầng kiểm thử bổ trợ nhau

Không phải mọi test đều cần dựng toàn bộ ứng dụng. Mỗi tầng có mục tiêu riêng:

| Tầng kiểm thử | Kiểm tra điều gì? | Phát hiện tốt nhất |
|---|---|---|
| Unit test assembler/model | Dữ liệu và link được thêm vào model trong bộ nhớ | Mapping sai, thiếu relation do logic assembler |
| MVC/integration test | HTTP status, header, media type và JSON hypermedia sau serialization | Serializer, content negotiation, relation name, URI và cấu hình MVC |
| Consumer/contract test | Client có thể tìm relation và thực hiện luồng đã công bố | Khác biệt giữa contract server và cách client diễn giải |

Unit test nhanh và dễ cô lập. MVC test cần thiết để xác nhận payload thực tế. Consumer contract test hữu ích khi server có nhiều client độc lập hoặc API được tích hợp bởi đội khác.

Không nên dùng một unit test của assembler để kết luận representation HAL đã đúng. Cũng không cần biến mọi trường hợp thành end-to-end test qua hạ tầng thật; chọn tầng kiểm thử phù hợp với rủi ro cần phát hiện.

Ví dụ unit test assembler chỉ xác nhận model được tạo đúng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler =
        new OrderModelAssembler();

    @Test
    void addsSelfLinkToOrderModel() {
        OrderResponse order = new OrderResponse(
            UUID.randomUUID(),
            "SUBMITTED",
            UUID.randomUUID()
        );

        EntityModel<OrderResponse> model = assembler.toModel(order);

        assertThat(model.getRequiredLink(IanaLinkRelations.SELF))
            .isNotNull();
    }
}
~~~

Đoạn test giả định ứng dụng có `OrderModelAssembler` với method `toModel()`. Nó không chạy Jackson serializer, content negotiation hoặc servlet request context, vì vậy vẫn cần MVC test cho HTTP representation.

## Chuẩn bị một endpoint mẫu

Giả sử API trả về đơn hàng cùng link tới chính nó và khách hàng:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.mvc.WebMvcLinkBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderResponse(UUID id, String status, UUID customerId) {
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService orders;

    OrderController(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    EntityModel<OrderResponse> one(
            @PathVariable("orderId") UUID orderId) {

        OrderResponse order = orders.findById(orderId);

        return EntityModel.of(
            order,
            WebMvcLinkBuilder.linkTo(
                WebMvcLinkBuilder.methodOn(OrderController.class)
                    .one(orderId))
                .withSelfRel(),
            WebMvcLinkBuilder.linkTo(
                WebMvcLinkBuilder.methodOn(CustomerController.class)
                    .one(order.customerId()))
                .withRel("customer")
        );
    }
}
~~~

Trong response HAL, client kỳ vọng một representation tương tự:

~~~json
{
  "id": "6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16",
  "status": "SUBMITTED",
  "customerId": "4bb3b37d-9e95-42e6-96a8-8a8e2e0bcb40",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16"
    },
    "customer": {
      "href": "https://api.example.com/customers/4bb3b37d-9e95-42e6-96a8-8a8e2e0bcb40"
    }
  }
}
~~~

Đây là ví dụ contract để định hướng assertion. Host và prefix trong href có thể thay đổi theo cấu hình ứng dụng, proxy hoặc môi trường. Test nên kiểm tra đúng relation và phần URI có ý nghĩa, trừ khi host tuyệt đối là một phần contract cần bảo đảm.

## Kiểm thử HTTP response bằng MockMvc

Với Spring MVC, `MockMvc` cho phép gọi endpoint qua MVC infrastructure và kiểm tra response mà không cần mở server thật. Dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc` để kiểm tra cấu hình ứng dụng và serializer đang được dùng:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRepresentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderAsHalWithSelfAndCustomerLinks() throws Exception {
        UUID orderId =
            UUID.fromString("6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16");

        mockMvc.perform(get("/orders/{orderId}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(orderId.toString()))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/" + orderId)))
            .andExpect(jsonPath("$._links.customer.href")
                .exists());
    }
}
~~~

Ví dụ giả định test fixture hoặc database test đã tạo đơn hàng tương ứng và `OrderQueryService` trả dữ liệu cho ID này. Nếu ứng dụng dùng test slice như `@WebMvcTest`, cần mock các dependency và bảo đảm cấu hình hypermedia message converter có trong test context.

Các assertion trên kiểm tra:

- Request được xử lý thành công.
- Client yêu cầu HAL và server trả đúng media type.
- Payload chứa dữ liệu resource.
- Relation `self` và `customer` có mặt.
- Link `self` trỏ tới đúng resource được yêu cầu.

### Kiểm tra content negotiation

Không chỉ kiểm tra JSON body. Hãy xác nhận server thực sự trả media type mà client cần:

~~~java
mockMvc.perform(get("/orders/{orderId}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON));
~~~

Nếu API hỗ trợ nhiều representation, viết test riêng cho từng media type đã cam kết. Không giả định JSON thông thường và HAL có cùng cấu trúc. Với HAL, client cần `_links` và có thể cần `_embedded`; nếu server trả `application/json` thì những thành phần này có thể không tồn tại.

Có thể kiểm tra status và media type của response lỗi riêng. Ví dụ, nếu API dùng Problem Details, test cần xác nhận `application/problem+json` thay vì mong đợi HAL chỉ vì endpoint thông thường trả HAL.

## Kiểm thử relation và href

Một test representation cần xác nhận cả tên relation và target. Chỉ kiểm tra JSON có chứa chuỗi `/orders/` là quá yếu; chuỗi đó có thể xuất hiện trong field khác hoặc một link sai relation.

Nên dùng JSONPath để kiểm tra cấu trúc:

~~~java
mockMvc.perform(get("/orders/{orderId}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Nếu relation là custom relation hoặc có CURIE, hãy kiểm tra đúng key relation mà client sẽ nhìn thấy sau serialization. Ví dụ với CURIE prefix `ex`, relation có thể xuất hiện dưới key `ex:approval`; test phải phản ánh contract HAL đã công bố.

### Tránh kiểm tra href quá chặt

Test sau dễ vỡ:

~~~java
.andExpect(jsonPath("$._links.self.href")
    .value("http://localhost/orders/" + orderId));
~~~

Host, scheme hoặc prefix có thể thay đổi do test environment, TLS termination hoặc reverse proxy. Nếu mục tiêu là xác nhận đúng resource, có thể kiểm tra suffix:

~~~java
.andExpect(jsonPath("$._links.self.href")
    .value(endsWith("/orders/" + orderId)));
~~~

Nếu public origin là một phần quan trọng của contract, hãy kiểm tra nó trong một test cấu hình riêng có thiết lập forwarded headers rõ ràng. Đừng vô tình khóa mọi test representation vào host cục bộ.

## Kiểm thử embedded resources

`CollectionModel` có thể serialize phần tử trong `_embedded`. Relation của collection hoặc item phụ thuộc cấu hình relation provider và `@Relation`. Vì vậy, cần xác nhận đúng tên relation và nội dung item:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "SUBMITTED",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
~~~

Test có thể xác nhận:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0].id").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
        .exists());
~~~

Tên `orders` trong ví dụ phải khớp với relation thực tế do `@Relation` hoặc `LinkRelationProvider` tạo ra. Nếu thay đổi tên class hoặc cấu hình relation, test sẽ phát hiện contract bị đổi.

Với collection rỗng, kiểm tra đúng semantics mà API cam kết. HAL có thể không serialize `_embedded` nếu không có phần tử; client cần dựa vào collection relation và metadata thích hợp thay vì giả định luôn có phần tử đầu tiên.

## Kiểm thử pagination

`PagedModel` cung cấp page metadata cùng các link điều hướng. Khi có nhiều trang, response thường có `first`, `prev`, `self`, `next` và `last` tùy vị trí hiện tại.

Ví dụ response trang đầu:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "SUBMITTED"
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders?page=0&size=1"
    },
    "next": {
      "href": "/orders?page=1&size=1"
    },
    "last": {
      "href": "/orders?page=4&size=1"
    }
  },
  "page": {
    "size": 1,
    "totalElements": 5,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Test nên kiểm tra cả metadata và relation điều hướng:

~~~java
mockMvc.perform(get("/orders?page=0&size=1")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(1))
    .andExpect(jsonPath("$.page.totalPages").value(5))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists());
~~~

Ở trang cuối, test cần xác nhận `next` không được công bố nếu không còn trang tiếp theo. Ở trang đầu, `prev` có thể vắng mặt. Những link có điều kiện như vậy phải được kiểm tra theo từng trạng thái phân trang.

Đừng chỉ assert query string chứa `page=1`. Điều quan trọng là relation `next` được công bố và href của nó có thể được client sử dụng. Server có thể chuyển từ page number sang cursor mà client vẫn điều hướng bằng cùng relation.

## Kiểm thử link có điều kiện

Một số link chỉ xuất hiện khi resource ở trạng thái phù hợp hoặc principal có quyền. Ví dụ, link `cancel` chỉ được công bố khi đơn hàng chưa giao và người dùng có quyền hủy.

Với trường hợp không đủ điều kiện, kiểm tra relation vắng mặt:

~~~java
mockMvc.perform(get("/orders/{orderId}", shippedOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Với trường hợp được phép, kiểm tra relation xuất hiện:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/orders/{orderId}", cancellableOrderId)
        .with(user("order-owner").authorities(
            new SimpleGrantedAuthority("ORDER_CANCEL")))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Đoạn thứ hai là mẫu cho ứng dụng dùng Spring Security Test; cần import `user` từ `SecurityMockMvcRequestPostProcessors` và tạo fixture order thuộc về principal tương ứng. Nếu policy có kiểm tra ownership, chỉ authority thôi chưa đủ: fixture phải đúng owner.
Các biến `shippedOrderId` và `cancellableOrderId` là ID của hai fixture được tạo trước test; chúng phải tham chiếu tới đơn hàng có trạng thái tương ứng.

Nên có test cho cả bốn nhóm:

- Người dùng có quyền và resource ở trạng thái cho phép: link xuất hiện.
- Người dùng thiếu quyền: link vắng mặt.
- Người dùng có quyền nhưng resource ở trạng thái không cho phép: link vắng mặt.
- Người dùng khác owner: link vắng mặt nếu policy yêu cầu quyền sở hữu.

Việc link vắng mặt không thay thế kiểm thử authorization trên endpoint action. Hãy kiểm tra request trực tiếp tới action vẫn bị từ chối khi principal không có quyền hoặc trạng thái resource không hợp lệ.

## Kiểm thử URI template

Nếu API công bố URI template, test cần xác nhận thuộc tính `templated` và các biến được công bố:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders{?status,createdAfter}",
      "templated": true
    }
  }
}
~~~

Ví dụ assertion:

~~~java
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("{?status,createdAfter}")));
~~~

Nếu client phải gửi filter theo template, kiểm tra các biến cần thiết có trong template. Không nên chỉ xác nhận link `search` tồn tại vì link có thể bị serialize thành URI thường, làm client không biết cần mở rộng biến.

## Kiểm thử affordance và HAL-FORMS

Khi API công bố affordance, representation chứa nhiều thông tin hơn một link đơn: method, target và metadata về input. Chỉ kiểm tra `_links.cancel.href` không chứng minh client có đủ thông tin để gửi thao tác.

Với HAL-FORMS, test nên:

- Gửi `Accept` đúng media type HAL-FORMS mà ứng dụng hỗ trợ.
- Kiểm tra `Content-Type` trả về tương ứng.
- Xác nhận relation hoặc template của action được công bố.
- Kiểm tra HTTP method trong template.
- Kiểm tra các input property bắt buộc và kiểu dữ liệu được mô tả.
- Kiểm tra affordance vắng mặt khi action không khả dụng.

Ví dụ cấu trúc HAL-FORMS rút gọn:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "cancel": {
      "method": "POST",
      "target": "/order-cancellations/42",
      "properties": [
        {
          "name": "reason",
          "required": true
        }
      ]
    }
  }
}
~~~

Đường dẫn và cấu trúc template thực tế phải theo serializer HAL-FORMS mà ứng dụng cấu hình. Tránh copy một snapshot cứng cho mọi endpoint; hãy assert các thuộc tính contract quan trọng như method, target relation và input property.

## Kiểm thử với @WebMvcTest và @SpringBootTest

Có thể dùng `@WebMvcTest` khi muốn kiểm tra controller và MVC slice nhanh:

~~~java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(OrderController.class)
class OrderControllerWebTest {
    // Mock OrderQueryService và các collaborator của controller.
}
~~~

Test slice cần bảo đảm cấu hình Spring HATEOAS, message converter và security liên quan được nạp đúng. Nếu cấu hình hypermedia của ứng dụng nằm ngoài slice mặc định, import cấu hình cần thiết vào test.

Dùng `@SpringBootTest` với `@AutoConfigureMockMvc` khi muốn xác nhận toàn bộ cấu hình ứng dụng, gồm controller advice, security filter chain, HATEOAS configuration và serializer. Test chậm hơn nhưng phù hợp cho một số contract representation quan trọng.

Không cần dùng `@SpringBootTest` cho mọi assertion nhỏ. Một chiến lược cân bằng có thể gồm nhiều unit test assembler, một số MVC slice test cho từng loại representation, và một số integration test cho luồng quan trọng.

## Những assertion nên có trong representation test

Một checklist thực tế:

| Thành phần | Assertion nên có |
|---|---|
| HTTP status | Status phù hợp với request và nghiệp vụ |
| Content type | Đúng media type mà client yêu cầu |
| Payload | Field quan trọng có đúng giá trị và kiểu |
| `self` | Có link tới resource hiện tại |
| Related links | Relation và href có mặt khi contract yêu cầu |
| Conditional links | Link xuất hiện hoặc vắng mặt theo trạng thái/quyền |
| `_embedded` | Relation collection và item structure đúng |
| Pagination | Page metadata và `next`/`prev` phù hợp |
| URI template | `templated=true` và biến cần thiết có mặt |
| Affordance | Method và input schema được công bố đúng |
| Error response | Status, media type, problem fields và support link đúng |
| Security | Link không tiết lộ action không được phép; endpoint vẫn enforce quyền |

Không nhất thiết mọi test phải kiểm tra tất cả thành phần. Chọn assertion theo contract của từng endpoint và rủi ro nếu representation sai.

## Tránh brittle test và snapshot quá lớn

Một snapshot toàn bộ JSON có thể phát hiện nhiều thay đổi, nhưng thường tạo nhiễu khi thứ tự field, host, timestamp hoặc dữ liệu fixture thay đổi. Snapshot cũng có thể khiến nhóm chấp nhận cập nhật hàng loạt mà không xem xét semantics.

Ưu tiên assertion theo contract:

- Kiểm tra relation name thay vì tìm chuỗi href bất kỳ.
- Kiểm tra href trỏ đúng resource thay vì cố định host không cần thiết.
- Kiểm tra metadata phân trang thay vì khóa toàn bộ query string.
- Kiểm tra method và input property của affordance thay vì snapshot mọi field.
- Dùng fixture ổn định cho ID và trạng thái.
- Chỉ dùng snapshot khi payload lớn và toàn bộ cấu trúc thực sự là contract cần bảo vệ.

Nếu dùng snapshot, hãy loại bỏ hoặc chuẩn hóa giá trị không ổn định như timestamp, host động và ID ngẫu nhiên trước khi so sánh.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra controller trả object | Không phát hiện lỗi serializer hoặc media type | Kiểm thử HTTP response qua MockMvc |
| Chỉ assert status 200 | Link và payload có thể sai nhưng test vẫn xanh | Assert content type, relation và field quan trọng |
| Chỉ test assembler | Không kiểm tra `_links` và `_embedded` sau serialization | Bổ sung MVC/integration test |
| Hard-code toàn bộ absolute href | Test vỡ khi host hoặc proxy prefix thay đổi hợp lệ | Assert relation và phần URI cần thiết |
| Không kiểm tra relation name | Sai `@Relation` hoặc relation provider không bị phát hiện | Assert JSONPath theo key relation |
| Bỏ qua link có điều kiện | Action có thể xuất hiện sai quyền hoặc sai trạng thái | Test cả trường hợp link có và không có |
| Chỉ kiểm tra link action | Không xác nhận endpoint thực thi có bảo vệ quyền | Test trực tiếp action endpoint |
| Bỏ qua `_embedded` | Client không đọc được collection theo contract | Kiểm tra embedded relation và item |
| Chỉ test trang đầu | Không phát hiện `next`, `prev` sai | Test trang đầu, giữa và cuối |
| Không kiểm tra media type | Client có thể nhận JSON thường thay vì HAL | Assert `Content-Type` |
| Dùng snapshot quá rộng | Test nhiễu và khó hiểu thay đổi contract | Assert theo semantics và chuẩn hóa giá trị động |
| Không cấu hình HATEOAS trong MVC slice | Test khác cấu hình chạy thật | Import cấu hình hoặc dùng integration test phù hợp |

## Ghi nhớ

Kiểm thử assembler chỉ xác nhận object trong bộ nhớ; nó không chứng minh client nhận đúng hypermedia representation. Hãy dùng MockMvc hoặc integration test để kiểm tra status, media type, payload đã serialize, relation, href, embedded resources, pagination, URI template và affordance. Với link có điều kiện, kiểm tra cả trường hợp xuất hiện lẫn vắng mặt và vẫn kiểm tra authorization ở endpoint thực thi. Assertion nên tập trung vào semantics của contract, tránh khóa host hoặc toàn bộ JSON nếu chúng không phải cam kết ổn định. Một representation test tốt giúp phát hiện sớm khi cấu hình Spring HATEOAS, serializer hoặc controller làm thay đổi điều client thực sự nhìn thấy.

## Tài liệu tham khảo

- [Spring HATEOAS – Traverson and client support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client)
- [Spring HATEOAS – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring Boot – Testing the Web Layer](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.with-mock-environment)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Security – Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
