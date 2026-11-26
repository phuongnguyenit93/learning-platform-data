# Controller tạo quá nhiều link trong Spring HATEOAS

Khi một controller vừa tải dữ liệu, kiểm tra trạng thái nghiệp vụ, kiểm tra quyền, vừa tạo hàng loạt link, nó nhanh chóng trở thành nơi tập trung mọi quyết định của API. Mỗi endpoint lặp lại các lời gọi `linkTo(methodOn(...))`, danh sách relation ngày càng dài và việc thay đổi route buộc phải sửa nhiều controller.

Đây là anti-pattern **controller tạo quá nhiều link**. Vấn đề không phải là một representation có nhiều link theo một con số cố định. Vấn đề xuất hiện khi controller sở hữu toàn bộ logic hypermedia, link bị lặp giữa nhiều endpoint, hoặc response công bố mọi route bất kể client có thể sử dụng chúng hay không.

Spring HATEOAS cung cấp `RepresentationModelAssembler`, `RepresentationModelProcessor` và `WebMvcLinkBuilder` để tổ chức việc tạo link theo trách nhiệm của từng representation. Bài này sử dụng Orders API để nhận diện dấu hiệu, tách link khỏi controller, chọn nơi đặt điều kiện action và kiểm thử hợp đồng HAL sau khi refactor.

## 1. Link là một phần của hợp đồng API

Trong HATEOAS, link cho client biết có thể đi tới tài nguyên nào và quan hệ giữa tài nguyên hiện tại với đích của link là gì. Một link có ít nhất hai thành phần quan trọng:

- `href`: URI hoặc URI template của tài nguyên đích.
- `rel`: ngữ nghĩa của quan hệ giữa tài nguyên hiện tại và đích.

Ví dụ một đơn hàng:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "state": "AWAITING_PAYMENT",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "payment": {
      "href": "https://api.example.com/orders/42/payment"
    }
  }
}
~~~

Client không cần tự ghép `/orders/{id}/payment` từ một quy ước URL. Nó đọc relation `payment` và sử dụng `href` được server công bố.

Các tên `orders` và `payment` trong JSON trên được rút gọn để dễ đọc. Với relation do API tự định nghĩa, contract thực tế nên dùng extension relation URI hoặc CURIE được công bố rõ ràng.

Vì link là một phần của hợp đồng, mỗi relation cần có ý nghĩa rõ ràng và ổn định. Một response có nhiều link nhưng relation mơ hồ sẽ làm client khó hiểu hơn. Một response có ít link nhưng không đủ để client điều hướng tới bước tiếp theo cũng không đáp ứng tốt mục tiêu hypermedia.

## 2. Dấu hiệu controller đang ôm quá nhiều logic link

Một controller bắt đầu phình to khi mỗi method endpoint tự tạo toàn bộ link:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {

        Order order = orderService.findById(id);

        EntityModel<Order> model = EntityModel.of(order);

        model.add(linkTo(methodOn(OrderController.class)
            .one(id)).withSelfRel());

        model.add(linkTo(methodOn(OrderController.class)
            .all()).withRel("orders"));

        model.add(linkTo(methodOn(OrderController.class)
            .cancel(id)).withRel("cancel"));

        model.add(linkTo(methodOn(OrderController.class)
            .changeAddress(id, null)).withRel("changeAddress"));

        model.add(linkTo(methodOn(InvoiceController.class)
            .byOrder(id)).withRel("invoice"));

        model.add(linkTo(methodOn(ShipmentController.class)
            .byOrder(id)).withRel("shipment"));

        model.add(linkTo(methodOn(PaymentController.class)
            .byOrder(id)).withRel("payment"));

        model.add(linkTo(methodOn(OrderHistoryController.class)
            .history(id)).withRel("history"));

        return model;
    }
}
~~~

Đoạn code có thể hoạt động, nhưng controller đang làm nhiều việc cùng lúc:

1. Tải đơn hàng.
2. Chọn payload trả về.
3. Quyết định link nào được hiển thị.
4. Biết route của nhiều controller khác.
5. Đặt tên relation.
6. Tạo từng link và gắn chúng vào model.

