# To-one association

Một đơn hàng thường thuộc về một khách hàng. Khi API trả representation của đơn hàng, client có thể cần điều hướng đến khách hàng đó. Đây là một quan hệ *to-one*: từ một đơn hàng, có tối đa một khách hàng liên quan. Trong Spring HATEOAS, quan hệ này thường được công bố bằng một link có relation như `customer`, trỏ đến item resource của khách hàng.

Điểm quan trọng là quan hệ trong domain model và quan hệ hypermedia giải quyết hai vấn đề khác nhau. Domain model mô tả cardinality và quy tắc nghiệp vụ; hypermedia link mô tả cách client khám phá resource liên quan. Spring HATEOAS không tự suy ra mọi quan hệ JPA để đưa vào response. Ứng dụng cần quyết định quan hệ nào được công bố, relation nào được dùng và người gọi có quyền truy cập đích hay không.

## To-one association là gì?

To-one association là quan hệ mà một đối tượng tham chiếu đến tối đa một đối tượng khác. Trong mô hình dữ liệu, các dạng phổ biến là:

- **Many-to-one:** nhiều đơn hàng có thể tham chiếu cùng một khách hàng; mỗi đơn hàng có tối đa một khách hàng.
- **One-to-one:** một người dùng có tối đa một hồ sơ cá nhân và một hồ sơ thuộc về tối đa một người dùng.

Ví dụ quan hệ đơn hàng – khách hàng:

```text
Order A ───────> Customer 10
Order B ───────> Customer 10
Order C ───────> Customer 24
```

Từ góc nhìn `Order`, `customer` là to-one. Từ góc nhìn `Customer`, `orders` có thể là to-many. Cardinality phụ thuộc hướng đang xét và quy tắc nghiệp vụ.

Trong JPA, quan hệ có thể được mô tả bằng `@ManyToOne` hoặc `@OneToOne`. Những annotation này điều khiển mapping persistence, khóa ngoại, cascade và fetch strategy. Chúng không tự định nghĩa relation hypermedia hoặc URI công khai. Spring HATEOAS xử lý phần representation và link ở tầng API.

## Domain association khác hypermedia link như thế nào?

Giả sử `Order` có thuộc tính `customer` tham chiếu một đối tượng `Customer`. Trong cơ sở dữ liệu, quan hệ có thể được lưu bằng `customer_id`. Client API không nhất thiết phải nhận trường `customerId` để tự tạo URL.

| Domain/persistence | Representation/hypermedia |
| --- | --- |
| `order.getCustomer()` trả đối tượng liên quan. | Link relation `customer` cho biết có resource khách hàng liên quan. |
| `customer_id` là chi tiết lưu trữ hoặc khóa tham chiếu. | `href` là URI công khai để client truy cập resource. |
| `@ManyToOne` hoặc `@OneToOne` mô tả cardinality trong ORM. | Relation `customer` mô tả ý nghĩa liên kết trong hợp đồng API. |
| Fetch strategy quyết định cách ORM tải dữ liệu. | API quyết định link-only hay embed projection. |

Client nên theo `href` được server cung cấp thay vì ghép `/api/customers/` với một ID. Cách này giúp API thay đổi cấu trúc URI mà client vẫn điều hướng qua relation đã công bố.

Không phải mọi association trong domain đều phải xuất hiện trong API. Có quan hệ chỉ phục vụ nội bộ, quan hệ chứa dữ liệu nhạy cảm hoặc quan hệ không có ý nghĩa với client. Chỉ công bố những quan hệ cần thiết cho use case và phù hợp với quyền truy cập.

## Biểu diễn to-one association bằng EntityModel

Giả sử API có DTO cho đơn hàng:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderView(
    UUID id,
    String status,
    BigDecimal total
) {
}
```

Assembler có thể tạo representation của đơn hàng và thêm link đến khách hàng:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
            order.getId(),
            order.getStatus().name(),
            order.getTotal());

        EntityModel<OrderView> model = EntityModel.of(view,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());

        Customer customer = order.getCustomer();
        if (customer != null) {
            model.add(linkTo(methodOn(CustomerController.class)
                .one(customer.getId()))
                .withRel("customer"));
        }

        return model;
    }
}
```

