# Tích hợp Spring WebFlux

Spring HATEOAS có thể được dùng cùng Spring WebFlux để xây dựng API REST reactive có liên kết hypermedia. Điểm khác biệt chính nằm ở cách tạo liên kết và lắp ráp biểu diễn: các thao tác này có thể trả về Reactor publisher, vì vậy cần kết hợp chúng trong luồng Mono hoặc Flux thay vì chờ kết quả đồng bộ.

Bài học này tập trung vào cách tích hợp Spring HATEOAS với controller WebFlux, cách dùng WebFluxLinkBuilder và ReactiveRepresentationModelAssembler, cách trả về HAL JSON, xử lý liên kết theo trạng thái, cấu hình địa chỉ khi chạy sau reverse proxy và kiểm thử bằng WebTestClient. Ví dụ dùng API quản lý đơn hàng; các kiểu Order và OrderService đại diện cho mô hình miền và lớp dịch vụ của ứng dụng.

## 1. WebFlux và HATEOAS phối hợp như thế nào?

Spring WebFlux là web framework reactive của Spring. Controller có thể trả về:

- Mono<T> khi một request tạo ra không hoặc một kết quả.
- Flux<T> khi một request tạo ra một luồng gồm nhiều phần tử.

Các publisher này được xử lý theo cơ chế non-blocking của Reactor. WebFlux có thể điều phối nhiều request mà không cần giữ một thread chờ cho từng thao tác I/O.

Spring HATEOAS bổ sung lớp hypermedia vào biểu diễn tài nguyên. Một biểu diễn có thể chứa dữ liệu đơn hàng cùng các liên kết như self, orders, customer hoặc cancel. Khi dùng WebFlux, việc tạo link có thể cần thông tin của request hiện tại và được thực hiện bên trong reactive pipeline.

Hai phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| WebFlux controller | Nhận request và trả về Mono hoặc Flux |
| Reactive service/repository | Truy xuất hoặc thay đổi dữ liệu theo dạng publisher |
| Representation model | Đóng gói dữ liệu công khai và các Link |
| Reactive assembler | Chuyển đối tượng miền thành representation theo dạng Mono |
| WebFluxLinkBuilder | Tạo Link dựa trên ánh xạ controller WebFlux và request hiện tại |
| Hypermedia serializer | Chuyển RepresentationModel thành định dạng như HAL JSON |

Không nên xem Spring HATEOAS là một cơ chế truy xuất dữ liệu reactive. Nó không thay thế Reactor, WebFlux hay reactive repository. Vai trò của nó là tạo biểu diễn hypermedia và liên kết trong khi ứng dụng vẫn duy trì luồng xử lý reactive.

## 2. Chuẩn bị dependency và cấu hình ứng dụng

Với Spring Boot, ứng dụng cần web stack WebFlux và Spring HATEOAS. Phiên bản dependency nên do Spring Boot dependency management quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>
</dependencies>
~~~

Nếu dự án đồng thời có spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thường ưu tiên cấu hình Spring MVC. Hãy kiểm tra web application type và các dependency thực tế để chắc chắn ứng dụng đang chạy trên WebFlux.

Trong cấu hình Spring thuần, có thể bật hỗ trợ HAL bằng annotation:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
public class HypermediaConfiguration {
}
~~~

Annotation này đăng ký các thành phần cần thiết để tuần tự hóa representation model theo định dạng hypermedia đã chọn. Trong ứng dụng Spring Boot, hãy kiểm tra cấu hình auto-configuration của phiên bản đang dùng trước khi thêm cấu hình thủ công, tránh đăng ký trùng lặp.

Khi endpoint công bố HAL JSON, client có thể gửi header:

~~~http
Accept: application/hal+json
~~~

Controller cũng có thể khai báo media type rõ ràng bằng hằng số MediaTypes.HAL_JSON_VALUE. Cách này giúp hợp đồng response được thể hiện ngay trong mapping.