Khi endpoint `all()`, `one()` và `search()` cùng trả về đơn hàng, các link chung thường bị sao chép. Khi route của invoice thay đổi, mọi chỗ tạo link tới invoice đều có thể phải sửa. Khi chính sách hủy đơn thay đổi, điều kiện hiển thị link `cancel` có thể bị triển khai khác nhau ở từng controller.

Một controller cũng dễ trở thành nơi thêm link theo kiểu tích lũy: endpoint mới xuất hiện thì thêm một lời gọi `model.add(...)`, dù link đó không phù hợp với mọi trạng thái hoặc mọi representation.

## 3. Không phải cứ nhiều link là sai

Một đơn hàng đang được xử lý có thể có nhiều quan hệ hữu ích: khách hàng, thanh toán, vận chuyển, hóa đơn, lịch sử và collection cha. Số link phụ thuộc vào nghiệp vụ và nhu cầu điều hướng của client.

Hãy đánh giá link theo các câu hỏi sau:

- Client có cần quan hệ này để tiếp tục workflow không?
- Relation có mô tả đúng mục đích của đích link không?
- Link có hợp lệ với trạng thái hiện tại của tài nguyên không?
- Link có được thêm ở một nơi nhất quán không?
- Link có làm lộ thông tin về tài nguyên hoặc action mà client không cần biết không?
- Có link nào trùng relation và trùng đích mà không bổ sung ngữ nghĩa không?

Không đặt một giới hạn cứng như “mỗi resource chỉ được có năm link”. Hãy giảm link dư thừa và relation không rõ nghĩa. Nếu một tài nguyên thực sự có nhiều quan hệ quan trọng, representation có thể công bố chúng một cách có tổ chức.

Cũng cần phân biệt chi phí. Tạo một `Link` bằng `WebMvcLinkBuilder` không tự động chạy truy vấn database. Tuy nhiên, mỗi link được serialize đều làm payload lớn hơn và tăng số relation mà client phải hiểu. Nếu logic tạo link gọi service hoặc repository cho từng item, chi phí truy vấn mới là vấn đề cần xử lý riêng.

## 4. Phân biệt ba loại link

Trước khi tổ chức code, hãy phân loại link mà representation cần cung cấp.

| Loại link | Mục đích | Ví dụ |
|---|---|---|
| Điều hướng | Đi tới tài nguyên có liên quan | `self`, `orders`, `customer`, `invoice` |
| Action | Bắt đầu một thao tác nghiệp vụ | `cancel`, `pay`, `submit`, `approve` |
| Khám phá | Tìm entry point hoặc tài liệu | `search`, `profile`, `describedby` |

Link điều hướng thường gắn với cấu trúc tài nguyên. Link action phụ thuộc trạng thái và quyền thực hiện. Link khám phá giúp client tìm điểm bắt đầu hoặc hiểu contract.

Không đưa tất cả endpoint của controller vào mọi representation chỉ vì chúng tồn tại. Hãy chọn các quan hệ có ý nghĩa trong ngữ cảnh hiện tại.

## 5. Controller nên điều phối request và response

Controller nên tập trung vào ranh giới HTTP:

- Nhận path variable, query parameter và request body.
- Gọi application service để thực hiện use case.
- Chọn HTTP status và header phù hợp.
- Trả representation được assembler xây dựng.

