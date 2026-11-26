# Reactive representation

Spring WebFlux xử lý yêu cầu HTTP theo mô hình reactive, thường dùng Reactor với hai kiểu publisher là Mono và Flux. Khi xây dựng REST API có hypermedia, representation cũng cần được tạo trong luồng reactive đó. Một endpoint chi tiết có thể trả Mono<EntityModel<T>>, còn endpoint collection có thể trả Mono<CollectionModel<EntityModel<T>>>. Các publisher cho phép việc truy vấn dữ liệu và tạo liên kết được kết hợp thành một pipeline mà không chặn thread để chờ kết quả.

Spring HATEOAS cung cấp các thành phần dành riêng cho WebFlux như ReactiveRepresentationModelAssembler và WebFluxLinkBuilder. Chúng giúp chuyển domain object thành representation có liên kết và xây URI dựa trên mapping của controller cùng ServerWebExchange hiện tại.

Bài học này trình bày cách tổ chức reactive representation, cách tạo link trong WebFlux, cách xử lý collection, cách cấu hình HAL, giới hạn của việc stream collection hypermedia và cách kiểm thử bằng WebTestClient.

## 1. Reactive representation là gì?

Trong Spring MVC, controller thường trả về một đối tượng đã được tạo sẵn như EntityModel<OrderDto> hoặc CollectionModel<EntityModel<OrderDto>>. Trong WebFlux, dữ liệu có thể chưa sẵn sàng tại thời điểm controller trả về. Repository reactive có thể phát ra kết quả sau đó, vì vậy controller trả về một publisher mô tả kết quả sẽ được phát ra.

Hai kiểu cơ bản:

| Kiểu | Số phần tử | Dùng khi |
| --- | --- | --- |
| Mono<T> | Không có hoặc một phần tử | Đọc một tài nguyên, trả một representation hoặc một collection model đã hoàn tất |
| Flux<T> | Không có, một hoặc nhiều phần tử | Đọc một luồng dữ liệu, truy vấn nhiều bản ghi hoặc phát sự kiện |

Một representation hypermedia vẫn là EntityModel, CollectionModel hoặc một lớp kế thừa RepresentationModel. Điểm khác biệt là publisher bao quanh representation:

| Nhu cầu | Kiểu trả về WebFlux thường dùng |
| --- | --- |
| Một tài nguyên có link | Mono<EntityModel<OrderDto>> |
| Một collection có link ở cấp collection và từng phần tử | Mono<CollectionModel<EntityModel<OrderDto>>> |
| Luồng phần tử được phát dần | Flux<EntityModel<OrderDto>> hoặc kiểu stream phù hợp với media type |

Không nên nhầm publisher với representation. Mono và Flux điều khiển thời điểm và cách dữ liệu được phát ra; EntityModel và CollectionModel mô tả dữ liệu cùng liên kết hypermedia.

## 2. Dependency cho Spring WebFlux và Spring HATEOAS

Trong ứng dụng Spring Boot dùng WebFlux, dependency cơ bản gồm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.hateoas</groupId>
    <artifactId>spring-hateoas</artifactId>
</dependency>
~~~

Sử dụng phiên bản Spring HATEOAS tương thích với phiên bản Spring Boot và Spring Framework mà ứng dụng đang dùng. Dependency trực tiếp spring-hateoas cung cấp các kiểu representation, assembler và link builder.

Lưu ý về starter: spring-boot-starter-hateoas được thiết kế cho Spring MVC. Khi dùng WebFlux, thêm spring-hateoas trực tiếp cùng spring-boot-starter-webflux; không dùng starter HATEOAS dành cho MVC trong cùng cấu hình WebFlux.

Spring Boot có cơ chế tự cấu hình hỗ trợ hypermedia trong những cấu hình phù hợp. Nếu cần bật định dạng và web stack một cách tường minh, có thể dùng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.support.WebStack;

@Configuration
@EnableHypermediaSupport(
        type = EnableHypermediaSupport.HypermediaType.HAL,
        stacks = WebStack.WEBFLUX
)
public class HypermediaConfiguration {
}
~~~

Không thêm cấu hình tường minh trùng lặp nếu ứng dụng đã được Boot tự cấu hình đúng. Khi chọn HAL, message conversion phải biết cách tuần tự hóa EntityModel, CollectionModel và các link theo media type HAL.