## 3. Dùng Mono và Flux trong controller

Một controller WebFlux trả về publisher thay vì đợi kết quả rồi trả về object trực tiếp. Ví dụ service có thể cung cấp các phương thức:

~~~java
public interface OrderService {
    Mono<Order> findById(UUID id);

    Flux<Order> findFirstPage(int page, int size);

    Mono<Void> cancel(UUID id);
}
~~~

Đây là hợp đồng minh họa cho service. Khi triển khai thật, các phương thức truy xuất dữ liệu nên dùng reactive repository hoặc reactive client tương ứng, chẳng hạn R2DBC, Reactive MongoDB hoặc WebClient.

Một endpoint đọc đơn hàng có thể bắt đầu như sau:

~~~java
@GetMapping("/{id}")
public Mono<Order> findOne(@PathVariable UUID id) {
    return service.findById(id);
}
~~~

Khi bổ sung HATEOAS, kiểu trả về chuyển thành Mono của representation model:

~~~java
@GetMapping("/{id}")
public Mono<EntityModel<OrderRepresentation>> one(@PathVariable UUID id) {
    return service.findById(id)
        .map(order -> EntityModel.of(toRepresentation(order)));
}
~~~

Đoạn trên mới bọc dữ liệu bằng EntityModel, chưa tạo liên kết. Phần tiếp theo sẽ dùng WebFluxLinkBuilder để bổ sung các link một cách reactive.

Đối với danh sách, Flux<Order> biểu diễn một luồng nhiều đơn hàng. Nếu API muốn trả về một tài nguyên tập hợp HAL có _embedded và _links, cần lắp ráp các phần tử thành CollectionModel. Không nên mặc định trả Flux trực tiếp sẽ tạo ra cấu trúc CollectionModel; WebFlux có thể tuần tự hóa Flux thành một luồng phần tử, nhưng hình dạng đó không tương đương với một tài nguyên tập hợp HAL.

## 4. Tạo liên kết bằng WebFluxLinkBuilder

Trong Spring MVC, WebMvcLinkBuilder tạo Link đồng bộ. Với WebFlux, Spring HATEOAS cung cấp WebFluxLinkBuilder trong package org.springframework.hateoas.server.reactive.

Có thể dùng hai phương thức chính:

- linkTo(invocation) tạo builder từ lời gọi controller giả lập và tìm ServerWebExchange trong Reactor Context.
- linkTo(invocation, exchange) tạo builder với ServerWebExchange được truyền rõ ràng.

Lời gọi methodOn(...) tạo proxy ghi nhận phương thức controller và các tham số cần cho URI. Nó không gọi logic nghiệp vụ của handler. Cách dùng cơ bản:

~~~java
import org.springframework.hateoas.Link;
import reactor.core.publisher.Mono;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

Mono<Link> selfLink =
    linkTo(methodOn(OrderController.class).one(orderId, null))
        .withSelfRel()
        .toMono();
~~~

WebFluxLinkBuilder trả về một WebFluxBuilder. Sau khi chọn quan hệ bằng withSelfRel() hoặc withRel(...), kết quả là WebFluxLink; gọi toMono() để lấy Mono<Link> và tiếp tục ghép vào pipeline.

Trong ví dụ, handler one có thêm tham số ServerWebExchange. Giá trị null trong lời gọi methodOn chỉ là placeholder cho tham số hạ tầng không tham gia URI; methodOn ghi nhận lời gọi giả lập, còn exchange thực tế được truyền riêng khi tạo link ở ví dụ tiếp theo.

Ví dụ dùng exchange tường minh:

~~~java
Mono<Link> selfLink =
    linkTo(
        methodOn(OrderController.class).one(orderId, null),
        exchange
    )
    .withSelfRel()
    .toMono();
~~~

