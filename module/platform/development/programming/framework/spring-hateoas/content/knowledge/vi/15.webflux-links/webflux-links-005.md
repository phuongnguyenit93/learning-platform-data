# Base URI reactive

Trong ứng dụng Spring WebFlux, base URI của một liên kết hypermedia thường được xác định từ request hiện tại. Base URI bao gồm thông tin gốc mà client dùng để truy cập ứng dụng, như scheme, host, port và context path. Spring HATEOAS cung cấp `WebFluxLinkBuilder` để lấy ngữ cảnh request theo cách tương thích với Reactor, sau đó kết hợp base URI đó với mapping của controller để tạo `Link`.

Điểm quan trọng của cách làm reactive là request context được truyền qua Reactor Context và `ServerWebExchange`. Vì vậy, quá trình tạo liên kết cần được ghép vào pipeline `Mono` hoặc `Flux`. Khi ứng dụng chạy sau reverse proxy, `ForwardedHeaderTransformer` giúp WebFlux nhận diện địa chỉ công khai mà proxy chuyển tiếp, để các liên kết tuyệt đối trỏ đúng host và scheme bên ngoài.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích base URI được hình thành từ request WebFlux như thế nào.
- Phân biệt cách tạo link của `WebFluxLinkBuilder` với `WebMvcLinkBuilder`.
- Dùng `linkTo()` và `methodOn()` trong pipeline reactive.
- Lấy `ServerWebExchange` từ Reactor Context hoặc truyền tường minh.
- Tạo `EntityModel` và `CollectionModel` có liên kết bằng `Mono` và `Flux`.
- Cấu hình forwarded headers để tạo URI công khai sau reverse proxy.
- Kiểm thử base URI và liên kết bằng `WebTestClient`.

## Base URI trong một request WebFlux

Giả sử client gọi API tại địa chỉ:

```text
https://api.example.test/store/orders/42
```

Các thành phần của URI gồm:

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| Scheme | `https` | Giao thức mà client sử dụng |
| Host | `api.example.test` | Tên máy chủ công khai |
| Port | `443` hoặc port được chỉ định | Cổng truy cập |
| Context path | `/store` | Tiền tố ứng dụng nếu có |
| Path | `/orders/42` | Mapping tài nguyên cụ thể |

Base URI của request có thể được hiểu là phần gốc `https://api.example.test/store`; mapping `/orders/42` được ghép vào để tạo URI đầy đủ cho liên kết `self`.

Trong môi trường chạy trực tiếp, địa chỉ gốc có thể lấy từ request mà WebFlux nhận được. Khi có reverse proxy, địa chỉ mà ứng dụng nhìn thấy ở tầng mạng có thể là `http://orders-service:8080`, trong khi client truy cập `https://api.example.test/store`. Nếu không xử lý forwarded headers, link tạo ra có thể công bố host hoặc scheme nội bộ và client bên ngoài không thể truy cập theo liên kết đó.

## Vì sao WebFlux cần cách tạo link reactive?

Spring MVC chạy trên Servlet API và thường dùng thông tin request hiện tại để xây dựng URI. WebFlux có mô hình xử lý khác: request được biểu diễn bởi `ServerWebExchange`, còn ngữ cảnh thực thi được truyền trong Reactor Context. Không nên dựa vào ThreadLocal hoặc giả định rằng request luôn được xử lý trên cùng một thread.

Spring HATEOAS cung cấp hai builder tương ứng với hai web stack:

| Web stack | Link builder | Ngữ cảnh request |
|---|---|---|
| Spring MVC | `WebMvcLinkBuilder` | Servlet request hiện tại |
| Spring WebFlux | `WebFluxLinkBuilder` | `ServerWebExchange` trong Reactor Context hoặc được truyền tường minh |

`WebFluxLinkBuilder` nằm trong package `org.springframework.hateoas.server.reactive`. API này tạo liên kết bất đồng bộ và trả kết quả dưới dạng `Mono<Link>`, để việc tạo link có thể kết hợp với các thao tác reactive khác.