## 3. Giữ dữ liệu và service ở dạng reactive

Ví dụ sử dụng đơn hàng. Domain object và DTO được rút gọn:

~~~java
import java.math.BigDecimal;

public record Order(
        Long id,
        String status,
        BigDecimal total
) {
}
~~~

~~~java
import java.math.BigDecimal;

import org.springframework.hateoas.server.core.Relation;

@Relation(value = "order", collectionRelation = "orders")
public record OrderDto(
        Long id,
        String status,
        BigDecimal total
) {
}
~~~

Trong dự án Java thực tế, mỗi kiểu public được đặt trong file nguồn riêng. Annotation Relation đặt tên phần tử và collection relation để HAL có thể dùng _embedded.orders cho danh sách đơn hàng.

Service cung cấp publisher:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderService {

    Mono<Order> findById(Long id);

    Flux<Order> findAll();

    Mono<Void> cancel(Long id);
}
~~~

Mono<Order> biểu diễn thao tác tìm một đơn hàng. Nếu không tìm thấy, publisher có thể hoàn tất mà không phát ra phần tử. Flux<Order> biểu diễn các đơn hàng được phát ra theo yêu cầu từ tầng web.

Service và repository nên dùng API reactive phù hợp, chẳng hạn Spring Data R2DBC hoặc một client reactive. Nếu gọi JDBC, JPA hoặc một API blocking trực tiếp trên event-loop thread, ứng dụng có thể làm nghẽn khả năng xử lý đồng thời của WebFlux. Không dùng block() để ép kết quả reactive thành đối tượng đồng bộ trong luồng request.

## 4. ReactiveRepresentationModelAssembler

RepresentationModelAssembler thông thường có phương thức toModel(T) trả về representation trực tiếp. Với WebFlux, Spring HATEOAS cung cấp ReactiveRepresentationModelAssembler<T, D>, trong đó:

- toModel(T entity, ServerWebExchange exchange) trả về Mono<D>.
- toCollectionModel(Flux<? extends T> entities, ServerWebExchange exchange) trả về Mono<CollectionModel<D>>.

D phải là một kiểu kế thừa RepresentationModel. Tham số ServerWebExchange cung cấp ngữ cảnh request WebFlux để tạo liên kết phù hợp với host, scheme, context path và mapping hiện tại.

Assembler cho đơn hàng:

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.reactive.ReactiveRepresentationModelAssembler;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class OrderModelAssembler
        implements ReactiveRepresentationModelAssembler<
                Order,
                EntityModel<OrderDto>
        > {

    @Override
    public Mono<EntityModel<OrderDto>> toModel(
            Order order,
            ServerWebExchange exchange
    ) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.status(),
                order.total()
        );

        Mono<Link> selfLink = linkTo(
                methodOn(OrderController.class).one(order.id(), null),
                exchange
        ).withSelfRel().toMono();

        Mono<Link> collectionLink = linkTo(
                methodOn(OrderController.class).all(null),
                exchange
        ).withRel("orders").toMono();

        return Mono.zip(selfLink, collectionLink)
                .map(links -> EntityModel.of(
                        dto,
                        links.getT1(),
                        links.getT2()
                ));
    }
}
~~~

Ví dụ giả định OrderController có các phương thức one(Long id, ServerWebExchange exchange) và all(ServerWebExchange exchange). Giá trị null trong methodOn dành cho tham số ServerWebExchange của chữ ký controller; tham số này không phải path variable. WebFluxLinkBuilder nhận exchange thực tế ở đối số riêng để tạo URI trong đúng ngữ cảnh request.

Điểm cần chú ý là linkTo(...).withSelfRel() trả về một WebFluxLink trung gian; gọi toMono() để lấy Mono<Link>. Vì tạo link là một thao tác reactive, assembler kết hợp các publisher bằng Mono.zip rồi tạo EntityModel khi các link đã sẵn sàng.

Không gọi block() trong assembler. Việc chặn để lấy Link sẽ làm mất lợi ích của pipeline reactive và có thể gây deadlock hoặc làm cạn thread xử lý request.

## 5. WebFluxLinkBuilder và ServerWebExchange

WebMvcLinkBuilder dành cho Spring MVC. Với WebFlux, sử dụng WebFluxLinkBuilder trong package org.springframework.hateoas.server.reactive.

