# Kiểm thử WebFlux link

Trong Spring WebFlux, link hypermedia được tạo trong một luồng reactive và thường phụ thuộc vào request hiện tại. Vì vậy, kiểm thử link cần xác nhận cả URI, relation và cách Spring WebFlux truyền ngữ cảnh request qua Reactor Context. Một link có thể đúng khi được tạo với ServerWebExchange tường minh nhưng lại trở thành URI tương đối nếu được tạo ngoài request context.

Spring HATEOAS cung cấp WebFluxLinkBuilder để tạo Link từ mapping của controller WebFlux và ReactiveRepresentationModelAssembler để chuyển đối tượng miền thành representation model theo dạng Mono. WebTestClient giúp kiểm tra response HTTP của controller mà không cần khởi động server thật; HypermediaWebTestClientConfigurer bổ sung encoder/decoder để giải mã response HAL thành các kiểu EntityModel và CollectionModel.

Bài học này hướng dẫn kiểm thử link ở ba mức: kiểm thử publisher tạo link, kiểm thử assembler và kiểm thử endpoint bằng WebTestClient. Nội dung cũng đề cập đến URI template, link tùy chọn theo trạng thái, xử lý lỗi, request context, HAL JSON và các lỗi thường gặp khi kiểm thử reactive API.

## 1. Kiểm thử WebFlux link cần xác nhận điều gì?

Một endpoint WebFlux có thể trả Mono<EntityModel<T>> cho tài nguyên đơn hoặc Mono<CollectionModel<D>> cho tập hợp. Các Link được tạo bên trong luồng xử lý và có thể phụ thuộc vào request URI, scheme, host, context path và trạng thái nghiệp vụ.

Các nhóm assertion cần có:

| Thành phần | Nội dung cần xác nhận |
|---|---|
| Relation | Link có relation đúng như self, orders, customer hoặc cancel |
| Href | URI trỏ đúng handler và có path variable chính xác |
| Request context | Link sử dụng scheme, host và base path của request phù hợp |
| URI template | Tên biến và trạng thái templated đúng hợp đồng |
| HAL | Response có media type và cấu trúc hypermedia đúng |
| Điều kiện nghiệp vụ | Link hành động chỉ xuất hiện khi được phép |
| Reactive behavior | Publisher hoàn tất đúng, không bị subscribe hoặc block ngoài ý muốn |
| Lỗi HTTP | Tài nguyên không tồn tại hoặc thao tác thất bại được ánh xạ đúng status |

Không nên chỉ kiểm tra status 200 hoặc sự tồn tại của thuộc tính _links. Một response có thể trả đúng status nhưng link bị thiếu, relation sai hoặc href trỏ đến địa chỉ nội bộ không thể truy cập từ client.

## 2. WebFluxLinkBuilder và ngữ cảnh request

WebFluxLinkBuilder nằm trong package org.springframework.hateoas.server.reactive. Nó tạo Link từ lời gọi giả lập đến controller method.

Có hai cách lấy ngữ cảnh request:

- linkTo(invocation) tìm ServerWebExchange trong Reactor Context. Nếu không có exchange, builder có thể tạo URI tương đối.
- linkTo(invocation, exchange) dùng ServerWebExchange được truyền tường minh.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public Mono<EntityModel<OrderRepresentation>> one(
            @PathVariable UUID id,
            ServerWebExchange exchange) {
        // Tìm đơn hàng và tạo representation
    }
}
~~~

Tạo self link với exchange tường minh:

~~~java
Mono<Link> self = linkTo(
        methodOn(OrderController.class).one(orderId, null),
        exchange
    )
    .withSelfRel()
    .toMono();
~~~

methodOn(...) ghi nhận handler method và tham số cần cho mapping; nó không chạy logic nghiệp vụ của controller. Tham số exchange trong lời gọi giả lập là placeholder vì exchange thật được truyền riêng cho linkTo(...).

Có thể import static:

~~~java
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;
~~~

WebFluxLinkBuilder trả về WebFluxBuilder. Sau khi chọn relation bằng withSelfRel() hoặc withRel(...), kết quả là WebFluxLink. Gọi toMono() để nhận Mono<Link> và ghép nó vào reactive pipeline.

## 3. Kiểm thử WebFluxLinkBuilder độc lập bằng StepVerifier

Khi cần kiểm tra riêng việc tạo link, có thể tạo MockServerWebExchange rồi truyền trực tiếp cho linkTo(...). Cách này giúp test không phụ thuộc vào một HTTP server thật.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import reactor.test.StepVerifier;