Không nên dùng `WebMvcLinkBuilder` trong controller WebFlux. Hai builder có cách lấy request context khác nhau; dùng đúng builder giúp URI phản ánh request đang được xử lý.

## Các API chính của `WebFluxLinkBuilder`

| API | Vai trò |
|---|---|
| `WebFluxLinkBuilder.methodOn(Controller.class)` | Tạo proxy mô tả lời gọi tới phương thức controller |
| `WebFluxLinkBuilder.linkTo(invocation)` | Tạo builder và tìm `ServerWebExchange` trong Reactor Context |
| `WebFluxLinkBuilder.linkTo(invocation, exchange)` | Tạo builder với `ServerWebExchange` được truyền tường minh |
| `withSelfRel()` | Tạo link với relation `self` |
| `withRel("name")` | Tạo link với relation được chỉ định |
| `andAffordance(invocation)` | Bổ sung mô tả hành động từ một phương thức controller |
| `toMono()` | Trả `Mono<Link>` để tiếp tục pipeline reactive |

Hai overload của `linkTo` giải quyết hai tình huống khác nhau:

- Dùng `linkTo(invocation)` khi request context đã có trong Reactor Context của pipeline.
- Dùng `linkTo(invocation, exchange)` khi handler đang có `ServerWebExchange` và muốn truyền rõ ngữ cảnh đó.

Nếu không tìm thấy exchange trong Reactor Context, `linkTo(invocation)` có thể tạo URI tương đối. Vì vậy, nếu hợp đồng API yêu cầu link tuyệt đối, hãy bảo đảm link được tạo trong request context hoặc truyền exchange tường minh.

## Tạo link trong pipeline `Mono`

Ví dụ dưới đây dùng API đọc chi tiết một đơn hàng. Repository hoặc service trả về `Mono<Order>`, sau đó controller tạo liên kết `self` trong cùng pipeline:

```java
import reactor.core.publisher.Mono;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<EntityModel<OrderView>> one(@PathVariable long id) {
        return orders.findById(id)
            .flatMap(order -> linkTo(methodOn(OrderController.class).one(id))
                .withSelfRel()
                .toMono()
                .map(self -> EntityModel.of(OrderView.from(order), self)));
    }
}
```

`methodOn(OrderController.class).one(id)` mô tả handler cần tham chiếu. `linkTo(...)` đọc mapping controller và tìm request context từ Reactor Context. `withSelfRel()` chọn relation chuẩn `self`; `toMono()` cung cấp `Mono<Link>`. Sau đó `map(...)` kết hợp link với DTO để tạo `EntityModel<OrderView>`.

Việc gọi `linkTo` bên trong `flatMap` giúp quá trình tạo link diễn ra trong lúc pipeline xử lý request. Không cần gọi `block()` để chờ link và cũng không cần tự gọi `subscribe()` trong controller. Hãy trả publisher để WebFlux điều phối việc subscribe và truyền Reactor Context.

Các kiểu dữ liệu và service contract tối giản dùng trong những ví dụ tiếp theo:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record Order(long id, String status) {
    boolean canCancel() {
        return status.equals("NEW") || status.equals("SUBMITTED");
    }
}

record OrderView(long id, String status) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.status());
    }
}

interface OrderService {
    Mono<Order> findById(long id);
    Flux<Order> findAll();
    Mono<Void> cancel(long id);
}
```

## Tạo liên kết cho tập hợp bằng `Flux`

Với endpoint danh sách, service trả về `Flux<Order>`. Controller có thể chuyển từng đơn hàng thành `EntityModel`, thu thập các model vào danh sách rồi tạo liên kết `self` cho `CollectionModel`:

```java
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@GetMapping
Mono<CollectionModel<EntityModel<OrderView>>> all() {
    return orders.findAll()
        .flatMap(this::toModel)
        .collectList()
        .flatMap(items -> linkTo(methodOn(OrderController.class).all())
            .withSelfRel()
            .toMono()
            .map(self -> CollectionModel.of(items, self)));
}