Hai cách tạo link:

~~~java
// Cách tường minh: truyền ServerWebExchange đang xử lý request.
WebFluxLinkBuilder.linkTo(invocation, exchange)

// Cách dựa trên Reactor Context: builder tìm ServerWebExchange trong context.
WebFluxLinkBuilder.linkTo(invocation)
~~~

Cách tường minh hữu ích khi assembler đã nhận ServerWebExchange qua ReactiveRepresentationModelAssembler. Cách không truyền exchange dựa vào Reactor Context; nếu không tìm thấy exchange, builder có thể tạo URI tương đối.

Các bước thường dùng:

1. Gọi WebFluxLinkBuilder.methodOn(Controller.class) để tham chiếu phương thức controller.
2. Gọi linkTo(invocation, exchange) để tạo builder theo mapping và request hiện tại.
3. Chọn relation bằng withSelfRel() hoặc withRel("...").
4. Gọi toMono() để lấy Mono<Link>.
5. Dùng map hoặc zip để gắn link vào representation.

Ví dụ tạo một link self độc lập:

~~~java
Mono<Link> self = linkTo(
        methodOn(OrderController.class).one(orderId, null),
        exchange
).withSelfRel().toMono();
~~~

WebFluxLinkBuilder kiểm tra Reactor Context nếu dùng overload không có exchange. Nó kết hợp thông tin đó với annotation Spring Web để tạo URI đầy đủ. Không hard-code hostname hoặc port vào assembler.

## 6. Tích hợp reactive representation vào controller

