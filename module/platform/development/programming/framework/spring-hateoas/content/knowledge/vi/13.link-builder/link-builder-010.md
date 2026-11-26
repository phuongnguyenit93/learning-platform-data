# Kiểm thử link builder

Link builder của Spring HATEOAS tạo URI và relation cho các liên kết trong representation. Một link có thể nhìn đúng trong mã nguồn nhưng vẫn sai khi chạy: mapping controller có thể thay đổi, path variable có thể bị đặt sai, query parameter có thể bị mất hoặc URI tuyệt đối có thể chứa host không phù hợp với môi trường triển khai. Vì vậy, kiểm thử link builder cần xác nhận những liên kết thực sự xuất hiện trong HTTP response.

Với Spring MVC, cách kiểm tra đáng tin cậy là dùng `MockMvc` để gọi endpoint và kiểm tra response hypermedia. Có thể bổ sung unit test cho assembler để xác nhận relation và điều kiện tạo link. Hai lớp kiểm thử này giúp phát hiện lỗi ở cả logic biểu diễn lẫn quá trình tạo URI theo mapping.

## Những gì cần kiểm thử

Một link thường chứa relation (`rel`) và URI đích (`href`). Với Spring HATEOAS, kiểm thử nên tập trung vào các thuộc tính sau:

| Thành phần | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Relation | Link mang đúng quan hệ | `self`, `customer`, `cancel` |
| Path | URI phản ánh mapping controller | `/api/orders/{id}` |
| Path variable | Giá trị định danh được truyền đúng | ID của đơn hàng hiện tại |
| Query parameter | Bộ lọc, sắp xếp và phân trang được giữ đúng | `status`, `page`, `size` |
| Media type | Response được tuần tự hóa đúng định dạng hypermedia | `application/hal+json` |
| Điều kiện nghiệp vụ | Link chỉ xuất hiện khi hành động được công bố | `cancel` chỉ có ở đơn hàng đang chờ xử lý |
| URI môi trường | Scheme, host, context path và proxy được xử lý đúng | `https://api.example.com/...` |

Không nên chỉ kiểm tra một chuỗi URL đầy đủ cố định trong mọi test. Host, port và context path có thể khác nhau giữa máy phát triển, CI và môi trường triển khai. Thông thường nên kiểm tra relation, path và query parameter; chỉ kiểm tra scheme/host khi đó là một phần cụ thể của cấu hình cần bảo vệ.

## Chuẩn bị endpoint và assembler mẫu

Giả sử API có endpoint đọc một đơn hàng và endpoint tìm kiếm đơn hàng:

```java
import java.util.UUID;
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        Order order = service.findRequired(id);
        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderResponse>> search(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size
    ) {
        List<EntityModel<OrderResponse>> orders = service.search(status, page, size)
                .stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
                orders,
                linkTo(methodOn(OrderController.class)
                        .search(status, page, size)).withSelfRel()
        );
    }
}
```

Assembler dùng `WebMvcLinkBuilder` để tạo link dựa trên mapping controller:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        UUID id = order.getId();
        OrderResponse content = new OrderResponse(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        EntityModel<OrderResponse> model = EntityModel.of(
                content,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Trong ví dụ, `one(...)` và `cancel(...)` là các phương thức controller được assembler tham chiếu. `methodOn(...)` tạo tham chiếu để Spring HATEOAS đọc mapping và tham số; nó không thực thi logic nghiệp vụ của endpoint. Các kiểu `Order`, `OrderResponse`, service và phần còn lại của controller là thành phần ứng dụng.

## Kiểm thử integration bằng MockMvc

`MockMvc` chạy request qua Spring MVC trong test context. Vì link builder được đánh giá trong ngữ cảnh request và mapping thực tế, cách này kiểm tra được cả URI được tạo lẫn response serialization.

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.junit.jupiter.api.Test;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLinkBuilderTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void detailResponseContainsCorrectSelfLink() throws Exception {
        UUID orderId = UUID.fromString("8a31f7a0-45a1-4a8c-9d9e-3b28e5f16d10");

        mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(orderId.toString()))
            .andExpect(jsonPath("$._links.self.href",
                    endsWith("/api/orders/" + orderId)));
    }
}
```

Test xác nhận response dùng HAL JSON, nội dung mang đúng ID và self link trỏ tới path của endpoint đọc đơn hàng. Matcher `endsWith(...)` tránh phụ thuộc host và port do môi trường test cung cấp.

Nếu ứng dụng dùng context path, chẳng hạn `/store`, hãy điều chỉnh matcher để kiểm tra path có context path đó. Khi context path là cấu hình cần bảo vệ, có thể kiểm tra chính xác phần path sau khi phân tích URI thay vì cố định toàn bộ absolute URL.

## Kiểm thử link có path variable

Path variable phải được đưa vào đúng vị trí của URI. Một test có thể kiểm tra `self` và một link liên quan:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href",
            endsWith("/api/orders/" + orderId)))
    .andExpect(jsonPath("$._links.customer.href",
            endsWith("/api/customers/" + customerId)));
```