Assembler chuyển domain object thành DTO và công bố hai loại link: `self` cho đơn hàng và `customer` cho association to-one nếu có khách hàng. `methodOn(...)` tham chiếu mapping controller để xây URI; nó không gọi method controller để thực hiện nghiệp vụ.

Ví dụ giả định `Order` có `getCustomer()`, `Customer` có `getId()`, và `CustomerController.one(UUID)` là endpoint đọc khách hàng. Trong ứng dụng thực tế, cần dùng đúng kiểu ID và mapping của dự án.

## HAL biểu diễn association như thế nào?

Khi response dùng HAL (`application/hal+json`), link `customer` xuất hiện trong `_links` của representation đơn hàng:

```json
{
  "id": "ord-1042",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/cus-73"
    }
  }
}
```

Relation `customer` là ngữ nghĩa của association; `href` là địa chỉ resource đích. Client không cần biết khóa ngoại hoặc quy tắc tạo URL nội bộ.

Tên relation nên ổn định, dễ hiểu và nhất quán. Nếu API công khai cho nhiều tổ chức, có thể cân nhắc URI relation được tài liệu hóa để tránh xung đột tên. Không dùng title hoặc tên field Java làm cơ chế nhận diện quan hệ thay cho `rel`.

## Association tùy chọn và association bắt buộc

Một to-one association có thể bắt buộc hoặc tùy chọn. Ví dụ, đơn hàng nháp có thể chưa được gán khách hàng; hoặc một hồ sơ có thể chưa liên kết tài khoản thanh toán.

Nếu association là tùy chọn và hiện không có đối tượng liên quan, không tạo link có `href` rỗng hoặc `null`. Có thể bỏ relation `customer` khỏi `_links`:

```java
Customer customer = order.getCustomer();

if (customer != null) {
    model.add(linkTo(methodOn(CustomerController.class)
        .one(customer.getId())).withRel("customer"));
}
```

Tuy nhiên, việc thiếu link không nhất thiết chứng minh association không tồn tại. Link cũng có thể bị ẩn do chính sách truy cập hoặc do API không công bố quan hệ đó. Nếu client cần phân biệt rõ “chưa gán khách hàng” với “không được phép xem khách hàng”, hãy biểu diễn trạng thái nghiệp vụ phù hợp trong DTO hoặc cung cấp một affordance/quan hệ khác theo hợp đồng. Không làm lộ sự tồn tại của resource nhạy cảm chỉ để giải thích vì sao link bị thiếu.

Nếu association bắt buộc theo nghiệp vụ, hãy bảo đảm invariant ở service/database. Việc không có link trong response không thay thế validation của domain.

## To-one association và embed

Một association to-one có thể được biểu diễn bằng link-only hoặc nhúng một projection nhỏ của resource liên quan.

| Cách biểu diễn | Response | Khi phù hợp |
| --- | --- | --- |
| Link-only | `_links.customer.href` trỏ đến khách hàng | Khách hàng có vòng đời, quyền truy cập hoặc cache độc lập; client có thể không cần dữ liệu khách hàng ngay. |
| Embedded projection | Representation đơn hàng chứa một bản tóm tắt khách hàng theo relation đã công bố | Client thường cần một vài trường khách hàng cùng lúc và dữ liệu có thể xem trong cùng request. |
| Kết hợp embed và link | Có bản tóm tắt cùng link đến canonical customer resource | Client cần hiển thị nhanh nhưng vẫn có thể điều hướng đến resource đầy đủ. |

Không nên nhúng toàn bộ domain entity hoặc toàn bộ graph association. Chỉ đưa các trường mà client cần, tránh vòng lặp `Order -> Customer -> Orders`, payload lớn và lộ thông tin ngoài quyền.

Một object JSON lồng trong DTO không mặc nhiên là embedded resource HAL. Nếu muốn công bố quan hệ hypermedia, hãy xác định relation và cấu trúc representation theo HAL mà ứng dụng hỗ trợ; kiểm thử response đã serialize thay vì chỉ nhìn object Java.

## Biểu diễn quan hệ ngược

Nếu một khách hàng có nhiều đơn hàng, representation khách hàng có thể cung cấp link `orders` đến collection đơn hàng của khách hàng:

```java
Link orders = linkTo(methodOn(OrderController.class)
    .byCustomer(customer.getId()))
    .withRel("orders");
```

Controller có thể ánh xạ collection theo khách hàng:

```java
@GetMapping("/by-customer/{customerId}")
CollectionModel<EntityModel<OrderView>> byCustomer(
        @PathVariable UUID customerId) {
    return orderAssembler.toCollectionModel(
        orderService.findByCustomer(customerId));
}
```

Ví dụ này thể hiện hai chiều điều hướng: từ đơn hàng đến một khách hàng qua `customer`, và từ khách hàng đến tập đơn hàng qua `orders`. Relation ở chiều ngược lại thường trỏ đến collection, không phải một item đơn.

Không nhất thiết phải công bố cả hai chiều. Chỉ thêm link ngược nếu client cần khám phá nó và người gọi có quyền truy cập collection đích.

## Thay đổi một to-one association

Đọc association và thay đổi association là hai khả năng khác nhau. Link `customer` trong representation đơn hàng thường chỉ cho biết khách hàng liên quan. Nếu API cho phép gán hoặc thay khách hàng, hãy công bố thao tác đó riêng bằng một endpoint và affordance thích hợp.

Ví dụ endpoint thay khách hàng của đơn hàng:

```java
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record AssignCustomerRequest(@NotNull UUID customerId) {
}
```

Endpoint:

```java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PutMapping("/{orderId}/customer")
EntityModel<OrderView> assignCustomer(
        @PathVariable UUID orderId,
        @Valid @RequestBody AssignCustomerRequest request) {

    Order updated = orderService.assignCustomer(
        orderId, request.customerId());

    return orderAssembler.toModel(updated);
}
```

`PUT /api/orders/{orderId}/customer` thay thế quan hệ khách hàng tại resource quan hệ này theo hợp đồng API. Nếu endpoint chỉ cập nhật một phần hoặc cần semantics khác, có thể chọn PATCH. Service phải xác minh khách hàng tồn tại, người gọi có quyền gán khách hàng đó và quy tắc nghiệp vụ cho phép thay đổi.

Có thể mô tả thao tác gán bằng affordance:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withSelfRel();

if (order.canChangeCustomer()) {
    self = self.andAffordance(afford(
        methodOn(OrderController.class)
            .assignCustomer(order.getId(), null)));
}
```

`assignCustomer(...)` trong `methodOn` chỉ được tham chiếu để lấy mapping và metadata. Placeholder `null` không gửi request và không thay đổi association. Việc ẩn affordance không phải cơ chế bảo mật; endpoint vẫn phải kiểm tra quyền và invariant khi nhận request thật.

Ví dụ dùng `order.canChangeCustomer()` như một phương thức domain minh họa cho điều kiện thay đổi association; ứng dụng cần triển khai điều kiện này theo trạng thái và chính sách nghiệp vụ thực tế.

## Bảo mật khi công bố to-one link

Một link đến resource liên quan có thể làm lộ thông tin về sự tồn tại của resource hoặc quan hệ giữa hai đối tượng. Trước khi thêm link, cần xem xét:

- Người gọi có quyền đọc resource đích hay không.
- Có được phép biết association này tồn tại hay không.
- ID hoặc URI có tiết lộ thông tin nhạy cảm hay không.
- Embedded projection có chứa field mà người gọi không được xem hay không.
- Endpoint đích có thực hiện authorization độc lập hay chỉ dựa vào việc link đã được công bố.

Không xem link là quyền truy cập. Client có thể gọi URI bằng tay hoặc dùng response cũ. Controller/service của resource đích phải xác thực và phân quyền cho mọi request.

Nếu response được cache, link phụ thuộc user/tenant/role cần cache policy tương ứng. Tránh dùng chung representation chứa link cá nhân hoặc dữ liệu nhúng theo quyền cho nhiều người dùng.

## Hiệu năng và cách tải association

Assembler truy cập `order.getCustomer()` cho từng đơn hàng có thể kích hoạt truy vấn lazy loading. Khi tạo collection lớn, điều này có thể gây N+1 query: một truy vấn lấy danh sách đơn hàng và thêm một truy vấn cho mỗi khách hàng.

Các hướng xử lý phổ biến:

- Dùng fetch join, entity graph hoặc batch fetching khi use case thực sự cần dữ liệu association.
- Dùng projection/query DTO để lấy sẵn ID hoặc các trường cần thiết cho representation.
- Chỉ tạo link từ ID đã có nếu không cần tải toàn bộ entity liên quan.
- Giới hạn collection và phân trang để tránh tạo quá nhiều link trong một response.
- Không gọi service hoặc repository riêng lẻ từ processor/assembler cho từng item nếu có thể chuẩn bị dữ liệu theo batch.

Không chuyển mọi association sang eager fetch chỉ để tạo hypermedia link. Link cần URI và định danh, không nhất thiết cần tải toàn bộ resource đích.

## Kiểm thử to-one association

Kiểm thử nên xác nhận relation đúng, URI trỏ đến đúng item và các trường hợp association tùy chọn được biểu diễn nhất quán.

### Kiểm tra link trong HAL

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href")
        .value(org.hamcrest.Matchers.endsWith(
            "/api/customers/" + customerId)));
```