import java.util.UUID;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

class OrderLinkBuilderTest {

    @Test
    void createsSelfLinkFromHandlerMapping() {
        UUID id = UUID.fromString(
            "7f2d8a6e-3f16-4f41-9a73-1f0b4e6c9a20"
        );

        MockServerHttpRequest request =
            MockServerHttpRequest.get(
                "https://api.example.test/orders"
            ).build();

        ServerWebExchange exchange =
            MockServerWebExchange.from(request);

        Mono<Link> self = linkTo(
                methodOn(OrderController.class).one(id, null),
                exchange
            )
            .withSelfRel()
            .toMono();

        StepVerifier.create(self)
            .assertNext(link -> {
                assertThat(link.getRel())
                    .isEqualTo(IanaLinkRelations.SELF);
                assertThat(link.getHref())
                    .endsWith("/orders/" + id);
            })
            .verifyComplete();
    }
}
~~~

Test xác nhận hai đặc tính: relation self và href chứa path variable đúng. Có thể kiểm tra thêm scheme và host nếu chúng là một phần của mục tiêu test:

~~~java
assertThat(link.getHref())
    .startsWith("https://api.example.test/");
~~~

MockServerWebExchange giúp kiểm thử overload có exchange tường minh. Nó không thay thế test tích hợp qua WebTestClient, vì test này chưa xác nhận controller, serializer và message codec phối hợp với nhau.

Nếu chỉ muốn xác nhận publisher tạo đúng một link, StepVerifier phù hợp hơn việc gọi block() trong test. Trong mã ứng dụng WebFlux, không gọi block() để chờ link; hãy tiếp tục dùng map, flatMap, zip hoặc các toán tử Reactor khác.

## 4. Kiểm thử link lấy exchange từ Reactor Context

Một số controller tạo link bằng overload không truyền exchange:

~~~java
Mono<Link> self = linkTo(
        methodOn(OrderController.class).one(orderId, null)
    )
    .withSelfRel()
    .toMono();
~~~

Trong trường hợp này, WebFluxLinkBuilder tìm ServerWebExchange trong Reactor Context. Khi không tìm thấy exchange, API có thể tạo URI tương đối. Vì thế, không nên viết unit test gọi linkTo(...) ngoài request context rồi mặc định rằng kết quả phải chứa host công khai.

Cách kiểm thử phù hợp là gọi endpoint qua WebTestClient. WebFlux thiết lập request context cho quá trình xử lý request; test có thể xác nhận link cuối cùng trong response.

Nếu assembler nhận ServerWebExchange, truyền exchange tường minh thường làm dependency rõ ràng hơn và dễ kiểm thử trực tiếp. Nếu ứng dụng chủ ý dựa vào Reactor Context, cần có integration test chứng minh link được tạo đúng trong request thực tế.

Không tự subscribe vào publisher trong controller hoặc assembler để lấy link rồi thêm vào model. Một lệnh subscribe() riêng có thể tách công việc khỏi request lifecycle, làm mất request context và khiến response được trả trước khi link hoàn tất.

## 5. Tổ chức assembler reactive để kiểm thử được

ReactiveRepresentationModelAssembler<T, D> là phiên bản reactive của RepresentationModelAssembler. Phương thức toModel nhận đối tượng nguồn cùng ServerWebExchange và trả về Mono<D>. Phương thức toCollectionModel nhận Flux nguồn và trả về Mono<CollectionModel<D>>.

Ví dụ DTO:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler tạo link self và orders:

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
        ReactiveRepresentationModelAssembler<
            Order, EntityModel<OrderRepresentation>> {

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

        return Mono.zip(self, orders)
            .map(links -> EntityModel.of(
                body,
                links.getT1(),
                links.getT2()
            ));
    }
}
~~~

Trong ví dụ, handler one và all nhận ServerWebExchange. Giá trị null trong methodOn(...) là placeholder cho tham số hạ tầng; exchange thật được truyền vào linkTo(...).

Có thể kiểm thử assembler riêng bằng MockServerWebExchange và StepVerifier:

~~~java
@Test
void assemblesOrderWithSelfAndCollectionLinks() {
    Order order = sampleOrder();

    ServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get(
            "https://api.example.test/orders"
        ).build()
    );

    StepVerifier.create(assembler.toModel(order, exchange))
        .assertNext(model -> {
            assertThat(model.getContent().id())
                .isEqualTo(order.getId());
            assertThat(model.hasLink(IanaLinkRelations.SELF))
                .isTrue();
            assertThat(model.hasLink("orders"))
                .isTrue();
        })
        .verifyComplete();
}
~~~

