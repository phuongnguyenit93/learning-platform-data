# Lazy link generation

## Mục tiêu

Khi một API trả về collection có nhiều phần tử, mỗi representation có thể cần self link và một số action links. Nếu assembler luôn tạo tất cả links trước khi quyết định có đưa chúng vào response hay không, server vẫn phải trả chi phí tạo proxy, phân tích mapping, dựng URI và cấp phát object cho những links cuối cùng bị bỏ đi.

Spring HATEOAS hỗ trợ tạo links có điều kiện bằng RepresentationModel.addIf(...) và addAllIf(...). Hai phương thức nhận Supplier, nhờ đó chỉ gọi logic tạo link khi điều kiện đúng. Đây là cách trì hoãn phần công việc không cần thiết trong quá trình lắp ráp representation.

Sau bài học, bạn có thể:

- Nhận diện chi phí tạo link trong collection và representation có nhiều affordances.
- Dùng addIf(...) để tạo một link khi cần.
- Dùng addAllIf(...) để tạo một nhóm links khi cần.
- Kết hợp Supplier với MvcLink để trì hoãn controller invocation.
- Phân biệt lazy link generation với việc trì hoãn serialize response.
- Dùng EntityLinks và assembler support để giảm code tạo link lặp lại.
- Đo hiệu năng trước và sau tối ưu mà vẫn giữ đúng hợp đồng hypermedia.

## Vì sao cần lazy link generation?

Một link được tạo từ controller mapping thường cần nhiều bước: tạo proxy invocation, đọc mapping, ghép path variable và query parameters, tạo URI, rồi tạo đối tượng Link. Một bước riêng lẻ có thể nhỏ, nhưng chi phí nhân lên khi một response chứa hàng trăm item và mỗi item có nhiều links.

Ví dụ một collection 200 đơn hàng, mỗi đơn hàng có self, customer, invoice, cancel, approve và reject. Nếu assembler tạo đủ sáu links cho mọi item, server có thể dựng 1.200 links dù phần lớn đơn hàng không có invoice hoặc không cho phép cancel, approve, reject.

Lazy link generation cho phép quyết định trước xem link có cần xuất hiện không. Khi điều kiện sai, supplier không được gọi và phần việc tạo link không xảy ra.

~~~mermaid
flowchart TD
    A[Nhận domain object] --> B[Tạo representation cơ bản]
    B --> C{Điều kiện công bố link?}
    C -- Không --> D[Bỏ qua Supplier]
    C -- Có --> E[Gọi Supplier]
    E --> F[Tạo Link từ mapping]
    F --> G[Thêm Link vào model]
    D --> H[Trả representation]
    G --> H
~~~

Điều này đặc biệt hữu ích với action links phụ thuộc trạng thái, quyền, feature flag hoặc dữ liệu liên quan chỉ có ở một số trường hợp.

## addIf: chỉ tạo một link khi cần

RepresentationModel.addIf(boolean, Supplier<Link>) nhận một điều kiện và một supplier tạo link. Khi điều kiện là false, supplier không được gọi. Khi điều kiện là true, Spring HATEOAS gọi supplier và thêm link trả về vào model.

Ví dụ, đơn hàng chỉ có thể bị hủy khi còn ở trạng thái PENDING và người dùng có quyền tương ứng:

~~~java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

class OrderModelAssembler {

    private final OrderLinkPolicy linkPolicy;

    OrderModelAssembler(OrderLinkPolicy linkPolicy) {
        this.linkPolicy = linkPolicy;
    }

    EntityModel<OrderResponse> toModel(
            Order order,
            CurrentUser currentUser) {

        OrderResponse response = OrderResponse.from(order);
        EntityModel<OrderResponse> model = EntityModel.of(response);

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.id()))
                .withSelfRel());

        boolean canCancel = linkPolicy.canCancel(currentUser, order);

        model.addIf(canCancel, () ->
                linkTo(methodOn(OrderController.class)
                        .cancel(order.id()))
                        .withRel("cancel"));

        return model;
    }
}
~~~

