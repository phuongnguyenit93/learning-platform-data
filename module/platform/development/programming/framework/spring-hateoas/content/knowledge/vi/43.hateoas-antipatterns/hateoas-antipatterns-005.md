# Payload trộn sai tầng trong Spring HATEOAS

Một API HATEOAS dễ trở nên khó bảo trì khi một object phải đại diện cùng lúc cho dữ liệu nghiệp vụ, entity persistence, trạng thái giao diện, link HTTP, metadata pagination và thông tin điều khiển. Ban đầu cách làm này có vẻ tiện vì controller chỉ cần trả một DTO duy nhất. Nhưng theo thời gian, thay đổi database có thể làm đổi JSON, đổi route buộc phải sửa domain model, link bị serialize thành field nghiệp vụ và client không phân biệt được dữ liệu với khả năng điều hướng.

Trong Spring HATEOAS, representation có thể chứa cả dữ liệu và hypermedia controls, nhưng hai phần đó cần được đặt đúng cấu trúc và tạo ở đúng tầng. Dữ liệu resource mô tả trạng thái nghiệp vụ được công bố; link mô tả quan hệ và nơi client có thể điều hướng; affordance mô tả hành động có thể khám phá; HTTP headers mô tả metadata của giao thức. Bài này phân tích các dạng payload trộn sai tầng, cách tách domain/application/representation/HTTP concerns và cách kiểm thử để giữ contract rõ ràng.

## 1. Hiểu các tầng trước khi thiết kế payload

Một request thường đi qua nhiều tầng:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Controller]
    B --> C[Application use case]
    C --> D[Domain model]
    C --> E[Repository]
    E --> C
    C --> F[Response DTO]
    F --> G[HATEOAS assembler]
    G --> H[EntityModel / CollectionModel / PagedModel]
    H --> I[HTTP message converter]
    I --> J[HAL JSON response]
~~~

Mỗi tầng có một trách nhiệm:

| Tầng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain | Quy tắc và trạng thái nghiệp vụ độc lập với HTTP. | Order, OrderStatus, cancel(). |
| Application | Điều phối use case, quyền, transaction và truy xuất dữ liệu. | CancelOrderUseCase, FindOrdersQuery. |
| Persistence | Lưu và truy vấn dữ liệu. | JPA entity, repository, projection. |
| Representation | Chọn dữ liệu công khai cho API. | OrderSummary, OrderDetail. |
| Hypermedia | Tạo relation, link và affordance theo context. | self, customer, cancel, next. |
| HTTP | Status, headers, content negotiation và serialization. | 200, ETag, Cache-Control, application/hal+json. |

Một class có thể tham gia nhiều cơ chế framework, nhưng contract cần giữ ranh giới rõ. Domain không nên phụ thuộc vào URI hoặc Spring HATEOAS; representation không nên vô tình phơi bày entity graph; assembler không nên trở thành nơi chạy business workflow; controller không nên tự ghép chuỗi JSON.

## 2. Payload là gì và hypermedia controls là gì?

Với HAL, một resource representation thường có ba nhóm:

- Dữ liệu resource: các field mô tả trạng thái được công bố, ví dụ id, status, total.
- Links: các relation trong _links, ví dụ self, customer, cancel.
- Embedded resources: representation liên quan được nhúng trong _embedded.

Paged representation còn có metadata pagination ở cấp collection, ví dụ size, totalElements, totalPages và number. HTTP headers như Content-Type, ETag và Cache-Control thuộc tầng giao thức.

Ví dụ một representation có ranh giới rõ:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": { "href": "/api/orders/o-42" },
    "customer": { "href": "/api/customers/c-7" },
    "cancel": { "href": "/api/orders/o-42/cancel" }
  }
}
~~~

Các field id, status và total là dữ liệu resource. Các relation trong _links là hypermedia controls. Link cancel có thể chỉ xuất hiện khi đơn hàng đang ở trạng thái cho phép hủy và người gọi có quyền. Sự vắng mặt của link là một phần semantics của representation.