Ví dụ sau khi tách link:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService queryService;
    private final OrderCommandService commandService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderQueryService queryService,
            OrderCommandService commandService,
            OrderModelAssembler assembler) {
        this.queryService = queryService;
        this.commandService = commandService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable Long id) {
        return assembler.toModel(queryService.findView(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return assembler.toCollectionModel(queryService.findViews());
    }

    @PostMapping("/{id}/cancel")
    EntityModel<OrderView> cancel(@PathVariable Long id) {
        OrderView updated = commandService.cancel(id);
        return assembler.toModel(updated);
    }
}
~~~

Controller không cần biết đơn hàng có link invoice, shipment hay payment. Nó chỉ cần biết use case nào cần thực hiện và representation nào cần trả về.

Đừng chuyển logic nghiệp vụ sang assembler chỉ để làm controller ngắn hơn. Điều kiện cho phép hủy đơn thuộc domain/application policy. Assembler sử dụng kết quả chính sách đó để quyết định có công bố action link hay không.

## 6. Dùng RepresentationModelAssembler cho một loại representation

Spring HATEOAS cung cấp `RepresentationModelAssembler<T, D>` để chuyển một domain object hoặc read model thành `RepresentationModel`. Interface có `toModel()` và phương thức mặc định `toCollectionModel()` để chuyển một tập phần tử thành `CollectionModel`.

Đối với Orders API, tạo một view model chỉ chứa dữ liệu cần trả về:

~~~java
public record OrderView(
    Long id,
    String number,
    OrderState state,
    Long shipmentId,
    boolean invoiceAvailable
) {}
~~~

Assembler chịu trách nhiệm tạo model và link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    private static final LinkRelation ORDERS_REL =
        LinkRelation.of("https://api.example.com/rels/orders");

    private static final LinkRelation CANCEL_REL =
        LinkRelation.of("https://api.example.com/rels/order-cancellation");

    private static final LinkRelation INVOICE_REL =
        LinkRelation.of("https://api.example.com/rels/order-invoice");

    private final OrderActionPolicy actionPolicy;

    OrderModelAssembler(OrderActionPolicy actionPolicy) {
        this.actionPolicy = actionPolicy;
    }

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {

        Long id = order.id();
        EntityModel<OrderView> model = EntityModel.of(order);

        model.add(linkTo(
            methodOn(OrderController.class).one(id)
        ).withSelfRel());

        model.add(linkTo(OrderController.class).withRel(ORDERS_REL));

        if (actionPolicy.canCancel(order)) {
            model.add(linkTo(
                methodOn(OrderController.class).cancel(id)
            ).withRel(CANCEL_REL));
        }

        if (order.invoiceAvailable()) {
            model.add(linkTo(
                methodOn(InvoiceController.class).byOrder(id)
            ).withRel(INVOICE_REL));
        }

        return model;
    }

    @Override
    public CollectionModel<EntityModel<OrderView>> toCollectionModel(
            Iterable<? extends OrderView> orders) {

        CollectionModel<EntityModel<OrderView>> collection =
            RepresentationModelAssembler.super.toCollectionModel(orders);

        collection.add(linkTo(OrderController.class).withSelfRel());

        return collection;
    }
}
~~~

Ở đây, assembler có một phạm vi rõ ràng: tạo representation cho Order. Nó chịu trách nhiệm cho `self`, link về collection và các action hoặc quan hệ trực tiếp của Order.

`toCollectionModel()` tái sử dụng `toModel()` cho từng phần tử rồi thêm link cho collection. Khi endpoint danh sách và endpoint chi tiết cùng cần cách biểu diễn một đơn hàng, chúng dùng chung assembler thay vì chép lại link list.

Nếu ứng dụng dùng `RepresentationModelAssemblerSupport`, có thể tận dụng helper tạo model và self link. Tuy nhiên, không cần kế thừa lớp support chỉ để giảm vài dòng code. Interface `RepresentationModelAssembler` thường đủ cho một assembler thông thường.

## 7. Dùng methodOn và linkTo thay cho URL hard-code

Không nên tạo link bằng chuỗi URL rải rác:

~~~java
model.add(Link.of("/orders/" + id).withSelfRel());
model.add(Link.of("/orders/" + id + "/cancel").withRel("cancel"));
~~~

Khi mapping thay đổi, các chuỗi này có thể bị bỏ sót. Cách xây dựng URI cũng dễ bỏ qua context path hoặc host hiện tại.

Với Spring MVC, `WebMvcLinkBuilder` cung cấp `linkTo(...)` và `methodOn(...)`:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(id)
).withSelfRel();

Link cancel = linkTo(
    methodOn(OrderController.class).cancel(id)
).withRel(CANCEL_REL);
~~~

`methodOn(...)` tạo controller proxy để ghi nhận method mapping cần tham chiếu. Nó không gọi method controller thật và không thực thi use case hủy đơn. `linkTo(...)` dùng mapping của controller và method để tạo URI.

Điều này giúp link đi theo mapping đã khai báo bằng `@RequestMapping`, `@GetMapping`, `@PostMapping` và `@PathVariable`. Khi route thay đổi, code tham chiếu method có thể tiếp tục tạo đúng URI sau khi ứng dụng được cập nhật.