private Mono<EntityModel<OrderView>> toModel(Order order) {
    return linkTo(methodOn(OrderController.class).one(order.id()))
        .withSelfRel()
        .toMono()
        .map(self -> EntityModel.of(OrderView.from(order), self));
}
```

`flatMap(this::toModel)` chuyển mỗi domain object thành model cùng liên kết riêng. `collectList()` gom các model thành một danh sách khi luồng hoàn tất. Sau đó controller tạo link cấp collection và bọc danh sách bằng `CollectionModel`.

Nếu số phần tử rất lớn, không nên thu thập toàn bộ dữ liệu bằng `collectList()` mà không có giới hạn. Hãy dùng phân trang hoặc streaming response phù hợp với hợp đồng API. Với kết quả phân trang từ Spring Data, có thể chuyển dữ liệu và metadata thành `PagedModel` bằng cơ chế assembler phù hợp; việc tạo các link trong WebFlux vẫn cần request context reactive.

## Công bố hành động có điều kiện

Một representation có thể công bố liên kết `cancel` khi trạng thái đơn hàng cho phép hủy. Cả liên kết `self` và `cancel` đều được tạo dưới dạng `Mono<Link>` rồi ghép vào cùng model:

```java
private Mono<EntityModel<OrderView>> toModel(Order order) {
    return linkTo(methodOn(OrderController.class).one(order.id()))
        .withSelfRel()
        .toMono()
        .flatMap(self -> {
            EntityModel<OrderView> model = EntityModel.of(
                OrderView.from(order), self
            );

            if (!order.canCancel()) {
                return Mono.just(model);
            }

            return linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel")
                .toMono()
                .map(cancel -> {
                    model.add(cancel);
                    return model;
                });
        });
}
```

Điều kiện `canCancel()` là quy tắc nghiệp vụ minh họa. Trong ứng dụng thật, việc công bố link còn có thể phụ thuộc quyền của người dùng. Server vẫn phải kiểm tra trạng thái và quyền tại thời điểm xử lý request hủy, vì tài nguyên có thể thay đổi sau khi client đọc representation.

Endpoint thao tác có thể trả `Mono<ResponseEntity<Void>>`:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/{id}/cancellation")
Mono<ResponseEntity<Void>> cancel(@PathVariable long id) {
    return orders.cancel(id)
        .thenReturn(ResponseEntity.noContent().build());
}
```

`thenReturn` đợi thao tác reactive hoàn tất rồi phát response `204 No Content`. Nếu nghiệp vụ cần trả trạng thái mới của đơn hàng, service có thể trả `Mono<Order>` và controller chuyển kết quả đó thành representation mới có liên kết phù hợp.

## Truyền `ServerWebExchange` tường minh

Trong một số trường hợp, bạn muốn chỉ định rõ request exchange dùng làm base URI. WebFlux cho phép inject `ServerWebExchange` vào tham số handler. Sau đó dùng overload `linkTo(invocation, exchange)`:

```java
import org.springframework.web.server.ServerWebExchange;

import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.linkTo;
import static org.springframework.hateoas.server.reactive.WebFluxLinkBuilder.methodOn;

@GetMapping("/{id}/share")
Mono<EntityModel<OrderView>> share(
        @PathVariable long id,
        ServerWebExchange exchange) {

    return orders.findById(id)
        .flatMap(order -> linkTo(
                methodOn(OrderController.class).one(id), exchange)
            .withRel("order")
            .toMono()
            .map(orderLink -> EntityModel.of(OrderView.from(order), orderLink)));
}
```

Request tới `/orders/42/share` cung cấp exchange hiện tại. Builder dùng base URI từ exchange đó nhưng mapping đích từ phương thức `one(id)`, nên liên kết `order` trỏ tới endpoint chi tiết `/orders/42`. Cách truyền tường minh hữu ích khi bạn muốn tránh phụ thuộc vào việc tự tìm exchange trong Reactor Context hoặc khi đang xây dựng một helper nhận exchange làm tham số.

