# Kiểm thử self link

## Mục tiêu

Trong API HATEOAS, self link xác định URI của representation hiện tại. Với item resource, link này dẫn tới chính item đó; với collection resource, nó dẫn tới collection cùng trạng thái truy vấn hiện tại. Một response có thể chứa dữ liệu đúng nhưng vẫn có hợp đồng hypermedia sai nếu self link thiếu, trỏ nhầm tài nguyên hoặc làm mất các tham số tìm kiếm.

Kiểm thử self link cần xác nhận cả relation và đích đến của href. Với Spring HATEOAS, cách đáng tin cậy là gọi endpoint qua MockMvc, nhận HAL JSON rồi kiểm tra nội dung _links.self.href. Cách này bao phủ controller mapping, WebMvcLinkBuilder, request context, message converter và Jackson hypermedia module.

Sau bài học, bạn có thể:

- Giải thích self relation trong representation HATEOAS.
- Kiểm tra self link của item resource bằng MockMvc.
- Xác nhận href chứa đúng path variable và trỏ tới tài nguyên hiện tại.
- Kiểm tra self link của collection và trang phân trang.
- Phân biệt unit test link model với HTTP integration test.
- Kiểm tra link khi ứng dụng có context path hoặc proxy.
- Nhận diện các lỗi phổ biến khi test HAL links.

## Self link là một phần của hợp đồng API

Trong HAL, links được đặt trong _links. Relation self xác định URI của resource representation hiện tại:

~~~json
{
  "id": "order-42",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/order-42"
    }
  }
}
~~~

Client có thể theo self link để tải lại hoặc làm mới representation. Vì vậy, self link cần trỏ tới đúng tài nguyên được mô tả trong response.

Khi kiểm thử, đừng chỉ xác nhận _links tồn tại. Một assertion như jsonPath("$._links").exists() không phát hiện trường hợp self link trỏ nhầm collection, nhầm ID hoặc một endpoint cũ. Test cần kiểm tra relation cụ thể và URI đích.

Các điều cần xác minh:

- Response có relation self.
- Href không rỗng và là URI hợp lệ.
- Path của href trỏ tới đúng resource.
- Path variable trong href khớp ID của response.
- Href không bị thay bằng một URL hard-code cũ.
- Với collection có filter hoặc pagination, self link giữ ngữ cảnh truy vấn.
- Response được serialize theo media type mà client yêu cầu.

## Tạo self link bằng WebMvcLinkBuilder

Giả sử controller quản lý đơn hàng tại /api/orders/{id}. Assembler chuyển domain object thành DTO và gắn self link theo mapping của controller:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse response = new OrderResponse(
                order.id(),
                order.status());

        return EntityModel.of(
                response,
                linkTo(methodOn(OrderController.class)
                        .findById(order.id()))
                        .withSelfRel());
    }
}
~~~

methodOn(...) tạo proxy để Spring HATEOAS đọc mapping của method. Nó không gọi method controller thật. linkTo(...) dùng mapping cùng request context để tạo URI. withSelfRel() gắn relation chuẩn self cho link.

Controller trả representation do assembler tạo:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> findById(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }
}
~~~

Các kiểu domain trong ví dụ có thể là record đơn giản:

~~~java
import java.util.UUID;

record Order(UUID id, String status) {
}

record OrderResponse(UUID id, String status) {
}
~~~

Khi mapping /api/orders/{id} thay đổi, link builder tiếp tục đọc mapping mới từ controller. Test self link sẽ phát hiện nếu code vô tình quay lại URL hard-code không còn đúng với mapping.

## Kiểm thử item self link bằng MockMvc

MockMvc tạo request servlet giả lập và chạy qua Spring MVC. Vì WebMvcLinkBuilder cần request context để tạo URI đầy đủ, đây là cách phù hợp để kiểm tra link được phát ra trong response HTTP.

Ví dụ dùng @WebMvcTest để chỉ khởi tạo web layer:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerLinkTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsSelfLinkForRequestedOrder() throws Exception {
        UUID id = UUID.fromString(
                "a4b3f5c2-91d7-4b80-9f2a-123456789abc");

        given(orderService.findById(id))
                .willReturn(new Order(id, "PAID"));

        mockMvc.perform(get("/api/orders/{id}", id)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$._links.self.href")
                        .value(endsWith("/api/orders/" + id)));
    }
}
~~~

Assertion endsWith(...) cho phép host và port trong MockMvc thay đổi theo test environment, nhưng vẫn xác nhận path cuối trỏ đúng ID. Nếu API có base path hoặc context path khác, cập nhật suffix theo hợp đồng công khai của ứng dụng.