`methodOn(...)` ghi nhận lời gọi trên proxy; nó không chạy method controller. Các tham số chỉ tham gia URI theo mapping và annotation tương ứng, đặc biệt là `@PathVariable`. Với query parameter hoặc URI template phức tạp, hãy khai báo rõ `@RequestParam` và kiểm tra URI được tạo. `WebMvcLinkBuilder` dành cho Spring MVC; ứng dụng WebFlux dùng API link builder reactive tương ứng.

Không nên gọi trực tiếp method controller như một Java method thông thường để lấy dữ liệu rồi dùng kết quả làm link. Hãy sử dụng proxy của `methodOn(...)` theo đúng mục đích xây URI.

## 8. Tách điều kiện action khỏi thao tác tạo link

Một lỗi phổ biến là viết điều kiện nghiệp vụ trực tiếp vào nhiều controller:

~~~java
if (order.getState() == OrderState.NEW
        || order.getState() == OrderState.PENDING) {
    model.add(cancelLink);
}
~~~

Nếu cùng một quy tắc xuất hiện ở nhiều endpoint, các bản sao có thể lệch nhau khi workflow thay đổi.

Hãy đưa quyết định action vào policy dùng chung:

~~~java
@Component
class OrderActionPolicy {

    private final CurrentActor currentActor;

    OrderActionPolicy(CurrentActor currentActor) {
        this.currentActor = currentActor;
    }

    boolean canCancel(OrderView order) {
        boolean stateAllowsCancellation =
            order.state() == OrderState.NEW
                || order.state() == OrderState.PENDING;

        return stateAllowsCancellation
            && currentActor.hasAuthority("order:cancel");
    }
}
~~~

Assembler chỉ hỏi policy:

~~~java
if (actionPolicy.canCancel(order)) {
    model.add(linkTo(
        methodOn(OrderController.class).cancel(order.id())
    ).withRel(CANCEL_REL));
}
~~~

Policy cần dựa trên trạng thái nghiệp vụ và thông tin quyền của actor hiện tại. Nếu kiểm tra quyền phải truy cập database hoặc dịch vụ từ xa, tránh gọi một lần cho từng model trong collection. Hãy tải hoặc tính quyền theo tập ID, hoặc tạo một capability map cho cả trang trước khi chạy assembler.

Việc ẩn link không thay thế authorization. Endpoint `POST /orders/{id}/cancel` vẫn phải kiểm tra quyền và trạng thái ngay khi nhận request. Client có thể lưu một link cũ hoặc tự tạo request, nên server luôn phải xác thực action ở phía xử lý lệnh.

## 9. Không công bố tất cả action trong mọi trạng thái

Một controller có thể khai báo các endpoint `cancel`, `pay`, `ship`, `deliver`, `refund` và `close`. Điều đó không có nghĩa mọi đơn hàng đều nên chứa tất cả link này.

Ví dụ:

| Trạng thái đơn hàng | Action phù hợp |
|---|---|
| `NEW` | `submit`, `cancel` |
| `AWAITING_PAYMENT` | `pay`, `cancel` nếu chính sách cho phép |
| `PAID` | `ship`, `cancel` nếu chưa xử lý giao hàng |
| `SHIPPED` | `track`, `confirm-delivery` |
| `DELIVERED` | `request-return`, `download-invoice` |
| `CANCELLED` | Có thể chỉ còn `self`, `orders`, `history` |

Bảng chỉ minh họa workflow. Quy tắc thực tế phụ thuộc domain và quyền của người gọi.

Một representation có action link theo trạng thái giúp client biết bước tiếp theo hợp lệ. Client không cần tự mã hóa toàn bộ state machine bằng cách suy luận từ tên enum. Tuy nhiên, trạng thái trong body vẫn có ích cho hiển thị, báo cáo và logic riêng của giao diện.

Đừng thêm action link chỉ để “phòng khi cần”. Nếu thao tác chưa khả dụng, không công bố link action đó. Nếu thao tác chỉ khả dụng cho một vai trò, chính sách link nên tính đến actor hiện tại.

## 10. Chọn relation có ngữ nghĩa ổn định