Self link luôn được tạo vì mọi item đều cần nó. Cancel link chỉ được tạo khi canCancel là true. Khi điều kiện sai, Spring HATEOAS không thực hiện lời gọi linkTo(methodOn(...)) nằm trong supplier.

Hãy tính điều kiện một lần rồi truyền vào addIf. Không đặt lời gọi policy tốn kém vào nhiều biểu thức hoặc bên trong supplier nếu điều kiện đã có thể được xác định trước. Supplier nên tập trung vào việc tạo link.

## addAllIf: tạo một nhóm links khi cần

Khi một nhóm links cùng phụ thuộc vào một điều kiện, dùng addAllIf(boolean, Supplier<? extends Iterable<Link>>). Supplier chỉ được gọi khi guard đúng; khi được gọi, nó tạo danh sách links và Spring HATEOAS thêm tất cả vào model.

~~~java
import java.util.List;

import org.springframework.hateoas.Link;

boolean canManage = orderPolicy.canManage(currentUser, order);

model.addAllIf(canManage, () -> List.of(
        linkTo(methodOn(OrderController.class)
                .approve(order.id()))
                .withRel("approve"),
        linkTo(methodOn(OrderController.class)
                .reject(order.id()))
                .withRel("reject"),
        linkTo(methodOn(OrderController.class)
                .assign(order.id()))
                .withRel("assign")));
~~~

Khi người dùng không có quyền quản lý, danh sách không được tạo. Nếu có quyền, cả ba links được dựng trong cùng supplier và thêm vào model.

Có thể gom logic tạo links vào một method riêng để assembler dễ đọc:

~~~java
private List<Link> managementLinks(Order order) {
    return List.of(
            linkTo(methodOn(OrderController.class)
                    .approve(order.id()))
                    .withRel("approve"),
            linkTo(methodOn(OrderController.class)
                    .reject(order.id()))
                    .withRel("reject"));
}

model.addAllIf(canManage, () -> managementLinks(order));
~~~

Không tạo danh sách trước khi gọi addAllIf:

~~~java
// Cách này vẫn tạo toàn bộ links trước khi guard được kiểm tra.
List<Link> links = managementLinks(order);
model.addAllIf(canManage, () -> links);
~~~

Supplier chỉ trì hoãn công việc được đặt bên trong nó. Nếu link hoặc list đã được tạo trước, addIf và addAllIf không thể hoàn tác chi phí đó.

## Kết hợp addIf với MvcLink

Spring HATEOAS cung cấp MvcLink như cú pháp gọn để tạo Link từ lời gọi MvcUriComponentsBuilder. Lớp này có overload nhận Supplier<Object>:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.mvc.MvcLink;

Link cancel = MvcLink.of(
        () -> MvcLink.on(OrderController.class).cancel(orderId),
        LinkRelation.of("cancel"));
~~~

Supplier ở MvcLink.of(...) trì hoãn việc thực hiện lời gọi controller proxy cho đến khi MvcLink xử lý invocation. Overload không nhận Supplier yêu cầu invocation đã được tạo trước:

~~~java
Link cancel = MvcLink.of(
        MvcLink.on(OrderController.class).cancel(orderId),
        LinkRelation.of("cancel"));
~~~

Có thể kết hợp với addIf để trì hoãn toàn bộ quá trình tạo link cho tới khi điều kiện đúng:

~~~java
model.addIf(canCancel, () -> MvcLink.of(
        () -> MvcLink.on(OrderController.class).cancel(orderId),
        LinkRelation.of("cancel")));
~~~

Ở đây có hai ranh giới:

- addIf quyết định có cần tạo link hay không.
- MvcLink.of(Supplier, relation) trì hoãn controller invocation cho tới khi link được tạo.

Link vẫn được materialize trong lúc assembler chạy khi guard đúng. Nó không đợi đến lúc Jackson serialize response, và không được tính lại ở phía client.

MvcLink.of(Supplier, ...) có từ Spring HATEOAS 1.3. Nếu dự án dùng phiên bản cũ hơn, có thể dùng WebMvcLinkBuilder với supplier của addIf, hoặc nâng cấp phiên bản theo kế hoạch tương thích của dự án.