Controller WebFlux trả publisher thay vì chờ dữ liệu hoàn tất trước khi trả về. Ví dụ:

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler
    ) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public Mono<EntityModel<OrderDto>> one(
            @PathVariable Long id,
            ServerWebExchange exchange
    ) {
        return orderService.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)
                ))
                .flatMap(order -> assembler.toModel(order, exchange));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public Mono<CollectionModel<EntityModel<OrderDto>>> all(
            ServerWebExchange exchange
    ) {
        Mono<CollectionModel<EntityModel<OrderDto>>> collection =
                assembler.toCollectionModel(
                        orderService.findAll(),
                        exchange
                );

        Mono<Link> self = linkTo(
                methodOn(OrderController.class).all(null),
                exchange
        ).withSelfRel().toMono();

        return Mono.zip(collection, self)
                .map(result -> result.getT1().add(result.getT2()));
    }

    @DeleteMapping("/{id}/cancellation")
    public Mono<ResponseEntity<Void>> cancel(@PathVariable Long id) {
        return orderService.cancel(id)
                .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

Ở endpoint chi tiết, service trả Mono<Order>. flatMap được dùng vì assembler cũng trả Mono<EntityModel<OrderDto>>. Nếu dùng map ở đây, kết quả sẽ thành Mono<Mono<EntityModel<OrderDto>>> thay vì publisher phẳng mà controller cần.

Ở endpoint collection, service trả Flux<Order>. toCollectionModel nhận Flux đó và trả Mono<CollectionModel<EntityModel<OrderDto>>>. Controller tạo thêm link self cho collection rồi kết hợp hai publisher bằng Mono.zip.

Các lời gọi methodOn trong ví dụ tham chiếu đúng chữ ký của controller. Tham số ServerWebExchange được truyền null trong lời gọi proxy vì link builder nhận exchange thực tế riêng; exchange không phải biến của URI.

## 7. map, flatMap và zip khi tạo representation

Khi kết hợp dữ liệu và link trong WebFlux, chọn toán tử Reactor theo kiểu kết quả:

| Toán tử | Dùng khi | Ví dụ |
| --- | --- | --- |
| map | Hàm chuyển đổi đồng bộ trả về một đối tượng | Order -> OrderDto |
| flatMap | Hàm chuyển đổi trả về Mono hoặc publisher khác | Order -> Mono<EntityModel<OrderDto>> |
| zip | Cần đợi nhiều publisher độc lập rồi kết hợp kết quả | Mono<Link> self + Mono<Link> collection |
| flatMapSequential | Xử lý nhiều phần tử bất đồng bộ nhưng giữ thứ tự nguồn | Flux<Order> -> Flux<EntityModel<OrderDto>> |
| collectList | Thu thập các phần tử Flux thành Mono<List<T>> | Tạo một collection representation từ các phần tử |

Ví dụ map cho dữ liệu thuần:

~~~java
Mono<OrderDto> dto = orderService.findById(42L)
        .map(order -> new OrderDto(
                order.id(),
                order.status(),
                order.total()
        ));
~~~

Ví dụ flatMap khi assembler tạo link bất đồng bộ:

~~~java
Mono<EntityModel<OrderDto>> model = orderService.findById(42L)
        .flatMap(order -> assembler.toModel(order, exchange));
~~~

Ví dụ zip kết hợp hai link:

~~~java
Mono<EntityModel<OrderDto>> model = Mono.zip(selfLink, collectionLink)
        .map(links -> EntityModel.of(dto, links.getT1(), links.getT2()));
~~~

Không dùng subscribe() bên trong controller hoặc assembler để tự kích hoạt pipeline. WebFlux sẽ subscribe publisher được trả về từ handler. Tự subscribe làm tách công việc khỏi vòng đời request, khiến việc xử lý lỗi, cancellation và truyền kết quả HTTP khó kiểm soát.

## 8. Conditional link trong reactive assembler

Hypermedia có thể công bố thao tác theo trạng thái hiện tại của tài nguyên. Ví dụ, đơn hàng chỉ có link cancel khi status là PENDING. Trong WebFlux, link điều kiện cũng được tạo thành Mono<Link>:

~~~java
Mono<Link> cancelLink = order.status().equals("PENDING")
        ? linkTo(
                methodOn(OrderController.class).cancel(order.id()),
                exchange
        ).withRel("cancel").toMono()
        : Mono.empty();
~~~

Có thể kết hợp link tùy chọn với các link bắt buộc:

~~~java
return Mono.zip(selfLink, collectionLink)
        .flatMap(links -> cancelLink
                .map(cancel -> EntityModel.of(
                        dto,
                        links.getT1(),
                        links.getT2(),
                        cancel
                ))
                .defaultIfEmpty(EntityModel.of(
                        dto,
                        links.getT1(),
                        links.getT2()
                )));
~~~

Đây là phần mở rộng minh họa; controller cần có phương thức cancel(Long id, ServerWebExchange exchange) và endpoint tương ứng. Khi trạng thái không cho phép hủy, cancelLink hoàn tất rỗng và representation chỉ chứa các link bắt buộc.

Việc không công bố link cancel không thay thế xác thực hoặc kiểm tra trạng thái ở endpoint. Server vẫn phải kiểm tra lại quyền và trạng thái khi client gửi yêu cầu vì tài nguyên có thể thay đổi sau khi representation được tạo.

## 9. Collection hypermedia và giới hạn của streaming

Một điểm quan trọng trong API reactive assembler là:

~~~java
Mono<CollectionModel<D>> toCollectionModel(
        Flux<? extends T> entities,
        ServerWebExchange exchange
)
~~~

Kết quả là Mono<CollectionModel<D>>, không phải Flux<CollectionModel<D>>. Để tạo một collection representation duy nhất có _embedded và các link ở cấp collection, các phần tử phải được gom vào mô hình collection trước khi tuần tự hóa.

Điều đó có nghĩa một Flux đầu vào không tự động biến response HAL thành luồng vô hạn phát từng phần tử. CollectionModel phù hợp với tập hợp có kích thước hữu hạn và được giới hạn, chẳng hạn một trang dữ liệu. Với tập dữ liệu lớn, hãy dùng phân trang hoặc giới hạn số phần tử trước khi tạo CollectionModel.

Nếu yêu cầu nghiệp vụ là stream dữ liệu liên tục, ví dụ giá thị trường hoặc sự kiện cảm biến, hãy chọn kiểu phản hồi stream phù hợp như application/x-ndjson hoặc text/event-stream. Có thể gắn metadata điều hướng vào từng sự kiện hoặc cung cấp một resource điểm vào riêng. Đừng cố gom một luồng vô hạn vào một CollectionModel HAL.

Backpressure cho phép subscriber điều tiết tốc độ nhận dữ liệu trong pipeline reactive. Tuy nhiên, khi gọi collectList hoặc toCollectionModel, ứng dụng phải tích lũy các phần tử để tạo collection hoàn chỉnh. Backpressure không loại bỏ chi phí bộ nhớ của một collection quá lớn.

## 10. HAL và content negotiation trong WebFlux

RepresentationModel có thể được trả về từ controller WebFlux. Khi client yêu cầu HAL:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Endpoint có thể khai báo:

~~~java
@GetMapping(
        value = "/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public Mono<EntityModel<OrderDto>> one(...) {
    // ...
}
~~~

Với hỗ trợ HAL được cấu hình, Spring tuần tự hóa EntityModel thành JSON có _links. CollectionModel được tuần tự hóa thành collection representation, thường dùng _embedded cho phần tử và _links cho liên kết ở cấp collection.

Ví dụ phản hồi:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/42/cancellation"
    }
  }
}
~~~