Nếu dùng overload không nhận exchange, WebFluxLinkBuilder kiểm tra Reactor Context để lấy ServerWebExchange của request. Khi không tìm thấy exchange, builder có thể tạo URI tương đối. Overload có exchange tường minh hữu ích khi assembler đã nhận ServerWebExchange qua tham số và muốn xác định rõ ngữ cảnh tạo link.

### 4.1. Vì sao không gọi block()?

Kết quả link là Mono<Link>, nên cần dùng map, flatMap, zip hoặc các toán tử Reactor khác để ghép nó vào luồng hiện tại. Không gọi block() để lấy Link đồng bộ trong controller.

Việc block() có thể làm thread xử lý request phải chờ. Nếu thao tác đó diễn ra trên event-loop thread, nó có thể làm giảm khả năng phục vụ các request khác và gây cảnh báo blocking trong môi trường reactive.

Cách xử lý phù hợp:

~~~java
return service.findById(id)
    .flatMap(order -> createModel(order, exchange));
~~~

Trong đó createModel trả về Mono<EntityModel<OrderRepresentation>>. Controller chỉ trả publisher cho WebFlux đăng ký và điều phối.

## 5. Lắp ráp representation bằng ReactiveRepresentationModelAssembler

Spring HATEOAS cung cấp ReactiveRepresentationModelAssembler<T, D> cho trường hợp cần chuyển một đối tượng nguồn thành representation model theo dạng Mono. Interface này thuộc package org.springframework.hateoas.server.reactive.

Khác với RepresentationModelAssembler đồng bộ, phương thức toModel của reactive assembler nhận thêm ServerWebExchange và trả về Mono<D>. Interface cũng cung cấp toCollectionModel nhận Flux nguồn và trả về Mono<CollectionModel<D>>.

Ví dụ DTO:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler tạo link self, orders và cancel. Liên kết cancel chỉ xuất hiện khi trạng thái đơn hàng cho phép thao tác:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.reactive.ReactiveRepresentationModelAssembler;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        ReactiveRepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public Mono<EntityModel<OrderRepresentation>> toModel(
            Order order, ServerWebExchange exchange) {

        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        Mono<Link> self = linkTo(
                methodOn(OrderController.class).one(order.getId(), null),
                exchange
            )
            .withSelfRel()
            .toMono();

        Mono<Link> orders = linkTo(
                methodOn(OrderController.class).all(null),
                exchange
            )
            .withRel("orders")
            .toMono();

        Mono<Link> cancel = order.canCancel()
            ? linkTo(
                    methodOn(OrderController.class).cancel(order.getId()),
                    exchange
                )
                .withRel("cancel")
                .toMono()
            : Mono.empty();

        return Mono.zip(self, orders)
            .flatMap(links -> {
                var model = EntityModel.of(
                    body,
                    links.getT1(),
                    links.getT2()
                );

                return cancel
                    .map(link -> {
                        model.add(link);
                        return model;
                    })
                    .defaultIfEmpty(model);
            });
    }
}
~~~

Ở đây, Mono.zip kết hợp hai link bắt buộc. Link cancel là publisher tùy chọn: nếu đơn hàng có thể hủy, publisher phát ra Link và assembler thêm link vào model; nếu không, Mono.empty() khiến defaultIfEmpty trả về model không có relation cancel.

Đối với tham số ServerWebExchange trong methodOn, giá trị null là placeholder vì lời gọi giả lập chỉ dùng để mô tả mapping. Đối tượng exchange thực tế được truyền vào overload linkTo để xây URI theo request hiện tại.

Assembler nhận Order và tạo OrderRepresentation, nhờ đó entity nội bộ không bị tuần tự hóa trực tiếp. Việc tạo link cũng nằm trong cùng reactive pipeline, nên có thể kết hợp thêm các kiểm tra quyền hoặc dữ liệu liên quan nếu cần.

### 5.1. Dùng assembler cho một tập hợp