Không lưu `ServerWebExchange` vào singleton hoặc biến toàn cục. Exchange thuộc về một request cụ thể và không được dùng lại cho request khác. Nếu cần tạo liên kết ngoài vòng đời request, hãy xác định base URI công khai từ cấu hình đáng tin cậy và xử lý riêng theo ngữ cảnh tác vụ đó.

## Base URI khi ứng dụng chạy sau reverse proxy

Trong triển khai thực tế, proxy có thể nhận request công khai rồi chuyển tiếp đến WebFlux bằng địa chỉ nội bộ. Ví dụ:

```text
Client
  https://api.example.test/store/orders/42
          |
          v
Reverse proxy
  http://orders-service:8080/orders/42
          |
          v
Spring WebFlux
```

Proxy có thể gửi các header như `Forwarded` hoặc `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix` để mô tả địa chỉ mà client thực sự sử dụng. Spring Framework không mặc định tin các header này vì chúng có thể làm thay đổi root URI được ứng dụng công bố. Ứng dụng cần bật xử lý forwarded headers khi hạ tầng proxy được kiểm soát và cấu hình đúng.

Với Spring WebFlux, thành phần xử lý tương ứng là `ForwardedHeaderTransformer`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
class WebFluxForwardedHeaderConfiguration {

    @Bean
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        // false: sử dụng nhóm header X-Forwarded-*.
        ForwardedHeaderTransformer transformer = new ForwardedHeaderTransformer(false);
        transformer.setUseForwardedPrefix(true);
        return transformer;
    }
}
```

Constructor nhận `false` để chọn nhóm header `X-Forwarded-*`; truyền `true` nếu proxy sử dụng header chuẩn `Forwarded`. `X-Forwarded-Prefix` được bật riêng bằng `setUseForwardedPrefix(true)`. API constructor có tham số này và tùy chọn prefix phụ thuộc phiên bản Spring Framework; hãy đối chiếu phiên bản mà Spring Boot của dự án quản lý. Với cấu hình Spring Boot, cũng có thể bật chiến lược `server.forward-headers-strategy=framework`; khi cần xử lý prefix, xác nhận transformer được cấu hình để chấp nhận header prefix.

Sau khi transformer được áp dụng, WebFlux sử dụng thông tin forwarded đã được biến đổi khi tạo request URI. Ví dụ proxy chuyển tiếp:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 8443
X-Forwarded-Prefix: /store
```

thì link có thể được tạo thành:

```text
https://api.example.test:8443/store/orders/42
```

Chỉ bật xử lý forwarded headers khi proxy đáng tin cậy loại bỏ hoặc ghi đè các header do client gửi vào và tự thiết lập giá trị chính xác. Nếu ứng dụng chấp nhận trực tiếp header giả mạo từ client, kẻ tấn công có thể khiến API phát ra link với host hoặc scheme do họ kiểm soát.

## URI tương đối khi không có request context

`WebFluxLinkBuilder.linkTo(invocation)` tìm `ServerWebExchange` trong Reactor Context. Nếu không có exchange, builder có thể tạo URI tương đối. Ví dụ link có thể chỉ là `/orders/42` thay vì `https://api.example.test/orders/42`.

URI tương đối có thể phù hợp với một số hợp đồng API vì client giải quyết nó dựa trên URI của representation hiện tại. Tuy nhiên, nếu client hoặc hệ thống tích hợp cần URI tuyệt đối, hãy kiểm tra response trong đúng môi trường request và cấu hình forwarded headers.

Các tình huống có thể không có request context gồm:

- Tác vụ theo lịch chạy độc lập với HTTP request.
- Xử lý message từ broker.
- Công việc nền tạo email hoặc thông báo chứa link.
- Unit test gọi builder ngoài pipeline WebFlux.

Trong các trường hợp đó, không nên giả định `WebFluxLinkBuilder` có thể tự biết public host. Hãy dùng base URI được cấu hình rõ ràng cho môi trường, hoặc tạo link bằng một cơ chế nhận URI gốc tường minh. Tránh lấy host từ dữ liệu không đáng tin cậy.