Test này phù hợp khi assembler tạo link `customer` từ ID khách hàng của đơn hàng. Nếu URI chứa ký tự cần mã hóa, hãy kiểm tra URI đã được encode đúng theo quy tắc URI thay vì so sánh một chuỗi chưa mã hóa. Dùng `URI` để đọc path/query sẽ giúp test phân biệt cấu trúc URI với cách biểu diễn ký tự.

## Kiểm thử query parameter

Với endpoint tìm kiếm, link `self` cần phản ánh các tham số xác định kết quả. Ví dụ request:

```http
GET /api/orders?status=PENDING&page=0&size=20
Accept: application/hal+json
```

Kiểm thử bằng MockMvc:

```java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").value(
            allOf(
                    containsString("status=PENDING"),
                    containsString("page=0"),
                    containsString("size=20")
            )));
```

Nếu assembler tạo link qua `methodOn(OrderController.class).search(status, page, size)`, test này xác nhận các tham số được phản ánh vào URI. Với query value chứa dấu cách, dấu `&`, dấu `+` hoặc ký tự Unicode, nên phân tích query string sau khi parse URI và kiểm tra giá trị đã decode. Không nên giả định mọi ký tự đặc biệt đều xuất hiện dưới dạng văn bản thô trong `href`.

## Kiểm thử relation và điều kiện xuất hiện

Link builder tạo URI, còn assembler thường quyết định link nào được thêm vào model. Kiểm thử response cần xác nhận cả relation lẫn điều kiện nghiệp vụ.

Với đơn hàng đang chờ xử lý:

```java
mockMvc.perform(get("/api/orders/{id}", pendingOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với đơn hàng đã giao:

```java
mockMvc.perform(get("/api/orders/{id}", deliveredOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Hai test bảo vệ hợp đồng hypermedia: relation `cancel` xuất hiện khi thao tác được công bố và vắng mặt khi trạng thái không còn cho phép. Endpoint `cancel` vẫn phải kiểm tra quyền và trạng thái khi nhận request; sự tồn tại của link không phải cơ chế phân quyền.

## Kiểm thử link builder trong assembler

Có thể viết unit test cho assembler để xác nhận relation được thêm vào model theo trạng thái. Ví dụ, dùng một đối tượng miền dựng sẵn:

```java
import java.math.BigDecimal;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@BeforeEach
void bindRequestContext() {
    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/orders");
    request.setScheme("http");
    request.setServerName("localhost");
    request.setServerPort(8080);
    RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
}

@AfterEach
void clearRequestContext() {
    RequestContextHolder.resetRequestAttributes();
}

@Test
void assemblerAddsCancelLinkForPendingOrder() {
    Order order = new Order(
            orderId,
            OrderStatus.PENDING,
            new BigDecimal("1250000")
    );

    EntityModel<OrderResponse> model = assembler.toModel(order);

    assertTrue(model.hasLink(IanaLinkRelations.SELF));
    assertTrue(model.hasLink("cancel"));
}

@Test
void assemblerOmitsCancelLinkForShippedOrder() {
    Order order = new Order(
            orderId,
            OrderStatus.SHIPPED,
            new BigDecimal("1250000")
    );

    EntityModel<OrderResponse> model = assembler.toModel(order);

    assertTrue(model.hasLink(IanaLinkRelations.SELF));
    assertFalse(model.hasLink("cancel"));
}
```

Trong test class, `assembler` và `orderId` được khởi tạo trước. `RequestContextHolder` được gắn với mock servlet request để `WebMvcLinkBuilder` có thông tin tạo URI; `@AfterEach` xóa context nhằm tránh rò rỉ trạng thái sang test khác. Unit test này kiểm tra logic tạo model và link relation. Để xác nhận URI cuối cùng phản ánh đúng mapping và serialization, vẫn cần ít nhất một test MVC như phần trước.

Nếu assembler gọi `WebMvcLinkBuilder` ngoài request context, cách thiết lập request context trong unit test có thể phụ thuộc phiên bản Spring và cấu hình MVC. Khi mục tiêu là kiểm tra URI cuối cùng, `MockMvc` thường đơn giản và gần với hành vi chạy thực tế hơn.

## Kiểm thử link phân trang

Khi dùng `PagedResourcesAssembler`, cần xác nhận các link điều hướng phù hợp với trang hiện tại. Ở trang đầu, thường có `self`, `next` và `last`; trang giữa có thể có `prev` và `next`; trang cuối có thể có `prev` và `first`.

Ví dụ kiểm tra trang đầu:

```java
mockMvc.perform(get("/api/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$.page.number").value(0));
```

Điều kiện xuất hiện link phụ thuộc tổng số trang và vị trí trang. Hãy tạo dữ liệu test đủ số phần tử để có nhiều trang; nếu chỉ có một trang thì `next` và `last` có thể không xuất hiện. Kiểm tra thêm trang cuối để bảo đảm link `next` không được công bố khi không còn trang tiếp theo.

## Kiểm thử URI khi có context path hoặc reverse proxy

Trong triển khai, ứng dụng có thể chạy dưới context path hoặc sau reverse proxy. Link được tạo từ request cần phản ánh URI công khai mà client sử dụng.

Với cấu hình proxy, hãy kiểm tra các tình huống:

- Scheme công khai là `https` dù kết nối proxy tới ứng dụng nội bộ dùng HTTP.
- Host và port trong link là địa chỉ công khai đã cấu hình.
- Context path hoặc prefix do gateway quản lý được giữ đúng.
- Header `Forwarded` hoặc `X-Forwarded-*` chỉ được tin khi request đến từ proxy đáng tin cậy.

Có thể gửi forwarded headers trong MockMvc nếu ứng dụng đã cấu hình `ForwardedHeaderFilter` hoặc cơ chế xử lý forwarded headers tương ứng. Test cần phản ánh cấu hình triển khai thực tế; việc chỉ thêm header vào request test không tự bật xử lý forwarded headers trong ứng dụng.

## Kiểm thử link có thể theo được

Một link đúng định dạng vẫn có thể trỏ tới endpoint không tồn tại. Có thể viết kiểm thử hai bước: gọi endpoint nguồn, đọc `href`, sau đó gọi URI đích bằng request test.

```java
import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult result = mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String href = JsonPath.read(
        result.getResponse().getContentAsString(),
        "$._links.self.href"
);

URI selfUri = URI.create(href);
String pathAndQuery = selfUri.getRawPath();
if (selfUri.getRawQuery() != null) {
    pathAndQuery += "?" + selfUri.getRawQuery();
}

mockMvc.perform(get(pathAndQuery).accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
```

Đoạn mã minh họa cho self link có host thuộc test server. Nếu URI chứa context path, cần bảo đảm request MockMvc được gửi với context path tương ứng. Với link trỏ sang hệ thống ngoài, không gọi mạng trong unit test; hãy kiểm tra relation, URI và hợp đồng của đích theo test phù hợp.

## Các lỗi thường gặp khi kiểm thử link builder

| Lỗi | Vì sao chưa đủ | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra response có `_links` | Không biết relation và URI có đúng không | Kiểm tra từng `rel` và `href` quan trọng |
| So sánh toàn bộ absolute URL | Test dễ hỏng do host/port khác môi trường | Phân tích URI và kiểm tra path/query; kiểm tra host khi cần |
| Chỉ unit test assembler | Không xác nhận mapping và serialization HTTP | Bổ sung MockMvc integration test |
| Chỉ test trang đầu với một trang dữ liệu | Không kiểm tra được `next` và `last` | Chuẩn bị nhiều trang và test đầu/giữa/cuối |
| Bỏ qua query encoding | Ký tự đặc biệt có thể làm link sai | Parse URI và kiểm tra query đã decode |
| Gửi forwarded header nhưng app không xử lý | Kết quả test không phản ánh proxy | Cấu hình filter/strategy trước khi kiểm thử |
| Chỉ kiểm tra link tồn tại | Link có thể trỏ tới endpoint sai | Theo link trong test nội bộ hoặc xác nhận route đích |

## Checklist kiểm thử link builder

1. Xác nhận relation của các link bắt buộc như `self` và các link nghiệp vụ.
2. Xác nhận path được tạo từ mapping controller và đúng path variable.
3. Xác nhận query parameter được giữ và encode đúng.
4. Xác nhận media type hypermedia và cấu trúc `_links`.
5. Kiểm tra link có điều kiện theo trạng thái nghiệp vụ.
6. Kiểm tra link phân trang ở trang đầu, giữa và cuối.
7. Kiểm tra context path, scheme và host khi ứng dụng có proxy hoặc gateway.
8. Xác nhận các link nội bộ quan trọng dẫn tới endpoint hoạt động.

## Kết luận

Kiểm thử link builder cần xác nhận relation, URI, query parameter và điều kiện xuất hiện của từng liên kết trong response. Unit test giúp kiểm tra logic assembler; MockMvc xác nhận mapping controller, request context và HAL serialization. Khi kiểm tra thêm phân trang, context path và forwarded headers theo cấu hình thực tế, nhóm phát triển có thể phát hiện sớm lỗi điều hướng và giữ hợp đồng hypermedia ổn định khi API thay đổi.