Ví dụ trên chỉ minh họa cấu trúc HAL. URI thực tế được tạo từ mapping controller và ngữ cảnh request. Nếu client yêu cầu media type mà endpoint không hỗ trợ, Spring WebFlux có thể trả 406 Not Acceptable theo cơ chế content negotiation.

## 11. Reverse proxy và forwarded headers

Khi ứng dụng chạy sau reverse proxy hoặc load balancer, địa chỉ nội bộ có thể khác địa chỉ client sử dụng. Link hypermedia cần phản ánh scheme, host, port và prefix công khai.

Spring WebFlux có ForwardedHeaderTransformer để xử lý các forwarded header. Có thể đăng ký bean:

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

Chỉ bật xử lý forwarded headers khi proxy tin cậy được cấu hình để ghi đè các header do client gửi. Không nên tin forwarded header tùy ý từ request công khai vì chúng có thể làm thay đổi host hoặc scheme được dùng để tạo link.

## 12. Kiểm thử bằng WebTestClient

WebTestClient hỗ trợ kiểm thử controller WebFlux mà không cần gửi request qua mạng thật. Kiểm thử nên xác nhận status, media type, nội dung và các link hypermedia.

Ví dụ:

~~~java
import static org.mockito.Mockito.when;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@WebFluxTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @MockBean
    OrderService orderService;

    @Test
    void returnsOrderAsHalRepresentation() {
        when(orderService.findById(42L)).thenReturn(
                Mono.just(new Order(
                        42L,
                        "PENDING",
                        BigDecimal.valueOf(1250000)
                ))
        );

        webTestClient.get()
                .uri("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
                .expectBody()
                    .jsonPath("$.id").isEqualTo(42)
                    .jsonPath("$.status").isEqualTo("PENDING")
                    .jsonPath("$._links.self.href")
                        .value(org.hamcrest.Matchers.endsWith(
                                "/api/orders/42"
                        ))
                    .jsonPath("$._links.orders.href").exists();
    }
}
~~~

Đây là ví dụ test slice; các kiểu Order, OrderDto, OrderService, controller và assembler cần được đặt trong package ứng dụng. @Import đăng ký assembler trong WebFluxTest, còn service được mock để kiểm soát publisher trả về.

Với endpoint collection, có thể kiểm tra:

~~~java
when(orderService.findAll()).thenReturn(Flux.just(
        new Order(42L, "PENDING", BigDecimal.valueOf(1250000)),
        new Order(43L, "PAID", BigDecimal.valueOf(900000))
));