## 3. Anti-pattern: serialize trực tiếp JPA entity

Một cách làm dễ gặp là controller trả entity:

~~~java
@GetMapping("/{id}")
Order get(@PathVariable UUID id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Entity được thiết kế để persistence và domain behavior, không phải để trở thành public API schema. Khi Jackson serialize entity, các association có thể bị tải lazy, vòng tham chiếu hai chiều có thể gây lỗi hoặc buộc phải thêm annotation serialization, và field nội bộ có thể bị lộ.

Ví dụ entity có các field tenantId, internalNote, paymentProviderReference hoặc audit metadata. Client không nhất thiết được phép nhìn thấy các field này. Thay đổi quan hệ JPA cũng có thể làm JSON thay đổi dù API contract không hề được chủ động cập nhật.

Hãy chuyển entity thành DTO/representation có chủ đích:

~~~java
public record OrderDetail(
        UUID id,
        String orderNumber,
        OrderStatus status,
        BigDecimal total
) {}
~~~

Application query trả DTO hoặc projection đã chọn field. HATEOAS assembler nhận DTO rồi thêm link. Nhờ đó persistence mapping có thể thay đổi mà contract HTTP vẫn ổn định.

## 4. Anti-pattern: đặt URL vào DTO nghiệp vụ

Một DTO trộn tầng thường trông như sau:

~~~java
public record OrderResponse(
        UUID id,
        String status,
        BigDecimal total,
        String selfUrl,
        String customerUrl,
        String cancelUrl,
        String nextPageUrl
) {}
~~~

Các field selfUrl, customerUrl và cancelUrl không phải dữ liệu nghiệp vụ của đơn hàng. Chúng phụ thuộc vào route, context path, host, proxy, version và policy của request. Nếu lưu hoặc truyền chúng qua application service, tầng nghiệp vụ bắt đầu biết chi tiết HTTP.

Trong HAL, các URL nên được biểu diễn bằng relation trong _links. Page navigation thuộc collection model, không thuộc từng OrderResponse. Nếu API chủ động chọn một JSON media type riêng với field url, đó phải là contract có chủ đích và được tài liệu hóa; không nên trộn ngẫu nhiên URL vào DTO chỉ vì cần trả link.

## 5. Anti-pattern: đưa Spring HATEOAS Link vào domain entity

Không nên thêm field Link hoặc WebMvcLinkBuilder vào domain object:

~~~java
class Order {
    private UUID id;
    private Link selfLink;
    private Link cancelLink;
}
~~~

Domain model cần biểu diễn quy tắc nghiệp vụ và trạng thái. URI phụ thuộc HTTP adapter và có thể thay đổi theo request context. Khi domain import Spring HATEOAS, unit test domain phải kéo theo framework web và logic nghiệp vụ khó tái sử dụng ở batch job, message consumer hoặc ứng dụng khác.

Giữ domain thuần:

~~~java
class Order {
    private UUID id;
    private OrderStatus status;

    boolean canBeCancelled() {
        return status == OrderStatus.PENDING;
    }
}
~~~

Application layer xác định use case và quyền. Adapter HATEOAS dùng kết quả đó để quyết định có thêm relation cancel hay không. Không lưu Link vào entity hoặc database.

## 6. Anti-pattern: trộn dữ liệu resource với trạng thái giao diện

Một response có thể chứa các field như isSelected, isExpanded, currentTab hoặc buttonColor. Đây thường là trạng thái của một màn hình cụ thể, không phải trạng thái resource trên server.

Nếu API là backend cho một UI duy nhất, một số presentation hint có thể có chủ đích. Nhưng khi xây API hypermedia dùng cho nhiều consumer, các field giao diện thường làm contract phụ thuộc vào layout hoặc framework frontend. Client khác có thể không hiểu chúng.

Chỉ đưa field vào representation khi nó mô tả dữ liệu hoặc semantics công khai mà consumer có thể sử dụng. Nếu một hành động khả dụng, hãy công bố relation/affordance phù hợp; đừng trả buttonLabel, buttonColor và isButtonEnabled để mô phỏng một giao diện cụ thể.

## 7. Anti-pattern: đặt pagination metadata trong từng item

Không đặt totalPages, currentPage, nextPageUrl hoặc hasNext vào mọi order trong collection. Đây là metadata của collection result, không phải thuộc tính của từng đơn hàng.

Ví dụ sai:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PENDING",
        "currentPage": 0,
        "totalPages": 13,
        "nextPageUrl": "/api/orders?page=1"
      }
    ]
  }
}
~~~