## Những gì nên và không nên trì hoãn

Lazy generation phù hợp với links có chi phí hoặc chỉ xuất hiện trong một số trường hợp:

- Action link chỉ khả dụng với một trạng thái nghiệp vụ.
- Link quản trị chỉ công bố cho người có quyền.
- Link tới dữ liệu phụ chỉ có khi tài nguyên có quan hệ tương ứng.
- Nhóm affordances có nhiều metadata cần phân tích.
- Link chỉ xuất hiện khi feature flag được bật.

Self link thường cần cho mọi item nên tạo trực tiếp sẽ dễ hiểu hơn. Không cần bọc mọi link trong Supplier nếu nó luôn được tạo; việc thêm lambda và abstraction không cần thiết cũng làm code khó đọc.

Supplier chỉ nên thực hiện công việc tạo link. Tránh đặt truy vấn database, gọi HTTP service hoặc thay đổi trạng thái domain vào Supplier. Nếu việc xác định khả năng phụ thuộc dữ liệu ngoài, hãy tải và kiểm tra dữ liệu trước, rồi truyền kết quả thành guard.

Lazy link generation cũng không thay thế authorization. Việc bỏ cancel link giúp client hiểu thao tác không được công bố, nhưng endpoint cancel vẫn phải kiểm tra quyền và trạng thái tại thời điểm request đến.

## Dùng EntityLinks cho các resource links lặp lại

Nếu nhiều assembler thường xuyên tạo link tới collection hoặc item của cùng một entity type, EntityLinks giúp tạo link theo domain type thay vì lặp lại controller invocation:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderLinks {

    private final EntityLinks entityLinks;

    OrderLinks(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    Link toOrder(Order order) {
        return entityLinks.linkToItemResource(Order.class, order.id());
    }

    Link toOrders() {
        return entityLinks.linkToCollectionResource(Order.class);
    }
}
~~~

Để ControllerEntityLinks mặc định phát hiện mapping, controller cần khai báo @ExposesResourceFor(Order.class), mapping cấp class cho collection và mapping cấp method cho item có path variable. EntityLinks được cung cấp khi hypermedia support được bật.

EntityLinks giảm sự phụ thuộc vào class controller và gom cách tạo link theo entity type. Đây là một lựa chọn kiến trúc hữu ích khi có nhiều nơi tạo cùng loại link; không nên mặc định rằng nó luôn nhanh hơn WebMvcLinkBuilder. Hãy đo trong workload thực tế nếu mục tiêu là tối ưu hiệu năng.

## Dùng RepresentationModelAssemblerSupport

RepresentationModelAssemblerSupport có thể tạo representation model và self link theo mapping của controller:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;

class OrderAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    OrderAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);
        model.setStatus(order.status());
        return model;
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel();
    }
}
~~~

createModelWithId(...) tạo model và thêm self link dựa trên controller mapping cùng ID. Mặc định instantiateModel(...) dùng reflection và yêu cầu model có no-argument constructor. Nếu việc khởi tạo bằng reflection trở thành chi phí đo được, có thể override method này để dùng constructor cụ thể hoặc factory phù hợp.

Assembler support giảm boilerplate khi mọi entity đều cần cùng quy tắc self link. Nó không tự làm cho mọi action link trở nên lazy; vẫn dùng addIf và addAllIf cho những links chỉ cần trong một số điều kiện.

## Hiểu chi phí trong collection lớn

Giả sử một trang có 100 đơn hàng và mỗi đơn hàng có 5 action links. Nếu chỉ 15 đơn hàng đủ điều kiện hiển thị action links, cách tạo eager có thể tạo tới 500 link objects, trong khi cách tạo có điều kiện chỉ tạo 75 action links.

Đây là mô hình minh họa, không phải benchmark. Chi phí thực tế phụ thuộc số mapping, proxy invocation, path variables, affordances, relation, serializer, JVM warm-up và cấu hình ứng dụng.

Những yếu tố cần xem khi tối ưu:

- Số lượng item trong mỗi response.
- Số links trên mỗi item.
- Tỷ lệ links bị loại do trạng thái hoặc quyền.
- Chi phí policy xác định guard.
- Chi phí tạo controller invocation và URI.
- Chi phí serialize HAL hoặc media type khác.
- Kích thước response trên mạng.

Lazy generation giảm công việc tạo link không được dùng. Nó không làm nhỏ response của những links vẫn được tạo, không giảm số lượng item được truy vấn và không tự giảm chi phí serialization của body.

## Đo trước và sau khi tối ưu

Không nên kết luận một cách tạo link nhanh hơn chỉ từ cảm nhận hoặc một request đơn lẻ. Tạo benchmark hoặc load test có dữ liệu đại diện và giữ nguyên các điều kiện giữa hai lần chạy.

Một quy trình đo có thể gồm:

1. Tạo fixture có số lượng item và tỷ lệ action links tương tự production.
2. Đo assembler tạo tất cả links trước khi kiểm tra điều kiện.
3. Đo assembler dùng addIf và addAllIf với cùng dữ liệu.
4. So sánh thời gian tạo representation, allocation/GC và kích thước response.
5. Đo endpoint qua HTTP để bao gồm serialization và các thành phần Spring MVC.
6. Chạy nhiều lần sau warm-up và so sánh median cùng p95 thay vì chỉ nhìn một kết quả.

Nếu cần microbenchmark, dùng JMH để kiểm soát warm-up, fork và phép đo JVM. Nếu cần biết tác động lên người dùng, dùng load test endpoint với concurrency và phân phối dữ liệu gần production. Tránh benchmark chỉ một lời gọi link builder rồi suy ra hiệu năng toàn API.

## Không cache Link tuyệt đối giữa các request

Link được tạo từ request context có thể phụ thuộc scheme, host, port, context path và forwarded headers. Nếu cache một Link tuyệt đối rồi tái sử dụng giữa các request, response có thể chứa host hoặc base path của request trước.

Không cache representation model mutable rồi dùng chung giữa người dùng hoặc request. Links có thể phụ thuộc principal, tenant, trạng thái và feature flag. Hãy cache dữ liệu domain hoặc metadata ổn định ở tầng phù hợp, rồi tạo representation và links theo request hiện tại.

Nếu cần giảm chi phí tra cứu mapping, dùng các abstraction như EntityLinks hoặc assembler chuyên biệt để gom quy tắc tạo URI. Không tự giữ một URL tuyệt đối toàn cục trừ khi nó thực sự là URI công khai cố định và không phụ thuộc request.

## WebFlux và link generation bất đồng bộ

MvcLink và WebMvcLinkBuilder dành cho Spring MVC. Trong ứng dụng WebFlux, dùng WebFluxLinkBuilder; API này cung cấp Mono<Link> để tiếp tục xử lý trong reactive pipeline.

Không gọi block() chỉ để lấy link trong luồng reactive. Hãy kết hợp Mono<Link> với map, flatMap hoặc zip theo cách phù hợp. Việc trì hoãn trong reactive pipeline khác với Supplier của RepresentationModel.addIf: một bên mô tả công việc bất đồng bộ, bên kia quyết định có gọi hàm tạo link đồng bộ hay không.

## Kiểm thử lazy link generation

Test cần xác minh hai điều: link xuất hiện khi guard đúng và supplier không được gọi khi guard sai.

Có thể dùng AtomicInteger để quan sát số lần supplier được gọi:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.assertj.core.api.Assertions.assertThat;

class LazyLinkGenerationTest {

    @Test
    void doesNotCreateLinkWhenGuardIsFalse() {
        AtomicInteger calls = new AtomicInteger();
        EntityModel<String> model = EntityModel.of("order");

        model.addIf(false, () -> {
            calls.incrementAndGet();
            return Link.of("/orders/42/cancel", "cancel");
        });

        assertThat(calls).hasValue(0);
        assertThat(model.hasLink("cancel")).isFalse();
    }