Test này xác nhận đơn hàng có self link và relation `customer` trỏ đến đúng khách hàng. Nếu host thay đổi theo môi trường, kiểm tra path hoặc cấu hình base URI cố định trong test.

### Kiểm tra association tùy chọn

```java
mockMvc.perform(get("/api/orders/{id}", draftOrderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer").doesNotExist());
```

Test này giả định đơn hàng nháp chưa được gán khách hàng và hợp đồng quy định bỏ relation `customer` khi association null. Nếu API biểu diễn trạng thái chưa gán bằng một field riêng, hãy kiểm tra field đó cùng với link.

### Kiểm tra endpoint đích và quyền

Ngoài việc kiểm tra link được sinh ra, hãy gọi endpoint khách hàng với người dùng được phép và không được phép. Xác nhận server trả status phù hợp và không tiết lộ dữ liệu qua embedded representation hoặc link. Nếu association được thay đổi qua PUT/PATCH, kiểm thử cả trường hợp khách hàng hợp lệ, không tồn tại, người dùng không đủ quyền và vi phạm invariant.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả `customerId` và yêu cầu client tự ghép URL | Client phụ thuộc cấu trúc URI nội bộ. | Công bố relation `customer` với `href` được tạo từ mapping. |
| Nhầm `@ManyToOne` với relation hypermedia | Mapping persistence bị coi là hợp đồng API. | Tạo link tường minh trong assembler hoặc model builder. |
| Tạo link khi association null | Response có `href` rỗng hoặc link không hợp lệ. | Chỉ thêm relation khi có đích hợp lệ. |
| Cho rằng thiếu link nghĩa là không tồn tại association | Client có thể suy luận sai khi link bị ẩn do quyền. | Biểu diễn trạng thái nghiệp vụ rõ ràng nếu cần phân biệt. |
| Nhúng toàn bộ entity liên quan | Payload lớn, vòng lặp và nguy cơ lộ dữ liệu. | Dùng projection nhỏ hoặc link-only resource. |
| Công bố link mà không kiểm tra quyền ở endpoint đích | Client có thể truy cập URI trực tiếp. | Thực hiện authorization độc lập trên mọi endpoint. |
| Tải association lazy cho từng item | Phát sinh N+1 query khi trả collection. | Dùng projection, batch fetching hoặc query phù hợp. |
| Dùng cùng relation cho nhiều ý nghĩa khác nhau | Client không biết resource đích đại diện cho quan hệ nào. | Chọn relation ổn định, có ngữ nghĩa rõ ràng. |

## Ghi nhớ

- To-one association là quan hệ từ một resource đến tối đa một resource khác; ví dụ một đơn hàng có một khách hàng.
- `@ManyToOne` và `@OneToOne` mô tả quan hệ persistence; chúng không tự tạo hypermedia link.
- Dùng `EntityModel` và relation như `customer` để công bố link đến item resource liên quan.
- Client theo `href` thay vì tự ghép URL từ khóa ngoại hoặc ID.
- Với association tùy chọn, chỉ tạo link khi có đích hợp lệ; thiếu link không nhất thiết chứng minh association không tồn tại.
- Chọn link-only, embedded projection hoặc kết hợp dựa trên nhu cầu client, kích thước payload, cache và quyền truy cập.
- Dùng affordance riêng nếu API cho phép thay đổi association; endpoint vẫn phải kiểm tra quyền và invariant.
- Chú ý lazy loading/N+1 khi tạo link cho collection và kiểm thử cả quan hệ tồn tại, null, quyền và URI đích.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