Mỗi item bị lặp metadata giống nhau và có thể tạo mâu thuẫn nếu một item được tái sử dụng trong response khác. PagedModel đặt metadata và navigation links ở cấp collection:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PENDING",
        "_links": {
          "self": { "href": "/api/orders/o-42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders?page=0&size=20" },
    "next": { "href": "/api/orders?page=1&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 245,
    "totalPages": 13,
    "number": 0
  }
}
~~~

## 8. Anti-pattern: trộn action input với resource state

Một resource representation mô tả trạng thái hiện tại. Request command mô tả ý định thay đổi trạng thái. Nếu DTO response chứa sẵn các field chỉ dùng để submit hành động, client có thể hiểu nhầm chúng là dữ liệu resource.

Ví dụ response sai:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "cancelReasonInput": "",
  "refundAmountInput": 0,
  "approveButtonEnabled": true
}
~~~

Input cho action nên được mô tả bằng affordance hoặc form representation nếu API hỗ trợ. Với HAL-FORMS, template có thể chỉ ra method, target, content type và properties:

~~~json
{
  "_links": {
    "cancel": { "href": "/api/orders/o-42/cancel" }
  },
  "_templates": {
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "type": "text",
          "required": true
        }
      ]
    }
  }
}
~~~

Trong ví dụ này, link relation cancel cung cấp target URI; template cancel mô tả method, content type và các property cần gửi tới target đó. Tài liệu cần nói rõ cách ghép template với link tương ứng theo contract HAL-FORMS mà API công bố.

Nếu không dùng HAL-FORMS, tài liệu hóa request body của action và công bố link relation tới endpoint. Dù có affordance, server vẫn phải validate input và kiểm tra quyền khi action được thực thi.

## 9. Anti-pattern: trộn HTTP metadata vào JSON payload

Content-Type, ETag, Cache-Control, Location, Retry-After và status code là metadata của HTTP. Không nên lặp chúng thành các field tùy tiện trong business payload như responseStatus, contentType, cachePolicy hoặc etagValue nếu không có nhu cầu contract rõ ràng.

Ví dụ response không cần:

~~~json
{
  "responseStatus": 200,
  "contentType": "application/hal+json",
  "etagValue": "\"orders-v42\"",
  "cachePolicy": "private",
  "data": {
    "id": "o-42",
    "status": "PENDING"
  }
}
~~~

HTTP response đã có status line và headers:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "orders-v42"
Cache-Control: private, max-age=30
~~~

Body tập trung vào representation. Nếu API dùng envelope JSON riêng và cố ý phản ánh một số metadata, cần định nghĩa vì sao thông tin đó không thể hoặc không nên nằm ở HTTP layer. Không sao chép headers vào body theo thói quen.

## 10. Anti-pattern: dùng một wrapper chung cho mọi response

Một số API tạo wrapper cố định:

~~~json
{
  "success": true,
  "message": "OK",
  "data": {},
  "links": {},
  "pagination": {},
  "errors": []
}
~~~

Sau đó response detail, collection, validation error và authentication error đều bị ép vào cùng cấu trúc. Điều này dễ tạo nhiều field rỗng, status trùng với HTTP, links không theo semantics HAL và client phải kiểm tra success trước khi đọc mọi dữ liệu.

Không phải mọi envelope đều sai. Một media type riêng có thể định nghĩa envelope có chủ đích. Anti-pattern xuất hiện khi wrapper chung làm mất semantics HTTP, lặp lại thông tin và không phân biệt resource representation với Problem Details. Với HAL, dùng EntityModel, CollectionModel hoặc PagedModel; với lỗi, dùng ProblemDetail/application-problem+json nếu contract chọn RFC 9457.