    @Test
    void createsLinkWhenGuardIsTrue() {
        AtomicInteger calls = new AtomicInteger();
        EntityModel<String> model = EntityModel.of("order");

        model.addIf(true, () -> {
            calls.incrementAndGet();
            return Link.of("/orders/42/cancel", "cancel");
        });

        assertThat(calls).hasValue(1);
        assertThat(model.hasLink("cancel")).isTrue();
    }
}
~~~

Với addAllIf, kiểm tra supplier không được gọi khi guard sai và toàn bộ links được thêm khi guard đúng. Với link tạo từ controller mapping, bổ sung MockMvc test để xác minh href cuối cùng vẫn đúng với mapping và request context.

Test logic lazy không thay thế test hợp đồng HTTP. Một test kiểm tra supplier chỉ chứng minh công việc được bỏ qua; test MockMvc xác nhận response HAL có đúng relation, href và media type.

## Những lỗi thường gặp

- **Tạo link trước rồi mới gọi addIf:** chi phí đã phát sinh; đặt toàn bộ logic tạo link bên trong Supplier.
- **Tạo list trước rồi gọi addAllIf:** Supplier chỉ trả list đã tạo không giúp trì hoãn việc tạo từng link.
- **Dùng Supplier cho mọi link:** self link luôn cần có thể tạo trực tiếp; chỉ trì hoãn links thực sự có điều kiện hoặc tốn kém.
- **Nghĩ link được tạo khi serialize:** Supplier được gọi lúc assembler gọi addIf hoặc addAllIf và guard đúng.
- **Đưa truy vấn database vào Supplier:** xác định dữ liệu và guard trước, giữ supplier tập trung vào link construction.
- **Bỏ kiểm tra authorization ở endpoint:** ẩn link chỉ hỗ trợ discovery; server vẫn phải bảo vệ request trực tiếp.
- **Cache link tuyệt đối giữa request:** host và base path có thể thay đổi theo request/proxy; tạo link trong request hiện tại.
- **Cho rằng EntityLinks luôn nhanh hơn:** đây là abstraction theo entity type; đo hiệu năng trước khi chọn vì lý do tốc độ.
- **Quên chi phí reflection của assembler support:** override instantiateModel(...) nếu phép đo cho thấy khởi tạo reflection là nút thắt.
- **Benchmark không đại diện:** đo với collection size, tỷ lệ action links, serialization và concurrency gần production.

## Quy trình áp dụng lazy link generation

1. Đo số lượng links được tạo trên mỗi item và xác định những links thường bị loại.
2. Tính điều kiện quyền và trạng thái trước khi tạo action links.
3. Dùng addIf(...) cho một link có điều kiện.
4. Dùng addAllIf(...) cho một nhóm links cùng điều kiện.
5. Đặt toàn bộ link construction bên trong Supplier; không tạo trước Link hoặc List.
6. Dùng MvcLink.of(Supplier, relation) khi muốn trì hoãn controller invocation trong Spring MVC.
7. Dùng EntityLinks hoặc assembler support khi chúng giúp gom quy tắc link dùng chung.
8. Kiểm thử supplier không chạy khi guard sai và href đúng khi guard đúng.
9. Benchmark assembler và endpoint sau warm-up để xác nhận tối ưu có lợi.

Lazy link generation giúp Spring HATEOAS tránh tạo những links mà representation hiện tại không cần. addIf và addAllIf cung cấp ranh giới trì hoãn rõ ràng: guard sai thì supplier không chạy; guard đúng thì link được tạo và thêm ngay trong lúc lắp ráp model. Kết hợp cách này với assembler gọn, link abstraction phù hợp và phép đo thực tế sẽ giúp giảm công việc không cần thiết mà vẫn giữ nguyên hợp đồng hypermedia.

## Tài liệu tham khảo

- Spring HATEOAS API, RepresentationModel: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html
- Spring HATEOAS API, MvcLink: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/MvcLink.html
- Spring HATEOAS Reference Documentation, Building links in Spring MVC: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder
- Spring HATEOAS Reference Documentation, EntityLinks: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.entity-links
- Spring HATEOAS API, RepresentationModelAssemblerSupport: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html
- Spring HATEOAS API, WebFluxLinkBuilder: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html