webTestClient.get()
        .uri("/api/orders")
        .accept(MediaTypes.HAL_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$._embedded.orders.length()").isEqualTo(2)
        .jsonPath("$._embedded.orders[0]._links.self.href").exists()
        .jsonPath("$._links.self.href").exists();
~~~

Nên bổ sung kiểm thử cho:

- Publisher Mono.empty() được ánh xạ thành 404 nếu đó là hợp đồng endpoint.
- Lỗi từ service reactive được chuyển thành HTTP status phù hợp.
- Collection rỗng vẫn trả cấu trúc HAL hợp lệ và link collection.
- Mỗi phần tử trong collection có link self.
- Link ở cấp collection trỏ đúng endpoint.
- Link có điều kiện chỉ xuất hiện ở trạng thái phù hợp.
- Media type và forwarded headers tạo representation đúng môi trường.

Ngoài WebFluxTest, kiểm thử tích hợp với application context đầy đủ giúp xác nhận repository reactive, codec HAL, cấu hình security và mapping cùng hoạt động.

## 13. Những lỗi thường gặp

**Dùng WebMvcLinkBuilder trong controller WebFlux.** WebMvcLinkBuilder dựa trên ngữ cảnh Servlet MVC. Dùng WebFluxLinkBuilder để tạo link từ WebFlux mapping và ServerWebExchange.

**Giả định EntityLinks có sẵn cho WebFlux.** Các triển khai EntityLinks tiêu chuẩn hiện tập trung vào Spring MVC. Với WebFlux, dùng WebFluxLinkBuilder để tham chiếu mapping của controller hoặc tự xây một abstraction reactive phù hợp với ứng dụng.

**Dùng spring-boot-starter-hateoas cùng WebFlux.** Starter này dành cho Spring MVC. Với WebFlux, thêm spring-boot-starter-webflux và dependency spring-hateoas trực tiếp.

**Gọi block() để lấy Link.** WebFluxLinkBuilder trả Mono<Link>. Kết hợp publisher bằng map, flatMap hoặc zip thay vì block.

**Dùng map khi hàm trả về Mono.** Kết quả sẽ thành publisher lồng nhau. Dùng flatMap để làm phẳng luồng.

**Tự gọi subscribe() trong controller hoặc assembler.** WebFlux quản lý subscription cho publisher mà handler trả về. Tự subscribe làm mất liên kết giữa request và pipeline.

**Cho rằng Flux đầu vào luôn tạo response stream.** ReactiveRepresentationModelAssembler.toCollectionModel trả Mono<CollectionModel<D>> và cần một collection hoàn chỉnh. Giới hạn số phần tử hoặc dùng định dạng streaming riêng cho dữ liệu không giới hạn.

**Dùng JPA hoặc JDBC blocking trên event loop.** Các lời gọi blocking có thể làm nghẽn thread xử lý request. Dùng repository/client reactive hoặc cô lập tác vụ blocking theo chiến lược phù hợp.

**Quên ServerWebExchange khi tạo link.** Link builder cần ngữ cảnh WebFlux để tạo URI chính xác. Truyền exchange tường minh hoặc bảo đảm Reactor Context có exchange khi dùng overload không tham số exchange.

**Cho rằng link là cơ chế phân quyền.** Link chỉ công bố khả năng điều hướng. Endpoint vẫn phải xác thực, kiểm tra quyền và trạng thái nghiệp vụ.

## 14. Ghi nhớ

Reactive representation kết hợp mô hình hypermedia của Spring HATEOAS với publisher Reactor. Mono<EntityModel<T>> phù hợp với một tài nguyên; Mono<CollectionModel<EntityModel<T>>> phù hợp với một collection hoàn chỉnh. Flux<T> thường là nguồn dữ liệu cho collection hoặc luồng stream.

ReactiveRepresentationModelAssembler chuyển một domain object thành Mono<RepresentationModel> và có thể chuyển Flux<T> thành Mono<CollectionModel<D>>. WebFluxLinkBuilder tạo link trong ngữ cảnh ServerWebExchange; withSelfRel hoặc withRel chọn quan hệ, còn toMono() đưa Link vào pipeline reactive.

Trong controller, dùng flatMap khi assembler hoặc thao tác tiếp theo trả publisher; dùng Mono.zip khi cần kết hợp nhiều link; tránh block() và subscribe() thủ công. CollectionModel cần tập hợp hữu hạn, vì vậy hãy phân trang hoặc giới hạn dữ liệu. Với stream liên tục, chọn media type streaming và thiết kế hypermedia phù hợp với từng sự kiện.

Kiểm thử bằng WebTestClient cần xác nhận dữ liệu, media type, link ở cấp tài nguyên và collection, hành vi publisher rỗng hoặc lỗi. Khi triển khai sau proxy, cấu hình ForwardedHeaderTransformer chỉ với proxy đáng tin cậy để link công bố địa chỉ mà client thực sự sử dụng.

## Tài liệu tham khảo

- [Spring Boot – Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [ReactiveRepresentationModelAssembler – Spring HATEOAS API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/ReactiveRepresentationModelAssembler.html)
- [WebFluxLinkBuilder – Spring HATEOAS API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [WebFluxLinkBuilder.WebFluxLink – Spring HATEOAS API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.WebFluxLink.html)
- [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html)