## Kiểm thử base URI bằng `WebTestClient`

`WebTestClient` có thể gửi request đến controller WebFlux và xác nhận link trong response. Ví dụ tích hợp dưới đây kiểm tra base URI được tạo từ forwarded headers:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderBaseUriIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void buildsLinkFromForwardedPublicOrigin() {
        webTestClient.get()
            .uri("/orders/42")
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "api.example.test")
            .header("X-Forwarded-Port", "8443")
            .header("X-Forwarded-Prefix", "/store")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$._links.self.href")
            .isEqualTo("https://api.example.test:8443/store/orders/42");
    }
}
```

Test cần chạy với cấu hình `ForwardedHeaderTransformer` đã đăng ký và dữ liệu đơn hàng 42 có sẵn. Nếu dùng `@WebFluxTest` thay cho test tích hợp, hãy import cấu hình transformer và cung cấp mock cho `OrderService`. Nếu không kiểm tra forwarded headers, có thể xác nhận phần path của link và để host/port phụ thuộc vào cấu hình WebTestClient.

Nên bổ sung các trường hợp kiểm thử:

- Request bình thường tạo link theo scheme và host mà WebFlux nhận được.
- Request qua proxy tạo link theo forwarded scheme, host, port và prefix.
- Khi không có exchange, builder tạo URI tương đối như mong đợi.
- Link `self` và link hành động trỏ tới mapping chính xác.
- Các request khác nhau không dùng nhầm base URI của nhau.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `WebMvcLinkBuilder` trong WebFlux | Builder dựa trên Servlet request context không phù hợp | Dùng `WebFluxLinkBuilder` |
| Gọi `.block()` để lấy link | Chặn thread trong pipeline reactive | Dùng `.toMono()`, `map` và `flatMap` |
| Gọi `subscribe()` bên trong controller | Tách thao tác khỏi vòng đời request và làm mất kiểm soát lỗi | Trả `Mono` hoặc `Flux` cho WebFlux |
| Tạo link khi không có Reactor Context nhưng mong đợi URL tuyệt đối | Builder có thể trả URI tương đối | Tạo link trong request pipeline hoặc truyền `ServerWebExchange` |
| Không xử lý forwarded headers | Link có thể chứa host nội bộ hoặc sai scheme | Cấu hình `ForwardedHeaderTransformer` ở sau proxy đáng tin cậy |
| Tin forwarded headers từ mọi client | Có nguy cơ tạo link với host do client giả mạo | Chỉ tin header do proxy kiểm soát và ghi đè |
| Lưu `ServerWebExchange` để dùng lại | Dùng nhầm request context giữa các request | Chỉ dùng exchange trong request hiện tại |
| Tạo link trong tác vụ nền mà không cấu hình base URI | Không có public origin để xây URI tuyệt đối | Dùng base URI cấu hình rõ ràng cho tác vụ nền |

## Ghi nhớ

Trong Spring WebFlux, base URI được xác định từ `ServerWebExchange` gắn với request hiện tại. `WebFluxLinkBuilder.linkTo(invocation)` tìm exchange trong Reactor Context và có thể tạo URI tương đối nếu không có context; overload `linkTo(invocation, exchange)` cho phép truyền exchange tường minh. Kết quả link được đưa vào pipeline qua `toMono()` để kết hợp với `Mono` và `Flux` mà không chặn thread. Khi chạy sau reverse proxy, `ForwardedHeaderTransformer` giúp WebFlux nhận diện public scheme, host, port và prefix để tạo link đúng địa chỉ bên ngoài. Hãy chỉ tin forwarded headers từ proxy đáng tin cậy và kiểm thử link trong môi trường triển khai tương ứng.

## Tài liệu tham khảo

- [Spring HATEOAS – WebFluxLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/WebFluxLinkBuilder.html)
- [Spring HATEOAS – Forwarded header handling](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.forwarded-headers)
- [Spring Framework – ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html)