Các relation như `self`, `next`, `prev`, `edit` có semantics đã được đăng ký trong IANA Link Relation Registry. Nếu một relation chuẩn mô tả đúng quan hệ, hãy ưu tiên dùng nó.

Đối với quan hệ riêng của ứng dụng như hủy đơn hoặc hóa đơn đơn hàng, nên định nghĩa extension relation bằng URI ổn định:

~~~java
private static final LinkRelation CANCEL_REL =
    LinkRelation.of("https://api.example.com/rels/order-cancellation");

private static final LinkRelation INVOICE_REL =
    LinkRelation.of("https://api.example.com/rels/order-invoice");
~~~

Tránh những relation mơ hồ như `link1`, `action`, `data`, `related2` hoặc `button`. Client cần hiểu quan hệ và mục đích của link mà không phải dựa vào vị trí của nó trong JSON.

Tài liệu relation nên giải thích:

- Relation trỏ tới loại tài nguyên hoặc action nào.
- Khi nào server công bố relation.
- Method và media type liên quan nếu đây là action.
- Dữ liệu đầu vào cần thiết.
- Kết quả và lỗi có thể xảy ra.
- Quy tắc authorization và trạng thái nghiệp vụ.

Nếu muốn biểu diễn extension relation ngắn trong HAL, có thể cấu hình CURIE để client tra cứu URI relation. Dù dùng tên ngắn hay URI đầy đủ, semantics phải ổn định qua các lần đổi route.

## 11. Tách link dùng chung thành component khi thật sự có tái sử dụng

Có những link xuất hiện trên nhiều loại representation, ví dụ link tới trang hỗ trợ, tài liệu API hoặc collection gốc. Nếu nhiều assembler cùng xây một link theo cùng quy tắc, có thể tạo một collaborator nhỏ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.stereotype.Component;

@Component
class ApiNavigationLinks {

    Link orders() {
        return linkTo(OrderController.class)
            .withRel(LinkRelation.of(
                "https://api.example.com/rels/orders"
            ));
    }

    Link documentation() {
        return Link.of(
            "https://api.example.com/docs",
            IanaLinkRelations.DESCRIBED_BY
        );
    }
}
~~~

Assembler có thể dùng component này:

~~~java
model.add(apiNavigationLinks.orders());
model.add(apiNavigationLinks.documentation());
~~~

Chỉ tách khi có nhiều nơi thực sự dùng chung một quy tắc. Nếu một link chỉ xuất hiện trong một assembler, giữ nó ở assembler đó thường dễ hiểu hơn.

Không tạo một `LinkFactory` tổng quát với hàng chục method cho từng link nhỏ nếu các method chỉ chuyển tiếp một dòng `linkTo(...)`. Abstraction nên gom một quy tắc có ý nghĩa, chẳng hạn link entry point, relation catalog hoặc policy tạo link theo loại resource.

## 12. Dùng RepresentationModelProcessor cho link thuộc module khác

Đôi khi Order representation cần một link do module khác sở hữu. Ví dụ Payment module muốn thêm link thanh toán vào Order khi trạng thái đang chờ thanh toán. Nếu thêm chi tiết `PaymentController` vào mọi Order controller và assembler, module Order sẽ bị phụ thuộc vào cấu trúc route của Payment.

`RepresentationModelProcessor` có thể bổ sung link sau khi representation đã được assembler tạo:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class PaymentLinkProcessor
        implements RepresentationModelProcessor<EntityModel<OrderView>> {

    private static final LinkRelation PAYMENT_REL =
        LinkRelation.of("https://api.example.com/rels/order-payment");

    @Override
    public EntityModel<OrderView> process(EntityModel<OrderView> model) {

        OrderView order = model.getContent();

        if (order != null
                && order.state() == OrderState.AWAITING_PAYMENT) {

            model.add(linkTo(
                methodOn(PaymentController.class).byOrder(order.id())
            ).withRel(PAYMENT_REL));
        }

        return model;
    }
}
~~~

Processor phù hợp khi một thành phần độc lập cần bổ sung một nhóm link theo kiểu representation. Nó giúp tránh đưa mọi controller liên quan vào assembler của resource gốc.