ReactiveRepresentationModelAssembler có sẵn phương thức toCollectionModel nhận Flux và ServerWebExchange. Phương thức này chuyển từng phần tử thành representation rồi bọc chúng trong CollectionModel:

~~~java
Mono<CollectionModel<EntityModel<OrderRepresentation>>> collection =
    assembler.toCollectionModel(orders, exchange);
~~~

CollectionModel có thể chứa các link ở cấp tập hợp. Sau khi assembler tạo xong, controller có thể thêm self:

~~~java
return assembler.toCollectionModel(orders, exchange)
    .flatMap(model ->
        linkTo(methodOn(OrderController.class).all(null), exchange)
            .withSelfRel()
            .toMono()
            .map(model::add)
    );
~~~

Trong ví dụ, orders là Flux<Order> đã được giới hạn kích thước bởi service. Với dữ liệu lớn, hãy phân trang hoặc dùng cursor để giới hạn số phần tử trong một response. Tránh collect toàn bộ dữ liệu không giới hạn chỉ để tạo một CollectionModel.

Nếu biểu diễn cần relation cho trang kế tiếp hoặc trang trước, hãy tạo link từ thông tin trang thực tế và chỉ công bố các link phù hợp. Client nên theo các relation đó thay vì tự ghép query string.

## 6. Tích hợp assembler vào controller WebFlux

Controller sau kết hợp service reactive, assembler và WebFluxLinkBuilder:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.UUID;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService service,
            OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public Mono<EntityModel<OrderRepresentation>> one(
            @PathVariable UUID id,
            ServerWebExchange exchange) {

        return service.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> assembler.toModel(order, exchange));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public Mono<CollectionModel<EntityModel<OrderRepresentation>>> all(
            ServerWebExchange exchange) {

        var orders = service.findFirstPage(0, 20);

        return assembler.toCollectionModel(orders, exchange)
            .flatMap(model ->
                linkTo(methodOn(OrderController.class).all(null), exchange)
                    .withSelfRel()
                    .toMono()
                    .map(model::add)
            );
    }

    @PostMapping("/{id}/cancellation")
    public Mono<ResponseEntity<Void>> cancel(@PathVariable UUID id) {
        return service.cancel(id)
            .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

OrderNotFoundException là ngoại lệ nghiệp vụ minh họa; ứng dụng nên ánh xạ nó sang HTTP 404 bằng exception handler. Nếu service phát Mono.empty() cho tài nguyên không tồn tại, controller cần quyết định rõ semantics thay vì để response rỗng không chủ đích.

Phương thức all() lấy một tập hợp đã giới hạn từ service, gọi toCollectionModel rồi thêm self link. Phương thức one() tìm đơn hàng và chuyển nó thành EntityModel. Cả hai endpoint công bố HAL JSON.

Ví dụ này giả định các kiểu Order, OrderService và OrderNotFoundException đã được định nghĩa trong ứng dụng. Chúng không phải lớp do Spring HATEOAS cung cấp.

## 7. HAL JSON và liên kết hành động trong WebFlux

RepresentationModel có thể được trả trực tiếp từ controller WebFlux. Khi client yêu cầu HAL JSON, Spring HATEOAS chuyển các link thành phần _links và biểu diễn phần tử của collection dưới _embedded.

Ví dụ đơn hàng:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "orders": {
      "href": "/orders"
    },
    "cancel": {
      "href": "/orders/ORD-42/cancellation"
    }
  }
}
~~~

Ví dụ tập hợp đơn hàng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "/orders/ORD-42"
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

Tên relation của phần tử trong _embedded cần được kiểm soát như một phần hợp đồng API. Có thể dùng @Relation trên kiểu representation để chỉ định itemRelation và collectionRelation khi cần tên ổn định.

Liên kết cancel được tạo có điều kiện theo trạng thái nghiệp vụ. Nếu quyền thao tác phụ thuộc người dùng, assembler có thể kết hợp trạng thái đơn hàng với thông tin xác thực trong reactive security context trước khi quyết định công bố link. Dù link có xuất hiện hay không, endpoint cancel vẫn phải kiểm tra lại quyền và trạng thái khi nhận request.