## 11. Anti-pattern: trộn error fields vào success resource

Không trả một resource thành công có field errorMessage, validationErrors hoặc exceptionClass chỉ để tránh dùng HTTP error response. Điều này làm client khó phân biệt request thành công với request thất bại và khiến schema success chứa các field chỉ xuất hiện khi lỗi.

Ví dụ không nên:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "error": true,
  "errorCode": "ORDER_ALREADY_SHIPPED",
  "errorMessage": "Cannot cancel"
}
~~~

Khi thao tác thất bại, trả HTTP status phù hợp và Problem Details riêng:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Cannot cancel a shipped order",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

Client có thể dùng type hoặc code để phân loại. Không phân tích title/detail làm khóa logic.

## 12. Anti-pattern: nhúng relation như dữ liệu nghiệp vụ

Một association có thể được biểu diễn bằng link hoặc embedded resource. Không nên biến URI association thành field customerUrl trong domain DTO, cũng không nên nhét object customer đầy đủ vào mọi response mà không cân nhắc kích thước và quyền.

Chọn cách biểu diễn theo use case:

| Cách | Khi phù hợp |
| --- | --- |
| Association link | Client cần khám phá hoặc tải customer khi cần. |
| Embedded customer | Client thường xuyên cần một phần thông tin customer trong cùng response. |
| Summary field như customerName | Client chỉ cần một giá trị hiển thị, không cần điều hướng tới customer. |

Nếu dùng summary field, đừng gọi nó là embedded customer. Nếu dùng embedded relation, mô tả payload và relation name rõ ràng. Nếu chỉ có link, client phải theo href để lấy resource liên quan.

## 13. Anti-pattern: trùng lặp dữ liệu ở nhiều tầng

Payload có thể lặp cùng một dữ liệu dưới nhiều tên:

~~~json
{
  "status": "PENDING",
  "orderStatus": "PENDING",
  "state": "PENDING",
  "isPending": true
}
~~~

Những field này có thể lệch nhau khi một mapper cập nhật mà mapper khác quên sửa. Hãy chọn một biểu diễn canonical cho trạng thái. Nếu cần derived property, chỉ thêm khi có semantics riêng và tài liệu hóa cách tính.

Tương tự, không lặp cùng một href vừa ở field selfUrl vừa trong _links.self.href. Client có thể đọc hai giá trị khác nhau khi route thay đổi. Một relation có một nguồn công bố chính thức.

## 14. Thiết kế DTO riêng cho từng use case

Không nhất thiết phải có một DTO duy nhất cho mọi endpoint. Collection summary và detail representation có nhu cầu khác nhau:

~~~java
public record OrderSummary(
        UUID id,
        String orderNumber,
        OrderStatus status,
        BigDecimal total
) {}

public record OrderDetail(
        UUID id,
        String orderNumber,
        OrderStatus status,
        BigDecimal total,
        Instant createdAt,
        String shippingAddress
) {}
~~~

Summary chỉ chứa field cần cho collection; detail chứa thông tin cần ở trang chi tiết. Cả hai có thể được bọc trong EntityModel và dùng assembler tương ứng. Đừng nhồi mọi field có thể có vào một DTO rồi để từng controller bỏ bớt bằng annotation hoặc null.

DTO khác nhau không có nghĩa resource bị phân mảnh tùy tiện. Mỗi representation phải có semantics rõ và relation để client chuyển từ summary sang detail.

## 15. Tách application result khỏi hypermedia assembly

Application use case nên trả dữ liệu hoặc kết quả nghiệp vụ, không trả JSON đã gắn URL:

~~~java
public record FindOrderResult(
        OrderDetail order,
        boolean canCancel
) {}
~~~

Ví dụ canCancel là context để adapter quyết định công bố action. Không nhất thiết serialize boolean này thành field public. Adapter có thể dùng nó để thêm hoặc bỏ relation:

~~~java
EntityModel<OrderDetail> toModel(FindOrderResult result) {
    OrderDetail order = result.order();

    EntityModel<OrderDetail> model = EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class)
                    .one(order.id()))
                    .withSelfRel()
    );

    if (result.canCancel()) {
        model.add(linkTo(methodOn(OrderController.class)
                .cancel(order.id(), null))
                .withRel("cancel"));
    }

    return model;
}
~~~

Đây là minh họa cho ranh giới: application result mang dữ liệu và kết quả policy; assembler chuyển kết quả thành representation. Trong hệ thống lớn, có thể tách policy decision khỏi query và batch load để tránh một lần kiểm tra quyền cho mỗi item.

## 16. Dùng RepresentationModelAssembler đúng vai trò

Assembler nhận model dữ liệu và tạo representation:

~~~java
@Component
class OrderSummaryAssembler implements
        RepresentationModelAssembler<OrderSummary,
                EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(OrderSummary order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id()))
                        .withSelfRel()
        );
    }
}
~~~

Assembler không nên:

- Truy cập repository để tải lại cùng entity.
- Chạy transaction nghiệp vụ.
- Gọi remote service cho từng item.
- Đọc hoặc ghi database.
- Nhét URL vào DTO rồi serialize như field dữ liệu.
- Tự quyết định quyền chỉ dựa trên thông tin client gửi.

Hãy chuẩn bị dữ liệu cần thiết ở application/query layer. Assembler tập trung tạo links và representation từ context đã có.

## 17. Đặt page metadata ở collection model

Với Spring HATEOAS, PagedResourcesAssembler có thể chuyển Spring Data Page thành PagedModel:

~~~java
@GetMapping
PagedModel<EntityModel<OrderSummary>> list(
        Pageable pageable,
        PagedResourcesAssembler<OrderSummary> pagedAssembler) {

    Page<OrderSummary> page = orderQueryService.findPage(pageable);
    return pagedAssembler.toModel(page, orderSummaryAssembler);
}
~~~

Controller trả về một model phân trang. Assembler tạo representation cho từng item; paged assembler tạo metadata và links ở cấp collection. Không tự thêm nextPageUrl vào từng item và không sao chép page metadata vào từng DTO.

Nếu API chỉ cần next/prev mà không cần total count, cân nhắc Slice hoặc cursor model. Chọn model theo semantics mà client cần, không thêm totalPages giả tạo để giữ một wrapper cố định.

## 18. Đặt HTTP headers ở HTTP response

Controller hoặc filter có thể đặt headers mà không thêm chúng vào resource payload:

~~~java
return ResponseEntity.ok()
        .contentType(MediaTypes.HAL_JSON)
        .eTag(etag)
        .cacheControl(CacheControl.cachePrivate()
                .maxAge(Duration.ofSeconds(30)))
        .body(orderModel);
~~~

Ví dụ này minh họa vị trí của HTTP metadata. ETag và Cache-Control thuộc response headers; HAL model vẫn mô tả resource và hypermedia. Nếu dùng conditional GET, status 304 và validator được xử lý ở tầng HTTP.

Không trả field cacheControl trong OrderDetail chỉ để client biết chính sách cache. Client đọc Cache-Control từ headers theo HTTP semantics.

## 19. Chọn đúng media type cho success và error

Một API có thể dùng:

| Media type | Dùng cho |
| --- | --- |
| application/hal+json | Resource, collection và paged hypermedia representation. |
| application/problem+json | Lỗi theo RFC 9457 Problem Details. |
| application/json | JSON không có HAL controls nếu API thực sự hỗ trợ contract đó. |
| application/prs.hal-forms+json | HAL-FORMS representation nếu ứng dụng cấu hình và công bố media type này. |

Không đặt _links vào một body application/json rồi giả định mọi client hiểu đó là HAL. Cũng không ép ProblemDetail thành HAL bằng cách thêm một field links không được định nghĩa. Nếu muốn error representation dùng HAL, hãy định nghĩa media type và schema riêng, hoặc dùng Link headers với Problem Details.