StepVerifier thuộc module reactor-test, thường được khai báo ở scope test. Nếu dùng @WebFluxTest, các component thông thường như assembler không nhất thiết được quét tự động; hãy đưa chúng vào test bằng @Import hoặc cấu hình slice phù hợp.

Test assembler phù hợp để kiểm tra việc chuyển đổi dữ liệu và tập link. Nó không xác nhận HAL JSON hoặc status HTTP; các phần đó cần được kiểm tra ở tầng endpoint.

## 6. Kiểm thử link hành động có điều kiện

Một link hành động có thể phụ thuộc trạng thái tài nguyên và quyền của người dùng. Ví dụ, đơn hàng mới tạo hoặc đang xử lý có thể hủy; đơn đã giao thì không.

Assembler có thể tạo link cancel như một publisher tùy chọn:

~~~java
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
~~~

Khi canCancel() là true, publisher phát ra link và model nhận relation cancel. Khi điều kiện sai, Mono.empty() khiến defaultIfEmpty trả về model không có link đó.

Nên có hai test riêng:

~~~java
@Test
void includesCancelWhenOrderCanBeCancelled() {
    Order order = orderInProcessingState();

    StepVerifier.create(assembler.toModel(order, exchange))
        .assertNext(model ->
            assertThat(model.hasLink("cancel")).isTrue()
        )
        .verifyComplete();
}

@Test
void omitsCancelWhenOrderCannotBeCancelled() {
    Order order = deliveredOrder();

    StepVerifier.create(assembler.toModel(order, exchange))
        .assertNext(model ->
            assertThat(model.hasLink("cancel")).isFalse()
        )
        .verifyComplete();
}
~~~

Nếu khả năng thao tác còn phụ thuộc quyền người dùng, test cần cung cấp SecurityContext reactive phù hợp hoặc mock abstraction phân quyền mà assembler sử dụng. Link chỉ phản ánh hành động server công bố tại thời điểm tạo response; endpoint vẫn phải kiểm tra quyền và trạng thái khi nhận request.

## 7. Thiết lập WebTestClient cho hypermedia

WebTestClient là HTTP client dành cho kiểm thử ứng dụng WebFlux. Có thể bind nó với controller, ApplicationContext hoặc một server đang chạy.

Với Spring HATEOAS, nếu chỉ kiểm tra JSON thô thì JSONPath có thể đủ. Nếu muốn giải mã response thành EntityModel hoặc CollectionModel, cần đăng ký encoder và decoder hỗ trợ hypermedia.

Spring HATEOAS cung cấp HypermediaWebTestClientConfigurer trong package org.springframework.hateoas.config. Configurer này đăng ký các Jackson encoder/decoder cần thiết cho hypermedia.

Với Spring Boot, có thể cấu hình builder:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class OrderWebFluxLinkTests {

    @Autowired
    WebTestClient.Builder builder;

    @Autowired
    HypermediaWebTestClientConfigurer configurer;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = builder.apply(configurer).build();
    }
}
~~~

Nếu ứng dụng chưa tự cấu hình hypermedia, cần bật định dạng mong muốn, ví dụ HAL:

~~~java
@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL
)
class HypermediaConfiguration {
}
~~~

Trong dự án Spring Boot đã có auto-configuration cho Spring HATEOAS, hãy kiểm tra cấu hình hiện tại trước khi thêm EnableHypermediaSupport thủ công.

WebTestClient là immutable value type. Hãy giữ lại instance được tạo từ builder đã áp dụng configurer; không giả định rằng thay đổi trên builder hoặc client cũ tự động cập nhật instance đã build.

## 8. Kiểm thử response HAL bằng JSONPath

Cách đơn giản nhất là kiểm tra response JSON mà client nhận được:

~~~java
client.get()
    .uri("/orders/{id}", orderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(orderId.toString())
    .jsonPath("$._links.self.href").exists()
    .jsonPath("$._links.orders.href").exists();
~~~

Kiểm tra link cancel khi đơn hàng được phép hủy:

~~~java
client.get()
    .uri("/orders/{id}", processingOrderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$._links.cancel.href").exists();
~~~

Và kiểm tra link không xuất hiện khi đơn hàng đã giao:

~~~java
client.get()
    .uri("/orders/{id}", deliveredOrderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$._links.cancel").doesNotExist();
~~~

JSONPath kiểm tra đúng cấu trúc bên ngoài mà client nhìn thấy. Đây là lựa chọn tốt khi mục tiêu test là bảo vệ tên relation, href và media type mà không cần giải mã response thành object Java.

## 9. Giải mã HAL thành EntityModel và CollectionModel

Khi cần kiểm tra bằng API của Spring HATEOAS, dùng TypeReferences để giữ thông tin generic lúc giải mã response.

Ví dụ một tài nguyên đơn:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.server.core.TypeReferences;

client.get()
    .uri("/orders/{id}", orderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody(
        new TypeReferences.EntityModelType<OrderRepresentation>() {}
    )
    .consumeWith(result -> {
        EntityModel<OrderRepresentation> model =
            result.getResponseBody();

        assertThat(model).isNotNull();
        assertThat(model.getContent().id()).isEqualTo(orderId);
        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
    });
~~~

Ví dụ tập hợp:

~~~java
client.get()
    .uri("/orders")
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody(
        new TypeReferences.CollectionModelType<
            EntityModel<OrderRepresentation>>() {}
    )
    .consumeWith(result -> {
        CollectionModel<EntityModel<OrderRepresentation>> model =
            result.getResponseBody();

        assertThat(model).isNotNull();
        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
        assertThat(model.getContent()).isNotEmpty();
    });
~~~

TypeReferences.EntityModelType và CollectionModelType là các ParameterizedTypeReference tiện ích của Spring HATEOAS. Chúng giúp giữ kiểu generic khi giải mã JSON, thay vì chỉ truyền EntityModel.class hoặc CollectionModel.class rồi mất kiểu nội dung cụ thể.

Khi test tập hợp rỗng, thay isNotEmpty() bằng isEmpty() và xác nhận link self vẫn được công bố nếu đó là hợp đồng endpoint. Nếu ứng dụng dùng RepresentationModelProcessor cho collection rỗng, hãy kiểm tra processor cũng được áp dụng với fallback type đã cấu hình.

## 10. Kiểm thử endpoint bằng WebTestClient bind trực tiếp

Không nhất thiết phải khởi động toàn bộ ứng dụng để kiểm tra một controller. Có thể bind WebTestClient vào ApplicationContext đã cấu hình WebFlux:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .build()
    .mutateWith(configurer);
~~~

Cách này tạo WebHandler chain từ ApplicationContext và cho phép test controller, filter, codec và cấu hình liên quan trong môi trường mock request/response.

Có thể bind trực tiếp vào controller:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(service, assembler))
    .build();
~~~

Cách bind trực tiếp phù hợp với test hẹp, nhưng cần tự cung cấp các thành phần phụ thuộc và cấu hình hypermedia cần thiết. Nếu cần kiểm tra Spring Security, forwarded header, filter hoặc cấu hình codec của toàn ứng dụng, nên bind ApplicationContext hoặc chạy test với server thật.

Các mức kiểm thử có phạm vi khác nhau:

| Cách thiết lập | Phạm vi phù hợp |
|---|---|
| StepVerifier với assembler | Kiểm tra publisher, model và link |
| WebTestClient.bindToController | Kiểm tra controller với hạ tầng mock tối thiểu |
| WebTestClient.bindToApplicationContext | Kiểm tra controller cùng cấu hình WebFlux của context |
| @SpringBootTest + WebTestClient | Kiểm tra tích hợp rộng hơn, có thể dùng server thật |
| WebTestClient.bindToServer | Kiểm tra end-to-end qua HTTP tới ứng dụng đang chạy |

Chọn mức test dựa trên rủi ro cần xác nhận. Không cần dùng full server cho mọi trường hợp nếu lỗi chỉ nằm trong logic assembler.

## 11. Kiểm thử URI template và query link

Link tìm kiếm có thể chứa URI template để client điền các query parameter:

~~~java
Mono<Link> search = linkTo(
        methodOn(OrderController.class).search(null, null),
        exchange
    )
    .withRel("search")
    .toMono();
~~~

Đoạn trên minh họa việc tạo template trong ngữ cảnh reactive. Trong mã ứng dụng, giữ kết quả dưới dạng Mono<Link> và ghép vào pipeline. Trong test, dùng StepVerifier hoặc kiểm tra template sau khi endpoint trả response; không gọi block() trong controller hoặc assembler.

Ví dụ kiểm tra qua WebTestClient:

~~~java
client.get()
    .uri("/orders")
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$._links.search.templated").isEqualTo(true)
    .jsonPath("$._links.search.href").exists();
~~~

Nếu muốn kiểm tra tên biến, có thể giải mã model hoặc lấy href từ response JSON rồi kiểm tra các biến template được công bố. Sau đó mở rộng template với giá trị cụ thể và gửi request tiếp theo để xác nhận endpoint nhận đúng query.

Không nên giả định truyền null vào mọi đối số methodOn luôn tạo URI template cho mọi loại tham số. Hãy xác nhận mapping, annotation request parameter và URI contributor thực tế tạo ra template như mong muốn.

## 12. Kiểm thử lỗi và trạng thái HTTP

Link chỉ giúp client điều hướng; endpoint vẫn phải trả status đúng nếu tài nguyên không tồn tại hoặc thao tác không hợp lệ.

Ví dụ controller:

~~~java
@GetMapping("/{id}")
public Mono<EntityModel<OrderRepresentation>> one(
        @PathVariable UUID id,
        ServerWebExchange exchange) {

    return service.findById(id)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
        .flatMap(order -> assembler.toModel(order, exchange));
}
~~~

Nếu service trả Mono.empty(), switchIfEmpty chuyển trường hợp đó thành lỗi nghiệp vụ. Một exception handler có thể ánh xạ lỗi sang HTTP 404.

Test:

~~~java
client.get()
    .uri("/orders/{id}", missingOrderId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isNotFound();
~~~

Các trường hợp khác nên được kiểm thử tương ứng:

- 400 khi query parameter hoặc request body không hợp lệ.
- 401/403 khi xác thực hoặc phân quyền thất bại.
- 404 khi tài nguyên đơn không tồn tại.
- 409 khi thao tác xung đột trạng thái nghiệp vụ.
- 5xx khi lỗi không dự kiến xảy ra và được xử lý theo chính sách ứng dụng.

Đừng trả một EntityModel rỗng với HTTP 200 chỉ để giữ response hypermedia. Nếu tài nguyên không tồn tại, status cần phản ánh đúng kết quả request.

## 13. Kiểm thử request context và reverse proxy

WebFluxLinkBuilder có thể tạo URI từ ServerWebExchange. Khi ứng dụng chạy sau reverse proxy, URI nội bộ của service có thể khác địa chỉ mà client truy cập.

Cần kiểm tra các thành phần sau khi chúng thuộc cấu hình triển khai:

- Scheme công khai là HTTPS hay HTTP.
- Host và port được công bố trong href.
- Context path hoặc prefix của gateway.
- Forwarded hoặc X-Forwarded-* headers được xử lý theo cấu hình tin cậy.
- Link không vô tình chứa hostname nội bộ của container hoặc service.

Có thể dùng WebTestClient với request header chuyển tiếp trong integration test để xác nhận link được tạo đúng theo cấu hình ứng dụng. Tuy nhiên, không nên tin header do client tùy ý gửi. Reverse proxy phải loại bỏ hoặc ghi đè forwarded header không đáng tin cậy trước khi chuyển request đến ứng dụng.

Đối với test dùng MockServerWebExchange, hãy thiết lập URI request đúng mục tiêu rồi truyền exchange tường minh vào WebFluxLinkBuilder. Đối với test toàn luồng, hãy cấu hình filter hoặc transformer giống môi trường triển khai và kiểm tra href thực tế trong HAL response.

## 14. Kiểm thử collection và publisher hữu hạn

Reactive controller có thể trả Flux<T>, nhưng một tài nguyên tập hợp HAL thường cần một CollectionModel hữu hạn. ReactiveRepresentationModelAssembler.toCollectionModel(...) nhận Flux nguồn và trả Mono<CollectionModel<D>>.

Ví dụ:

~~~java
@GetMapping
public Mono<CollectionModel<EntityModel<OrderRepresentation>>> all(
        ServerWebExchange exchange) {

    Flux<Order> orders = service.findFirstPage(0, 20);

    return assembler.toCollectionModel(orders, exchange)
        .flatMap(model ->
            linkTo(methodOn(OrderController.class).all(null), exchange)
                .withSelfRel()
                .toMono()
                .map(model::add)
        );
}
~~~

Trong test, xác nhận response chứa tập hợp đúng kích thước và các link cấp collection:

~~~java
client.get()
    .uri("/orders")
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody(
        new TypeReferences.CollectionModelType<
            EntityModel<OrderRepresentation>>() {}
    )
    .consumeWith(result -> {
        var model = result.getResponseBody();

        assertThat(model).isNotNull();
        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
        assertThat(model.getContent()).hasSize(2);
    });
~~~

Nếu Flux có thể phát ra số lượng phần tử lớn, hãy giới hạn bằng phân trang hoặc cursor trước khi chuyển thành CollectionModel. Không collect vô hạn một stream vào collection chỉ để tạo HAL response.

Đối với stream sự kiện liên tục như Server-Sent Events, hãy dùng test streaming với FluxExchangeResult và StepVerifier. Đây là hợp đồng streaming khác với một tài nguyên collection HAL thông thường; không nên dùng CollectionModel để bọc một luồng không có điểm kết thúc.

## 15. Những lỗi thường gặp khi kiểm thử WebFlux link

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng WebMvcLinkBuilder trong WebFlux | Không dùng đúng request context reactive | Dùng WebFluxLinkBuilder |
| Gọi linkTo(...) ngoài request context rồi mong có absolute URI | Builder có thể trả URI tương đối | Truyền ServerWebExchange hoặc test qua WebTestClient |
| Gọi block() trong controller/assembler | Chặn luồng xử lý reactive | Dùng toMono(), map, flatMap hoặc zip |
| Tự subscribe() để lấy link | Tách công việc khỏi request lifecycle và có thể mất context | Trả publisher cho WebFlux điều phối |
| Không cấu hình HypermediaWebTestClientConfigurer | Không giải mã được HAL thành EntityModel/CollectionModel | Áp dụng configurer cho WebTestClient |
| Chỉ kiểm tra status 200 | Không phát hiện link sai hoặc thiếu | Kiểm tra relation, href và media type |
| Chỉ kiểm tra JSONPath | Không xác nhận được model giải mã theo generic type | Bổ sung test với TypeReferences khi cần |
| Chỉ test assembler | Không phát hiện lỗi serializer hoặc content negotiation | Thêm integration test WebTestClient |
| Dùng Mono/Flux vô hạn cho CollectionModel | Response không hoàn tất hoặc giữ dữ liệu quá lâu | Giới hạn tập hợp hoặc dùng giao thức streaming |
| Tin forwarded header từ mọi nguồn | Href có thể bị giả mạo host/scheme | Chỉ tin proxy được kiểm soát |

## 16. Checklist cho bộ kiểm thử WebFlux link

Trước khi hoàn thành một endpoint Spring HATEOAS trên WebFlux, hãy xác nhận:

1. Link được tạo bằng WebFluxLinkBuilder.
2. Link sử dụng ServerWebExchange đúng hoặc được lấy từ Reactor Context trong request.
3. Relation self và các relation nghiệp vụ có tên đúng.
4. Href chứa path variable và query parameter đúng.
5. URI template có đúng biến và trạng thái templated.
6. Assembler trả Mono của representation model và không block.
7. Link hành động xuất hiện hoặc biến mất theo trạng thái và quyền.
8. WebTestClient nhận media type HAL JSON như hợp đồng.
9. HypermediaWebTestClientConfigurer được áp dụng khi giải mã thành model.
10. Test có cả JSONPath và TypeReferences nếu cần bảo vệ cấu trúc bên ngoài lẫn kiểu Java.
11. Collection có giới hạn; stream vô hạn được kiểm thử như giao thức streaming.
12. Request context, context path và forwarded header được kiểm tra theo cấu hình triển khai.
13. Tài nguyên không tồn tại và lỗi phân quyền trả status HTTP phù hợp.

Kiểm thử WebFlux link cần bao phủ cả reactive pipeline lẫn hợp đồng HTTP mà client nhận được. StepVerifier giúp kiểm tra publisher và assembler; WebTestClient kiểm tra controller, request context, serializer và media type. Khi kiểm thử cả relation, href, điều kiện hành động và cách giải mã HAL, API có thể thay đổi mapping mà vẫn giữ khả năng điều hướng rõ ràng cho client.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Configuring WebTestClient instances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [WebFluxLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [ReactiveRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/ReactiveRepresentationModelAssembler.html)
- [SimpleReactiveRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/SimpleReactiveRepresentationModelAssembler.html)
- [HypermediaWebTestClientConfigurer API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaWebTestClientConfigurer.html)
- [TypeReferences API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/TypeReferences.html)
- [Spring Framework WebTestClient Reference](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)