### 7.1. Affordance

Link cho biết client có thể điều hướng đến một URI theo một relation. Affordance bổ sung mô tả thao tác mà server cung cấp tại link, chẳng hạn cập nhật hoặc hủy tài nguyên. Với WebFlux, WebFluxLinkBuilder.WebFluxLink hỗ trợ thêm affordance trong quá trình tạo link:

~~~java
var self = linkTo(
        methodOn(OrderController.class).one(orderId, null),
        exchange
    )
    .withSelfRel()
    .andAffordance(methodOn(OrderController.class).cancel(orderId));

Mono<Link> selfWithCancelAffordance = self.toMono();
~~~

Đây là ví dụ cấu trúc; thao tác affordance phải trỏ đến handler thực tế có mapping và request/response type phù hợp. Media type được chọn quyết định cách metadata affordance được biểu diễn. HAL cơ bản chủ yếu hiển thị URI và relation; nếu client cần thông tin biểu mẫu hoặc đầu vào thao tác, hãy xem xét HAL-FORMS hoặc media type có hỗ trợ affordance tương ứng.

## 8. Reactor Context và địa chỉ của link

WebFluxLinkBuilder.linkTo(invocation) tìm ServerWebExchange trong Reactor Context. Cơ chế này cho phép link builder lấy thông tin request hiện tại mà không cần truyền exchange qua mọi tầng của ứng dụng.

Điều đó cũng có nghĩa là vị trí tạo link có ảnh hưởng đến kết quả. Nên tạo link bên trong reactive pipeline gắn với request. Nếu gọi builder ở giai đoạn khởi tạo singleton, trong tác vụ chạy nền không có request context hoặc sau khi tự tách luồng bằng cách subscribe riêng, builder có thể không tìm thấy exchange và tạo URI tương đối.

Nếu assembler đã nhận ServerWebExchange, có thể dùng overload linkTo(invocation, exchange) như ví dụ trước. Cách này làm rõ request nào được dùng để dựng URI và thuận tiện khi kiểm thử.

### 8.1. Ứng dụng đứng sau reverse proxy

Trong môi trường triển khai, ứng dụng WebFlux có thể chạy tại địa chỉ nội bộ như http://service:8080 trong khi client truy cập qua domain HTTPS của gateway. Nếu tạo link từ thông tin kết nối nội bộ, response có thể chứa host, scheme hoặc port không đúng với địa chỉ công khai.

Spring WebFlux cung cấp ForwardedHeaderTransformer để xử lý các header chuyển tiếp từ proxy. Có thể đăng ký bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
public class ForwardedHeaderConfiguration {

    @Bean
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        return new ForwardedHeaderTransformer();
    }
}
~~~

Chỉ bật xử lý forwarded header khi hạ tầng proxy đáng tin cậy đã loại bỏ hoặc ghi đè các header do client tự gửi. Nếu ứng dụng tin header chuyển tiếp từ nguồn tùy ý, kẻ gọi có thể tác động đến host hoặc scheme được dùng để tạo link. Cấu hình proxy và transformer phải được xem như một phần của triển khai API.

## 9. Tích hợp quyền và trạng thái trong reactive flow

Trong một API reactive, việc quyết định link nào được công bố có thể phụ thuộc nhiều nguồn dữ liệu bất đồng bộ: trạng thái đơn hàng, quyền của người dùng, hạn mức hoặc trạng thái quy trình.

Không nên gọi một hàm blocking để lấy người dùng hiện tại hoặc truy xuất quyền ngay bên trong assembler. Hãy kết hợp publisher tương ứng. Ví dụ ở mức khái niệm:

~~~java
Mono<Boolean> canCancel =
    authorizationService.canCancel(currentUser, order);