## 20. Kiểm soát serialization và Jackson annotations

Jackson annotations hữu ích cho representation DTO, nhưng không nên dùng chúng để che việc domain entity bị trả trực tiếp. Các annotation như JsonIgnore, JsonManagedReference và JsonBackReference có thể tránh một số vòng tham chiếu, nhưng không thay thế ranh giới DTO.

Ví dụ:

~~~java
public record OrderDetail(
        UUID id,
        String status,
        BigDecimal total
) {}
~~~

DTO chỉ có field được phép công bố, vì vậy serializer không cần hiểu entity relationship. Hypermedia links được Spring HATEOAS serializer xử lý theo media type HAL. Tránh tự tạo field _links trong DTO rồi đồng thời để assembler thêm một bộ links khác.

## 21. Xử lý nested resources đúng cách

Nếu một order có customer và items, hãy xác định consumer cần gì:

- Nếu chỉ cần customer name trong danh sách, có thể đưa customerName vào summary DTO.
- Nếu client cần mở customer resource, công bố relation customer.
- Nếu client cần customer snapshot cùng response, nhúng customer representation vào _embedded.customer.
- Nếu items là collection lớn, công bố link tới items collection và pagination riêng.

Không tạo một object customer vừa có field dữ liệu, vừa có customerUrl, vừa có links lồng tự chế nếu API đã dùng HAL. Chọn một hình thức rõ ràng cho từng association và áp dụng nhất quán.

## 22. Kiểm thử để phát hiện payload trộn sai tầng

Contract tests có thể phát hiện các field ngoài ý muốn:

~~~java
mockMvc.perform(get("/api/orders/o-42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").exists())
    .andExpect(jsonPath("$.status").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$.selfUrl").doesNotExist())
    .andExpect(jsonPath("$.cancelUrl").doesNotExist())
    .andExpect(jsonPath("$.tenantId").doesNotExist())
    .andExpect(jsonPath("$.internalNote").doesNotExist());
~~~

Test này khóa cả sự hiện diện của field contract và sự vắng mặt của field không được công bố. Trong dự án thực tế, không cần liệt kê mọi field nội bộ; tập trung vào các field nhạy cảm hoặc những tên từng gây nhầm lẫn giữa payload và controls.

## 23. Kiểm thử page metadata và action links đúng cấp

Với collection, xác nhận page metadata ở cấp ngoài cùng và không lặp trong item:

~~~java
mockMvc.perform(get("/api/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0].currentPage").doesNotExist())
    .andExpect(jsonPath("$._embedded.orders[0].nextPageUrl").doesNotExist());
~~~

Kiểm thử action theo trạng thái:

~~~java
mockMvc.perform(get("/api/orders/o-42")
        .with(user("buyer-7").roles("CUSTOMER"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());

mockMvc.perform(get("/api/orders/o-99")
        .with(user("buyer-7").roles("CUSTOMER"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Hai fixture cần có trạng thái nghiệp vụ và quyền khác nhau. Không giả định một role luôn đủ để hủy mọi order; policy phải xét cả resource state và ownership nếu contract yêu cầu.

## 24. Kiểm thử ranh giới giữa domain và web adapter

Domain unit test nên chạy mà không cần Spring MVC hoặc Spring HATEOAS. Có thể xác nhận business rule:

~~~java
@Test
void shippedOrderCannotBeCancelled() {
    Order order = Order.shipped(UUID.randomUUID());

    assertThat(order.canBeCancelled()).isFalse();
}
~~~

Web/assembler test xác nhận kết quả policy được phản ánh thành link phù hợp. Sự phân chia này giúp phân biệt lỗi nghiệp vụ với lỗi tạo hypermedia. Nếu domain test phải khởi tạo WebMvcLinkBuilder hoặc mock HTTP request để chạy, có thể domain model đã phụ thuộc sai tầng.

## 25. Lộ trình refactor payload đang trộn sai tầng

Khi API đã có client sử dụng, không nên đổi toàn bộ JSON trong một bước mà không đánh giá compatibility. Có thể refactor theo các bước:

1. Lập danh sách field hiện tại và phân loại: domain data, presentation-only, link, pagination, HTTP metadata, error.
2. Xác định field nào client thực sự dùng và field nào bị trùng lặp.
3. Tạo DTO riêng cho collection/detail và giữ mapping từ entity.
4. Chuyển URL fields sang HAL relations, giữ link semantics tương đương.
5. Chuyển page fields về collection-level PagedModel.
6. Chuyển error fields sang Problem Details hoặc error contract đã công bố.
7. Chuyển headers như ETag và Cache-Control về HTTP layer.
8. Thêm contract tests cho relation mới và response cũ trong giai đoạn chuyển đổi.
9. Công bố deprecation/migration nếu client cần thời gian chuyển.
10. Loại bỏ field cũ sau khi hết thời hạn hỗ trợ đã cam kết.

Nếu phải duy trì tương thích, có thể thêm relation mới trước, cập nhật client theo href, sau đó deprecate URL field cũ. Không để cả hai nguồn tồn tại mãi mà không chỉ ra nguồn nào là canonical.

## 26. Các lỗi thường gặp

**Trả trực tiếp JPA entity.** Dùng DTO/representation model để kiểm soát field công khai và tránh lazy loading ngoài ý muốn.

**Đưa selfUrl/cancelUrl vào business DTO.** Công bố link bằng relation trong _links.

**Lưu Spring HATEOAS Link trong domain entity.** Tạo link ở adapter sau khi application layer trả kết quả.

**Đặt nextPageUrl trong từng item.** Đưa pagination links và metadata vào collection model.

**Đưa form input vào resource state.** Mô tả input bằng affordance/HAL-FORMS hoặc request schema của action.

**Đưa status/ETag/cache policy vào JSON body.** Dùng HTTP status và headers.

**Dùng một success/error wrapper cho mọi tình huống.** Giữ success representation và Problem Details đúng media type.

**Nhúng mọi association.** Chọn summary, link hoặc embedded resource theo use case.

**Assembler tự truy vấn hoặc gọi remote service.** Chuẩn bị dữ liệu ở query/application layer và batch load khi cần.

**Tạo field trùng nhau cho cùng một khái niệm.** Chọn một tên canonical và kiểm thử contract.

## 27. Bài tập thực hành và tiêu chí hoàn thành

Hãy refactor một endpoint đơn hàng đang trả payload chứa cả dữ liệu, URL và metadata:

1. Liệt kê các field của response cũ và phân loại theo tầng.
2. Tạo OrderSummary và OrderDetail DTO không chứa URL hoặc HTTP metadata.
3. Chuyển entity sang DTO bằng query projection hoặc mapper phù hợp.
4. Tạo RepresentationModelAssembler để thêm self và association links.
5. Chỉ công bố cancel link khi business state và authorization policy cho phép.
6. Chuyển pagination metadata và next/prev links sang PagedModel.
7. Đưa ETag, Cache-Control và Content-Type về HTTP response headers.
8. Dùng ProblemDetail cho lỗi nghiệp vụ theo contract đã chọn.
9. Kiểm thử field không được công bố, relation bắt buộc và relation tùy chọn.
10. Xác nhận domain unit test không phụ thuộc Spring HATEOAS.
11. Đánh giá compatibility và viết migration/deprecation plan nếu payload cũ đã có consumer.

Bạn đã nắm được cách tránh payload trộn sai tầng khi có thể phân biệt dữ liệu nghiệp vụ, DTO công khai, hypermedia controls, collection metadata và HTTP metadata; tạo links ở adapter; giữ assembler tập trung vào representation; và kiểm thử contract để phát hiện field URL, field giao diện hoặc field nội bộ lọt vào response. Một payload rõ ràng giúp client hiểu resource và điều hướng qua relation mà không buộc domain model phụ thuộc vào HTTP.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS – Assembling links to controllers](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.methods)
- [Spring Data JPA – Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