Hãy chỉ định một nơi sở hữu mỗi relation. Nếu assembler đã thêm payment relation, processor không nên thêm lại cùng relation và href.

Không dùng processor như nơi gom tất cả link của toàn hệ thống. Nếu mỗi processor thêm nhiều relation không liên quan, model sẽ lại trở nên khó dự đoán. Mỗi processor nên có một phạm vi rõ ràng, chẳng hạn payment links hoặc support links.

Processor nên xử lý dữ liệu đã có trên model và tạo URI. Không gọi repository cho từng model trong `process()`, vì processor có thể được áp dụng trên nhiều response và làm phát sinh N+1.

Với `CollectionModel` rỗng, Spring HATEOAS không phải lúc nào cũng suy ra được payload type do Java type erasure. Nếu processor cần chạy trên collection rỗng, hãy khai báo fallback payload type bằng `withFallbackType(...)` hoặc tạo collection với type tường minh.

## 13. Chia assembler khi representation có nhiều vùng trách nhiệm

Nếu một Order representation thực sự cần nhiều nhóm link, hãy phân chia theo quan hệ nghiệp vụ:

- `OrderModelAssembler`: self, collection, action của đơn hàng.
- `ShipmentModelAssembler` hoặc shipment link contributor: quan hệ vận chuyển.
- `PaymentLinkProcessor`: quan hệ thanh toán thuộc module Payment.
- `InvoiceLinkContributor`: quan hệ hóa đơn nếu có quy tắc riêng.

Có thể tạo collaborator nhận model và dữ liệu cần thiết:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderShipmentLinks {

    void addLinks(EntityModel<OrderView> model, OrderView order) {
        if (order.shipmentId() == null) {
            return;
        }

        model.add(linkTo(
            methodOn(ShipmentController.class)
                .one(order.shipmentId())
        ).withRel(
            LinkRelation.of(
                "https://api.example.com/rels/order-shipment"
            )
        ));
    }
}
~~~

Assembler điều phối các contributor:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    private final OrderActionPolicy actionPolicy;
    private final OrderShipmentLinks shipmentLinks;

    OrderModelAssembler(
            OrderActionPolicy actionPolicy,
            OrderShipmentLinks shipmentLinks) {
        this.actionPolicy = actionPolicy;
        this.shipmentLinks = shipmentLinks;
    }

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        EntityModel<OrderView> model = EntityModel.of(order);

        model.add(linkTo(
            methodOn(OrderController.class).one(order.id())
        ).withSelfRel());

        if (actionPolicy.canCancel(order)) {
            model.add(linkTo(
                methodOn(OrderController.class).cancel(order.id())
            ).withRel(
                LinkRelation.of(
                    "https://api.example.com/rels/order-cancellation"
                )
            ));
        }

        shipmentLinks.addLinks(model, order);
        return model;
    }
}
~~~

Đây là lựa chọn khi các nhóm link có logic riêng hoặc được tái sử dụng. Nếu chỉ có một vài link đơn giản, giữ code trong assembler sẽ dễ đọc hơn. Không cần chia nhỏ chỉ vì assembler dài thêm vài dòng.

## 14. Dùng affordance khi link cần mô tả cách thực hiện action

Một HAL link thông thường cho biết relation và URI đích. Nó không tự mô tả đầy đủ HTTP method, request body hay input schema.

Nếu client cần biết một action sử dụng `POST`, `PUT` hay `PATCH`, hoặc cần biết cấu trúc payload, hãy cân nhắc affordance và media type hỗ trợ metadata như HAL-FORMS.

Ví dụ gắn affordance vào self link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(order.id())
).withSelfRel()
 .andAffordance(afford(
    methodOn(OrderController.class).cancel(order.id())
));
~~~

Controller method `cancel` cần khai báo mapping HTTP tương ứng và kiểu input/output phù hợp. Spring HATEOAS phân tích controller method để tạo metadata affordance cho media type hỗ trợ.

Không thêm nhiều action link rồi mong client tự đoán method và body từ relation. Hãy dùng affordance khi contract cần mô tả tương tác, đồng thời giữ relation có ngữ nghĩa ổn định.

## 15. Không dùng link ẩn để thay thế kiểm soát truy cập