return canCancel.flatMap(allowed -> {
    if (!allowed || !order.canCancel()) {
        return Mono.just(modelWithoutCancel);
    }

    return cancelLink(exchange)
        .map(link -> {
            modelWithoutCancel.add(link);
            return modelWithoutCancel;
        });
});
~~~

currentUser, authorizationService, modelWithoutCancel và cancelLink là các thành phần minh họa. Trong ứng dụng Spring Security reactive, thông tin SecurityContext được truy xuất qua ReactiveSecurityContextHolder. Không dùng SecurityContextHolder theo cách đồng bộ để đọc ngữ cảnh bảo mật trong reactive flow.

Liên kết chỉ phản ánh những hành động server đang công bố tại thời điểm tạo representation. Nó không phải token cấp quyền. Máy chủ luôn phải xác thực, phân quyền và kiểm tra lại điều kiện nghiệp vụ khi request thực thi hành động được gửi đến.

## 10. Phân trang và kích thước response

Một Flux có thể phát ra nhiều phần tử, nhưng một CollectionModel HAL thường được tuần tự hóa thành một biểu diễn tập hợp hữu hạn. Nếu lấy toàn bộ dữ liệu rồi chuyển thành CollectionModel, bộ nhớ có thể tăng theo số phần tử và thời gian tạo response cũng tăng.

Một số cách kiểm soát:

- Giới hạn số bản ghi cho mỗi request bằng page size hoặc cursor.
- Chỉ tạo CollectionModel cho tập kết quả đã giới hạn.
- Tạo link next, prev, first hoặc last dựa trên thông tin phân trang thực tế.
- Giữ response danh sách gọn; chỉ nhúng dữ liệu liên quan khi client thực sự cần.
- Với luồng dữ liệu lớn cần truyền liên tục, chọn giao thức và định dạng streaming phù hợp thay vì cố gắng đóng toàn bộ luồng vào một CollectionModel.

Reactive repository thường trả về Flux hoặc Mono và không nhất thiết cung cấp kiểu Page giống repository đồng bộ. Việc phân trang có thể cần query tùy chỉnh, cursor hoặc service điều phối cả truy vấn dữ liệu và tổng số bản ghi. Hãy thiết kế rõ giới hạn của response trước khi xây link điều hướng.

## 11. Kiểm thử bằng WebTestClient

WebTestClient là công cụ kiểm thử phù hợp với Spring WebFlux. Có thể kiểm tra status, content type, trường dữ liệu và các relation trong HAL JSON mà không cần gọi block() trong mã ứng dụng.

Ví dụ kiểm tra endpoint đơn hàng:

~~~java
webTestClient.get()
    .uri("/orders/{id}", orderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(orderId.toString())
    .jsonPath("$._links.self.href").exists()
    .jsonPath("$._links.orders.href").exists()
    .jsonPath("$._links.cancel.href").exists();
~~~

Kiểm tra trường hợp đơn hàng đã giao và không có link cancel:

~~~java
webTestClient.get()
    .uri("/orders/{id}", deliveredOrderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$._links.self.href").exists()
    .jsonPath("$._links.cancel").doesNotExist();
~~~

Với endpoint danh sách, hãy kiểm tra _embedded.orders, link self của từng phần tử và link self ở cấp tập hợp. Nếu API phân trang, kiểm tra next hoặc prev chỉ xuất hiện khi điều kiện trang tương ứng tồn tại.

Nếu cần giải mã response thành kiểu Spring HATEOAS như EntityModel hoặc CollectionModel, có thể áp dụng HypermediaWebTestClientConfigurer cho WebTestClient. Khi chỉ kiểm tra hợp đồng JSON bên ngoài, JSONPath thường đủ và giúp test tập trung vào cấu trúc mà client nhìn thấy.

Nên kiểm tra relation và ý nghĩa điều hướng thay vì khóa cứng toàn bộ host trong mọi test. Địa chỉ công khai có thể thay đổi theo context path, reverse proxy hoặc cấu hình môi trường. Các test riêng cho ForwardedHeaderTransformer nên xác minh host và scheme đã được xử lý đúng trong cấu hình proxy đáng tin cậy.

## 12. Những lỗi thường gặp khi tích hợp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng WebMvcLinkBuilder trong controller WebFlux | Link có thể phụ thuộc servlet request context và không phù hợp với reactive stack | Dùng WebFluxLinkBuilder |
| Gọi block() để lấy Link | Làm gián đoạn luồng non-blocking, có thể chặn event loop | Dùng toMono(), map, flatMap hoặc zip |
| Tạo link ngoài request context mà không truyền exchange | Builder có thể tạo URI tương đối hoặc thiếu ngữ cảnh request | Tạo link trong pipeline hoặc truyền ServerWebExchange |
| Trả Flux trực tiếp nhưng mong đợi HAL CollectionModel | Hình dạng response không có cấu trúc tài nguyên tập hợp như dự kiến | Dùng ReactiveRepresentationModelAssembler.toCollectionModel |
| Thu thập toàn bộ dữ liệu vào một collection | Response lớn có thể tiêu thụ nhiều bộ nhớ | Giới hạn bằng phân trang hoặc cursor |
| Dùng repository blocking trong event loop | Tắc nghẽn thread và làm giảm thông lượng | Dùng reactive repository/client hoặc cô lập thao tác blocking có kiểm soát |
| Chỉ kiểm tra link khi tạo response | Request cũ vẫn có thể được gửi sau khi trạng thái thay đổi | Kiểm tra lại quyền và điều kiện ở endpoint thực thi |
| Tin mọi forwarded header | Client có thể giả mạo địa chỉ gốc trong link | Chỉ xử lý header từ reverse proxy đáng tin cậy |

Một lưu ý khác: Spring HATEOAS có ReactiveRepresentationModelAssembler cho WebFlux. SPI EntityLinks truyền thống không được cung cấp sẵn cho ứng dụng WebFlux theo cùng cách như Spring MVC; nếu cần tra cứu link theo loại entity, hãy kiểm tra khả năng của phiên bản đang dùng hoặc xây một abstraction phù hợp với reactive pipeline.

## 13. Quy trình triển khai

Khi tích hợp Spring HATEOAS vào một API WebFlux hiện có, có thể thực hiện theo thứ tự:

1. Xác nhận ứng dụng đang chạy trên WebFlux và dùng dependency tương thích.
2. Xác định representation DTO và các kiểu model cần trả về.
3. Dùng WebFluxLinkBuilder để tạo link từ controller mapping.
4. Dùng ReactiveRepresentationModelAssembler khi cần chuyển đổi bất đồng bộ hoặc tạo nhiều link.
5. Trả Mono<EntityModel<T>> cho tài nguyên đơn và Mono<CollectionModel<D>> cho tập hợp HAL.
6. Giới hạn kích thước collection và tạo link phân trang từ trạng thái truy vấn.
7. Kết hợp trạng thái nghiệp vụ và quyền reactive khi công bố hành động.
8. Cấu hình forwarded header khi triển khai sau proxy đáng tin cậy.
9. Dùng WebTestClient kiểm tra nội dung, relation, media type và các trường hợp hành động không khả dụng.

Khi hoàn thành, API giữ được luồng xử lý non-blocking của WebFlux và vẫn cung cấp biểu diễn hypermedia có khả năng điều hướng. Client đọc trạng thái tài nguyên, theo relation để khám phá tài nguyên liên quan và nhận biết thao tác server đang công bố. Server tiếp tục giữ quyền quyết định cuối cùng bằng cách xác thực và kiểm tra điều kiện ở mỗi request.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [WebFluxLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [ReactiveRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/ReactiveRepresentationModelAssembler.html)
- [SimpleReactiveRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/SimpleReactiveRepresentationModelAssembler.html)