MockitoBean thuộc Spring Framework 6.2 trở lên. Với dự án Spring Boot cũ hơn, có thể dùng MockBean từ Spring Boot Test. WebMvcTest chỉ nạp web slice; Import đưa assembler thực tế vào test để link được tạo theo đúng code production.

Test trên kiểm tra nhiều lớp cùng lúc:

1. Mapping GET /api/orders/{id} được chọn.
2. Service trả đúng order có ID đã yêu cầu.
3. Assembler tạo EntityModel và relation self.
4. WebMvcLinkBuilder tạo href từ controller mapping.
5. Message converter serialize model thành HAL JSON.

Nếu test chỉ tạo EntityModel bằng tay rồi kiểm tra hasLink("self"), nó không xác minh URI do mapping tạo ra và cũng không kiểm tra HAL serializer.

## Kiểm tra self link trỏ đúng tài nguyên

Có thể tăng độ chắc chắn bằng cách đọc href từ response rồi gọi lại URI đó. Cách này xác nhận link không chỉ đúng về hình thức mà còn dẫn tới endpoint có thể truy cập.

~~~java
import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.springframework.test.web.servlet.MvcResult;

MvcResult result = mockMvc.perform(get("/api/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

String body = result.getResponse().getContentAsString();
String selfHref = JsonPath.read(body, "$._links.self.href");
URI selfUri = URI.create(selfHref);

mockMvc.perform(get(selfUri.getRawPath())
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(id.toString()));
~~~

Trong ví dụ này, test lấy path từ href để gửi request trong cùng MockMvc instance. Nếu link chứa query string có ý nghĩa, cần giữ cả raw query khi tạo request thứ hai. Nếu ứng dụng triển khai dưới context path, cần giữ context path theo cấu hình test.

Khi endpoint yêu cầu authentication, request theo self link phải mang cùng thông tin xác thực phù hợp. Self link không bỏ qua security filter và không bảo đảm người dùng vẫn có quyền ở lần gọi tiếp theo.

Không phải mọi self link đều phải được kiểm thử bằng cách gọi lại. Với endpoint có side effect hoặc yêu cầu dữ liệu biến động, assertion trên URI cùng một test riêng cho khả năng truy cập thường rõ ràng hơn.

## Kiểm thử self link của collection

Collection resource cũng có self link. Với collection không phân trang:

~~~java
mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/api/orders")));
~~~

Self link của collection đại diện collection hiện tại, không phải một item trong collection. Nếu collection response có embedded items, mỗi item có thể có self link riêng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "_links": {
          "self": {
            "href": "/api/orders/order-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/api/orders"
    }
  }
}
~~~

Test cần phân biệt hai cấp:

- $._links.self.href là self link của collection.
- $._embedded.orders[0]._links.self.href là self link của item đầu tiên.

Nếu chỉ kiểm tra $.._links.self.href bằng JSONPath recursive descent, test có thể tìm thấy link self của item và bỏ sót việc self link cấp collection bị thiếu.

## Kiểm thử self link của trang phân trang

Với PagedModel, self link cần phản ánh trang và filter hiện tại. Ví dụ request:

~~~http
GET /api/orders?status=PAID&page=1&size=10
Accept: application/hal+json
~~~

Self link cần giữ các tham số đang xác định representation:

~~~text
/api/orders?status=PAID&page=1&size=10
~~~

Có thể kiểm tra từng query parameter mà không phụ thuộc thứ tự chúng xuất hiện trong URI:

~~~java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("page", "1")
                .param("size", "10")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page.number").value(1))
        .andExpect(jsonPath("$.page.size").value(10))
        .andExpect(jsonPath("$._links.self.href")
                .value(allOf(
                        containsString("status=PAID"),
                        containsString("page=1"),
                        containsString("size=10"))));
~~~

Không nên so sánh toàn bộ href bằng một chuỗi tuyệt đối nếu host, port, context path hoặc thứ tự query parameters thay đổi theo môi trường. Hãy kiểm tra chính xác những phần thuộc hợp đồng: resource path, filter, page và size.

Với filter có ký tự đặc biệt hoặc Unicode, URI có thể encode giá trị. Khi đó nên parse URI và kiểm tra query parameter đã decode thay vì tìm chuỗi thô. Điều này tránh test phụ thuộc vào cách percent-encoding được biểu diễn.

## Unit test assembler và HTTP test khác nhau thế nào?

Có thể kiểm thử assembler riêng để xác minh model chứa relation self:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

EntityModel<OrderResponse> model = assembler.toModel(order);

assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
~~~

Unit test này nhanh và hữu ích khi assembler có nhiều nhánh tạo links. Tuy nhiên, WebMvcLinkBuilder cần request context để tạo URI. Nếu gọi assembler ngoài request context, test có thể gặp lỗi thiếu ServletRequestAttributes hoặc phải tự thiết lập request giả.

Không nên tự tạo request context phức tạp chỉ để test một href đã được MockMvc bao phủ. Dùng:

- Unit test cho logic chọn relation, trạng thái và dữ liệu model.
- MockMvc test cho URI thực tế, controller mapping, request context và HAL serialization.
- Integration test với application context đầy đủ khi cần xác minh cấu hình proxy, context path, security hoặc message converter tùy chỉnh.

Nếu muốn test unit assembler độc lập, có thể tách logic quyết định relation khỏi phần tạo URI. Khi đó unit test kiểm tra quyết định nghiệp vụ, còn MockMvc kiểm tra link builder.

## Kiểm tra context path và forwarded headers

Trong production, API có thể được triển khai sau gateway hoặc reverse proxy. URI bên ngoài có thể chứa context path hoặc host khác với servlet container. Self link phải phù hợp với URI công khai mà client dùng để gọi API.

Ví dụ:

~~~text
https://gateway.example.com/store/api/orders/order-42
~~~

Trong khi ứng dụng nội bộ nhận request tại:

~~~text
http://orders-service:8080/api/orders/order-42
~~~

Nếu proxy gửi forwarded headers và Spring Framework được cấu hình để xử lý chúng, link builder có thể tạo URI công khai. Chỉ tin forwarded headers từ proxy đáng tin cậy; không chấp nhận host hoặc scheme tùy ý do client gửi.

Trong test, hãy thiết lập context path hoặc forwarded headers theo đúng cấu hình triển khai rồi kiểm tra href. Tránh hard-code host nội bộ trong assembler vì nó làm hỏng links khi ứng dụng chạy qua gateway.

## Những lỗi thường gặp

- **Chỉ kiểm tra _links tồn tại:** kiểm tra riêng _links.self.href và xác minh URI đích.
- **Kiểm tra self bằng recursive JSONPath:** có thể vô tình khớp self link của item thay vì collection; dùng JSONPath đúng cấp.
- **So sánh nguyên URL tuyệt đối:** test dễ hỏng do host, port hoặc context path thay đổi; kiểm tra path và query thuộc hợp đồng.
- **Không gửi Accept HAL JSON:** test có thể nhận media type khác hoặc không kiểm tra được HAL serialization.
- **Unit test WebMvcLinkBuilder ngoài request context:** dùng MockMvc để cung cấp request context thực tế.
- **Dùng URL hard-code trong assembler:** tạo link từ controller mapping bằng linkTo(methodOn(...)).
- **Self link dùng nhầm ID:** xác nhận href chứa đúng path variable của response.
- **Collection self link trỏ tới item:** phân biệt self link cấp collection và cấp item.
- **Paged self link làm mất filter:** kiểm tra filter, page và size của request hiện tại.
- **Tin forwarded headers không kiểm soát:** cấu hình trusted proxy trước khi dùng host/scheme được forward.
- **Cho rằng self link cấp quyền:** endpoint vẫn phải xác thực và phân quyền ở mỗi request.

## Quy trình kiểm thử self link

1. Xác định resource được kiểm thử là item, collection hay paged collection.
2. Gửi request qua MockMvc với media type hypermedia mà API công bố.
3. Xác minh response status và Content-Type.
4. Kiểm tra relation $._links.self.href ở đúng cấp representation.
5. Xác minh path variable, collection path hoặc query parameters khớp request.
6. Khi cần, gọi lại href để xác nhận link dẫn tới đúng resource.
7. Kiểm thử context path và forwarded headers theo cấu hình triển khai.
8. Giữ unit test cho logic assembler và HTTP test cho URI/serialization.

Self link là một phần của hợp đồng hypermedia mà client dựa vào để nhận diện và truy cập representation hiện tại. Kiểm thử qua MockMvc giúp xác minh link được tạo từ mapping thực tế, serialize đúng trong HAL và tiếp tục hoạt động khi URI, context path hoặc cách triển khai thay đổi.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Building links in Spring MVC: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder
- Spring HATEOAS Reference Documentation, Representation models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models
- Spring Framework Reference Documentation, MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Spring Boot Reference Documentation, Testing Spring MVC applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