Một lỗi thiết kế là nghĩ rằng không trả link `cancel` thì client không thể hủy đơn. Client có thể giữ link cũ, gọi trực tiếp URI đã biết hoặc gửi request thủ công.

Vì vậy:

- Assembler chỉ quyết định action nào nên được khám phá trong representation hiện tại.
- Application service và security layer kiểm tra quyền khi request thực sự tới.
- Domain layer kiểm tra trạng thái có cho phép chuyển tiếp hay không.
- Endpoint trả lỗi phù hợp nếu action không còn hợp lệ.

Link visibility cải thiện trải nghiệm điều hướng và giúp client tránh đưa ra thao tác không phù hợp. Nó không phải cơ chế authorization.

Cũng tránh đưa link tới tài nguyên nhạy cảm chỉ vì người dùng có thể nhìn thấy Order. Mỗi relation cần được xem xét theo quyền đọc và quyền thực hiện action.

## 16. Tránh link generation gây truy vấn theo từng phần tử

Một assembler có thể tạo nhiều link mà không phát sinh SQL nếu chỉ dựa trên ID và controller mapping. Nhưng nếu nó gọi repository để kiểm tra mỗi quan hệ, query count sẽ tăng theo số phần tử.

Ví dụ không nên làm:

~~~java
for (OrderView order : orders) {
    boolean hasShipment =
        shipmentRepository.existsByOrderId(order.id());

    if (hasShipment) {
        // Add shipment link.
    }
}
~~~

Với 50 đơn hàng, đoạn code có thể tạo 50 truy vấn kiểm tra shipment.

Hãy tải thông tin cần thiết theo tập ID:

~~~java
Set<Long> orderIds = orders.stream()
    .map(OrderView::id)
    .collect(Collectors.toSet());

Set<Long> ordersWithShipment =
    shipmentQueryService.findOrderIdsWithShipment(orderIds);
~~~

Sau đó assembler hoặc link contributor dùng tập ID đã có:

~~~java
if (ordersWithShipment.contains(order.id())) {
    model.add(shipmentLink(order.id()));
}
~~~

Cùng nguyên tắc này áp dụng cho permission, invoice availability và payment status. Tạo link không nên là lý do để chạy thêm một truy vấn cho từng item.

## 17. Kiểm thử relation thay vì đếm số dòng code tạo link

Một refactor có thể làm controller ngắn hơn nhưng vô tình làm mất relation hoặc thêm link sai trạng thái. Kiểm thử nên tập trung vào hợp đồng representation.

### Unit test cho assembler

~~~java
@Test
void exposesCancellationOnlyWhenPolicyAllowsIt() {

    OrderView order = new OrderView(
        42L,
        "ORD-0042",
        OrderState.NEW,
        null,
        false
    );

    EntityModel<OrderView> model = assembler.toModel(order);

    assertThat(model.getLinks().hasLink(IanaLinkRelations.SELF)).isTrue();
    assertThat(model.getLinks().hasLink(
        LinkRelation.of(
            "https://api.example.com/rels/order-cancellation"
        )
    )).isTrue();
}
~~~

Một test khác kiểm tra trạng thái không cho hủy:

~~~java
@Test
void hidesCancellationForDeliveredOrder() {

    OrderView order = new OrderView(
        42L,
        "ORD-0042",
        OrderState.DELIVERED,
        501L,
        true
    );

    EntityModel<OrderView> model = assembler.toModel(order);

    assertThat(model.getLinks().hasLink(IanaLinkRelations.SELF)).isTrue();
    assertThat(model.getLinks().hasLink(
        LinkRelation.of(
            "https://api.example.com/rels/order-cancellation"
        )
    )).isFalse();
}
~~~

Các test này kiểm tra quan hệ và điều kiện nghiệp vụ. Chúng không phụ thuộc vào số dòng `model.add(...)` trong implementation.

### MockMvc contract test

Kiểm tra response HAL ở cấp HTTP để bảo đảm serialization giữ đúng relation:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/order-cancellation'].href"
    ).exists());
~~~

Với đơn hàng đã giao, xác nhận relation hủy đơn không xuất hiện:

~~~java
mockMvc.perform(
        get("/orders/43")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/order-cancellation']"
    ).doesNotExist());
~~~

Trong test thực tế, hãy chuẩn bị fixture có trạng thái và actor phù hợp. Nếu custom relation được rút gọn bằng CURIE, JSONPath cần dùng đúng tên relation mà serializer tạo ra.

### Kiểm tra link thực sự điều hướng được

Ngoài việc kiểm tra `href`, có thể đọc link từ response rồi gọi URI đó trong integration test. Điều này phát hiện trường hợp assembler tạo đúng chuỗi URI nhưng route không tồn tại hoặc mapping đã đổi.

Không nên kiểm tra bằng cách ghép URL thủ công trong test. Hãy lấy `href` từ relation trong representation rồi gọi theo đúng URI mà server công bố.

## 18. Các anti-pattern liên quan

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Mỗi controller tự tạo toàn bộ link | Logic trùng lặp, khó đổi route | Dùng assembler theo representation |
| Một assembler khổng lồ cho mọi resource | Khó kiểm thử và khó phân chia trách nhiệm | Tách theo resource hoặc nhóm quan hệ |
| Tạo link cho mọi endpoint | Payload và contract nhiễu | Chọn relation hữu ích trong ngữ cảnh |
| Luôn công bố action bất kể trạng thái | Client thử thao tác không hợp lệ | Dùng action policy |
| Dùng relation `action`, `link1` | Client không hiểu semantics | Dùng IANA relation hoặc extension URI |
| Hard-code URL trong controller | Mapping và URL dễ lệch nhau | Dùng `WebMvcLinkBuilder` |
| Gọi repository trong assembler/processor | N+1 khi dựng collection | Tải dữ liệu theo tập ID |
| Dùng link visibility như authorization | Request cũ hoặc giả mạo vẫn có thể gọi endpoint | Kiểm tra quyền tại endpoint |
| Processor thêm link không có phạm vi | Relation bị lặp hoặc xuất hiện sai model | Giới hạn theo kiểu representation và trách nhiệm |
| Dùng HAL link để mô tả request body | Client phải tự đoán input | Dùng affordance hoặc HAL-FORMS |

## 19. Quy trình refactor controller tạo quá nhiều link

Khi gặp controller có nhiều lời gọi `model.add(...)`, hãy thực hiện theo thứ tự:

1. Liệt kê relation hiện tại và phân loại thành navigation, action hoặc discovery.
2. Xác định relation nào thực sự cần cho từng representation.
3. Kiểm tra relation trùng lặp, tên mơ hồ và link không hợp lệ theo trạng thái.
4. Đưa mapping entity/read model sang `RepresentationModelAssembler`.
5. Đưa điều kiện action vào domain/application policy.
6. Dùng `WebMvcLinkBuilder` và `methodOn` để tham chiếu mapping controller.
7. Tạo collaborator nhỏ khi một nhóm link có quy tắc dùng chung.
8. Dùng `RepresentationModelProcessor` cho link cross-cutting thuộc module khác.
9. Tải trước dữ liệu và quyền theo tập ID nếu cần để tránh query per item.
10. Giữ controller tập trung vào request, use case và HTTP response.
11. Kiểm thử relation, href, điều kiện hiển thị và khả năng theo link.
12. Tài liệu hóa extension relation để client có thể sử dụng lâu dài.

Controller tạo quá nhiều link là dấu hiệu trách nhiệm hypermedia đang đặt sai chỗ hoặc representation đang công bố quá nhiều quan hệ thiếu ngữ nghĩa. Hãy để controller điều phối HTTP, assembler tạo representation theo resource, policy quyết định action có sẵn và processor bổ sung các quan hệ cross-cutting có phạm vi rõ ràng. Khi relation được chọn theo nhu cầu điều hướng, link được xây từ mapping và contract được kiểm thử, API dễ tiến hóa hơn mà client vẫn khám phá được các bước tiếp theo.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [Spring HATEOAS Reference — Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-assembler)
- [Spring HATEOAS Reference — Representation Model Processors](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.model-processors)
- [Spring HATEOAS Reference — Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS API — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring HATEOAS API — RepresentationModelProcessor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html)
- [Spring HATEOAS API — WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [IANA — Link Relation Types](https://www.iana.org/assignments/link-relations/)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
