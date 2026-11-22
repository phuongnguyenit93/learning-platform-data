# Luồng yêu cầu HTTP từ Controller qua dịch vụ đến Repository

Trong ứng dụng Spring WebFlux sử dụng Spring Data R2DBC, một yêu cầu HTTP thường đi qua ba lớp chính: **Controller**, **Service** và **Repository**. Controller tiếp nhận HTTP request, chuyển dữ liệu đầu vào thành tham số hoặc command; Service thực hiện quy tắc nghiệp vụ và phối hợp các thao tác; Repository truy cập database theo mô hình reactive. Kết quả đi ngược lại qua Service và Controller để WebFlux chuyển thành HTTP response.

Điểm quan trọng của luồng này là giữ publisher reactive xuyên suốt. Controller và Service trả về `Mono` hoặc `Flux`; Repository cũng trả publisher. Các lớp không tự gọi `subscribe()` hoặc `block()` để chờ kết quả. WebFlux quản lý subscription ở ranh giới xử lý request, còn Reactor phối hợp dữ liệu, lỗi, cancellation và backpressure trong pipeline.

## 1. Tổng quan kiến trúc Controller → Service → Repository

Một request đọc chi tiết sản phẩm có thể đi qua các bước:

1. Client gửi HTTP request đến endpoint.
2. WebFlux định tuyến request đến Controller.
3. Controller đọc path variable, query parameter, header hoặc request body.
4. Controller gọi Service bằng dữ liệu đã nhận.
5. Service áp dụng quy tắc nghiệp vụ và gọi Repository.
6. Repository phát truy vấn R2DBC tới database.
7. Kết quả được ánh xạ thành entity và phát qua `Mono` hoặc `Flux`.
8. Service chuyển entity thành DTO hoặc kết hợp kết quả nghiệp vụ.
9. Controller trả publisher; WebFlux ghi HTTP response khi publisher phát dữ liệu hoặc hoàn tất.

~~~mermaid
sequenceDiagram
    participant Client
    participant WebFlux as WebFlux Dispatcher
    participant C as Controller
    participant S as Service
    participant R as R2DBC Repository
    participant DB as Database
    Client->>WebFlux: HTTP request
    WebFlux->>C: Route and invoke handler
    C->>S: Call service with request data
    S->>R: Repository method
    R->>DB: R2DBC query
    DB-->>R: Rows / update result
    R-->>S: Mono or Flux
    S-->>C: Reactive result
    C-->>WebFlux: Return Mono / Flux / ResponseEntity
    WebFlux-->>Client: HTTP response
~~~

Sơ đồ thể hiện thứ tự logic. Vì publisher lazy, việc gọi một phương thức repository thường chỉ tạo publisher; câu SQL được thực thi khi WebFlux subscribe vào pipeline ở ranh giới xử lý request.

## 2. Trách nhiệm của từng lớp

| Lớp | Trách nhiệm chính | Không nên làm |
| --- | --- | --- |
| Controller | HTTP mapping, đọc input, validation đầu vào, chọn status/header và trả response | Chứa quy tắc nghiệp vụ phức tạp hoặc viết SQL |
| Service | Điều phối use case, kiểm tra quy tắc nghiệp vụ, phối hợp repository, transaction và chuyển đổi kết quả | Biết chi tiết HTTP như path/header nếu không cần |
| Repository | Truy vấn và lưu entity bằng Spring Data R2DBC | Điều phối workflow nhiều bước hoặc tạo HTTP response |
| Database | Lưu dữ liệu, thực thi constraint, transaction và query | Thay thế validation nghiệp vụ ở application layer |

Tách trách nhiệm giúp thay đổi API HTTP mà không phải viết lại logic nghiệp vụ; thay database query mà không làm Controller phụ thuộc SQL; và kiểm thử từng lớp với phạm vi rõ ràng.

## 3. Entity và Repository

Ví dụ entity Product:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price,
        String status
) {}
~~~

Repository reactive:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByStatus(String status);

    Mono<Product> findByName(String name);
}
~~~

`ReactiveCrudRepository` cung cấp các thao tác CRUD trả về publisher:

- `Mono<T>` thường dùng cho một entity hoặc kết quả đơn.
- `Flux<T>` dùng cho nhiều entity.
- `Mono<Void>` thường dùng cho thao tác chỉ cần biết hoàn tất hay lỗi.

Repository không mở một thread riêng để trả kết quả. Nó tạo publisher để driver R2DBC thực thi I/O bất đồng bộ khi có subscription.

## 4. Service điều phối use case

Service gọi repository và đặt quy tắc nghiệp vụ ở một nơi:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Mono<Product> findById(Long id) {
        return productRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)
                ));
    }

    public Flux<Product> findActiveProducts() {
        return productRepository.findByStatus("ACTIVE");
    }
}
~~~

Service chuyển trường hợp không tìm thấy thành lỗi nghiệp vụ có tên rõ ràng. Controller hoặc exception handler sẽ quyết định lỗi đó trở thành HTTP 404 như thế nào.

Không cần tạo một `Mono` mới chỉ để bọc publisher repository:

~~~java
// Không cần thiết nếu chỉ chuyển tiếp kết quả.
public Mono<Product> findById(Long id) {
    return Mono.from(productRepository.findById(id));
}
~~~

Có thể trả trực tiếp publisher nếu không có xử lý bổ sung. Dùng `map`, `flatMap`, `filter`, `switchIfEmpty` hoặc các operator khác khi cần thể hiện logic.

## 5. Controller nhận request và trả reactive response

Controller dùng annotation WebFlux:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> findById(
            @PathVariable Long id) {

        return productService.findById(id)
                .map(ResponseEntity::ok);
    }

    @GetMapping
    public Flux<Product> findActiveProducts() {
        return productService.findActiveProducts();
    }
}
~~~

Ở endpoint chi tiết, kết quả là `Mono<ResponseEntity<Product>>`. Nếu Service phát lỗi `ProductNotFoundException`, pipeline kết thúc bằng error và exception handler có thể ánh xạ sang 404.

Endpoint danh sách trả `Flux<Product>`. WebFlux có thể ghi các phần tử theo cách phù hợp với media type và cấu hình message writer. Nếu trả JSON thông thường, framework có thể mã hóa collection theo response format; nếu dùng streaming media type như NDJSON, từng phần tử có thể được phát ra khi sẵn sàng.

## 6. Luồng request body với Mono và validation

Với POST, Controller nhận body và có thể dùng Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}
~~~

DTO đầu vào tách biệt với entity database. Client không nên được phép gửi trực tiếp các trường nội bộ như ID tự sinh, trạng thái hệ thống hoặc thông tin audit nếu nghiệp vụ không cho phép.

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

@PostMapping
public Mono<ResponseEntity<Product>> create(
        @Valid @RequestBody Mono<CreateProductRequest> requestMono) {

    return requestMono
            .flatMap(productService::create)
            .map(saved -> ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(saved));
}
~~~

WebFlux giải mã request body thành DTO, áp dụng validation theo cấu hình hỗ trợ và đưa giá trị vào publisher. Service chỉ nhận command/DTO đã được Controller tiếp nhận; không cần tự đọc HTTP body.

Tùy chữ ký handler và phiên bản Spring Framework, validation có thể được khai báo với body dạng object hoặc `Mono<T>`. Hãy dùng đúng kiểu được WebFlux hỗ trợ trong phiên bản dự án và kiểm tra validation lỗi bằng integration test.

## 7. Service tạo bản ghi

Service chuyển request DTO thành entity và lưu:

~~~java
public Mono<Product> create(CreateProductRequest request) {
    Product product = new Product(
            null,
            request.name().trim(),
            request.price(),
            "ACTIVE"
    );

    return productRepository.save(product);
}
~~~

ID được để null để database/Spring Data xử lý theo mapping của entity. Trạng thái ACTIVE do service quyết định theo quy tắc ứng dụng, thay vì tin giá trị status do client gửi.

Trong thực tế, nên trả DTO response thay vì expose entity nếu entity có trường nội bộ hoặc cấu trúc database không phải hợp đồng API:

~~~java
public record ProductResponse(
        Long id,
        String name,
        BigDecimal price
) {}
~~~

Service có thể chuyển entity đã lưu thành response DTO bằng `map`.

## 8. Luồng GET: Controller → Service → Repository

Ví dụ lấy một sản phẩm:

~~~java
// Controller
@GetMapping("/{id}")
public Mono<ProductResponse> getProduct(@PathVariable Long id) {
    return productService.getProduct(id);
}

// Service
public Mono<ProductResponse> getProduct(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(product -> new ProductResponse(
                    product.id(),
                    product.name(),
                    product.price()
            ));
}
~~~

Repository trả entity hoặc Mono rỗng. Service chuyển trường hợp rỗng thành lỗi nghiệp vụ và map sang DTO. Controller chỉ khai báo route và trả publisher.

Nếu muốn trả 404 bằng `ResponseEntity` ngay trong Controller thay vì exception:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<ProductResponse>> getProduct(
        @PathVariable Long id) {

    return productService.findResponseById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Chọn một quy ước thống nhất cho ứng dụng. Exception mapping phù hợp khi not-found là lỗi nghiệp vụ dùng ở nhiều endpoint; `defaultIfEmpty` phù hợp khi Controller muốn thể hiện trực tiếp HTTP response cho kết quả không tồn tại.

## 9. Luồng POST và HTTP 201 Created

Khi tạo resource thành công, API thường trả HTTP 201 và có thể kèm Location header:

~~~java
@PostMapping
public Mono<ResponseEntity<ProductResponse>> create(
        @Valid @RequestBody Mono<CreateProductRequest> body) {

    return body.flatMap(productService::createResponse)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/products/" + saved.id()))
                    .body(saved));
}
~~~

Service:

~~~java
public Mono<ProductResponse> createResponse(
        CreateProductRequest request) {

    Product product = new Product(
            null,
            request.name().trim(),
            request.price(),
            "ACTIVE"
    );

    return productRepository.save(product)
            .map(saved -> new ProductResponse(
                    saved.id(),
                    saved.name(),
                    saved.price()
            ));
}
~~~

Location nên được xây dựng từ URI resource hợp lệ theo cấu trúc API. Với ứng dụng có base path, reverse proxy hoặc host động, có thể dùng URI builder từ request context thay vì ghép chuỗi cố định.

## 10. Luồng PUT/PATCH: đọc, kiểm tra và cập nhật

Một use case cập nhật có thể cần tải entity, xác nhận tồn tại và áp dụng các trường cho phép:

~~~java
public record UpdateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}
~~~

Service:

~~~java
public Mono<ProductResponse> update(
        Long id,
        UpdateProductRequest request) {

    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(current -> new Product(
                    current.id(),
                    request.name().trim(),
                    request.price(),
                    current.status()
            ))
            .flatMap(productRepository::save)
            .map(saved -> new ProductResponse(
                    saved.id(),
                    saved.name(),
                    saved.price()
            ));
}
~~~

Controller:

~~~java
@PutMapping("/{id}")
public Mono<ProductResponse> update(
        @PathVariable Long id,
        @Valid @RequestBody Mono<UpdateProductRequest> body) {

    return body.flatMap(request ->
            productService.update(id, request)
    );
}
~~~

Đây là mô hình đọc-sửa-ghi. Nếu nhiều request có thể cập nhật cùng lúc, hãy cân nhắc optimistic locking với `@Version`, khóa bi quan trong transaction hoặc một câu UPDATE có điều kiện. Không giả định việc gọi `findById` rồi `save` tự động ngăn lost update.

## 11. Luồng DELETE và Mono<Void>

Repository có thể xóa theo ID:

~~~java
public Mono<Void> deleteById(Long id) {
    return productRepository.deleteById(id);
}
~~~

Service có thể kiểm tra tồn tại trước nếu cần trả lỗi 404:

~~~java
public Mono<Void> delete(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .flatMap(product ->
                    productRepository.deleteById(product.id())
            );
}
~~~

Controller:

~~~java
@DeleteMapping("/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return productService.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
~~~

`Mono<Void>` biểu diễn hoàn tất hoặc lỗi, không phát entity. `thenReturn` tạo response 204 sau khi thao tác xóa hoàn tất. Nếu không cần phân biệt ID không tồn tại với đã xóa, có thể gọi trực tiếp `deleteById` theo semantics của repository.

Kiểm tra tồn tại rồi xóa có thể gặp race condition nếu bản ghi bị xóa giữa hai thao tác. Nếu cần phân biệt chính xác, có thể dùng câu DELETE trả số hàng bị ảnh hưởng qua `DatabaseClient` hoặc template và diễn giải count.

## 12. map và flatMap trong luồng Controller/Service

Hai operator thường xuất hiện trong luồng nhiều lớp:

- `map`: chuyển đổi giá trị đồng bộ thành một giá trị khác.
- `flatMap`: nhận giá trị rồi gọi một hàm trả về publisher, sau đó làm phẳng publisher lồng nhau.

Ví dụ `map`:

~~~java
Mono<ProductResponse> response = productRepository.findById(id)
        .map(product -> new ProductResponse(
                product.id(),
                product.name(),
                product.price()
        ));
~~~

Ví dụ `flatMap`:

~~~java
Mono<OrderResponse> response = orderRepository.findById(id)
        .flatMap(order ->
                customerRepository.findById(order.customerId())
                        .map(customer -> toResponse(order, customer))
        );
~~~

Nếu dùng `map` cho hàm trả publisher, kết quả sẽ thành `Mono<Mono<T>>`. `flatMap` làm phẳng để caller nhận `Mono<T>`.

Không dùng `flatMap` cho mọi phép chuyển đổi. Nếu chỉ tạo DTO từ entity, `map` rõ ràng và phù hợp hơn.

## 13. Kết hợp nhiều repository

Service có thể cần dữ liệu từ nhiều repository. Nếu các truy vấn độc lập, có thể dùng `Mono.zip`:

~~~java
public Mono<DashboardResponse> dashboard() {
    Mono<Long> productCount = productRepository.count();
    Mono<Long> orderCount = orderRepository.count();

    return Mono.zip(productCount, orderCount)
            .map(tuple -> new DashboardResponse(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
~~~

`zip` chờ các publisher phát giá trị rồi kết hợp. Nếu một publisher hoàn tất rỗng, `zip` có thể hoàn tất mà không tạo tuple; nếu một publisher phát lỗi, lỗi được truyền downstream và các subscription liên quan có thể bị hủy.

Nếu thao tác thứ hai phụ thuộc kết quả thứ nhất, dùng `flatMap`:

~~~java
public Mono<OrderResponse> findOrder(Long id) {
    return orderRepository.findById(id)
            .flatMap(order ->
                    customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer))
            );
}
~~~

Với danh sách nhiều Order, mẫu gọi customerRepository cho từng Order có thể tạo N+1 query. Khi đó, hãy dùng JOIN hoặc tải Customer theo tập ID.

## 14. Validation ở Controller và quy tắc nghiệp vụ ở Service

Validation đầu vào thường có hai tầng:

**Request validation** kiểm tra cấu trúc và giá trị đơn giản:

- Trường bắt buộc.
- Độ dài chuỗi.
- Định dạng email.
- Giá trị dương hoặc nằm trong khoảng.
- Kiểu dữ liệu và định dạng request.

**Business validation** kiểm tra ngữ cảnh nghiệp vụ:

- Khách hàng có tồn tại và còn hoạt động không?
- Sản phẩm có được phép bán không?
- Số lượng còn đủ không?
- Người dùng có quyền thực hiện thao tác không?
- Trạng thái hiện tại có cho phép chuyển sang trạng thái mới không?

Controller có thể kích hoạt Bean Validation cho request DTO. Service kiểm tra quy tắc nghiệp vụ bằng repository hoặc domain logic. Database constraint tiếp tục bảo vệ tính toàn vẹn khi có request đồng thời.

Không chỉ dựa vào kiểm tra tồn tại trong Service để bảo đảm uniqueness. Ví dụ hai request cùng kiểm tra email chưa tồn tại rồi cùng insert; unique constraint trong database mới là hàng rào cuối cùng.

## 15. Xử lý lỗi tập trung bằng RestControllerAdvice

Service nên phát lỗi nghiệp vụ có ý nghĩa:

~~~java
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

Exception handler chuyển lỗi thành HTTP response:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Mono<ApiError> handleNotFound(
            ProductNotFoundException error) {
        return Mono.just(new ApiError(
                "PRODUCT_NOT_FOUND",
                error.getMessage()
        ));
    }

    @ExceptionHandler(ServerWebInputException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Mono<ApiError> handleBadInput(
            ServerWebInputException error) {
        return Mono.just(new ApiError(
                "INVALID_REQUEST",
                "Request body or parameter is invalid"
        ));
    }
}
~~~

DTO lỗi:

~~~java
public record ApiError(String code, String message) {}
~~~

Trong ứng dụng thực tế, không nên trả stack trace, SQL, tên bảng hoặc thông tin connection cho client. Ghi chi tiết lỗi ở log nội bộ với correlation ID; response chỉ chứa thông tin phù hợp với API.

Ngoài exception do Service phát, WebFlux còn có lỗi giải mã body, binding, validation và lỗi framework. Hãy xác định handler phù hợp với các loại lỗi của phiên bản Spring đang dùng.

## 16. Transaction đặt ở Service

Một use case có nhiều thao tác database cần commit/rollback cùng nhau nên đặt transaction ở tầng Service:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                            toOrderLines(order.id(), command.items())
                    ).thenReturn(order)
            )
            .flatMap(order ->
                    auditRepository.save(toAudit(order))
                            .thenReturn(order)
            );
}
~~~

Transaction manager R2DBC phải được cấu hình phù hợp và các repository phải dùng cùng connection factory. Spring quản lý transaction reactive theo Reactor Context. Publisher cần được trả về để framework điều phối commit/rollback.

Không gọi `subscribe()` bên trong method transactional. Nếu tự subscribe, thao tác có thể tách khỏi transaction context và caller không theo dõi được lỗi hoặc kết quả.

Nếu dùng `TransactionalOperator`, có thể bao pipeline một cách tường minh:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                            toOrderLines(order.id(), command.items())
                    ).thenReturn(order)
            );

    return transactionalOperator.transactional(work);
}
~~~

Chọn annotation hoặc operator theo nhu cầu. Không bọc cùng một publisher bằng cả hai cách nếu không có chủ đích rõ ràng về propagation và transaction boundary.

## 17. Không block hoặc subscribe trong Controller/Service

Một lỗi thường gặp là chuyển reactive code thành imperative:

~~~java
// Không dùng trong WebFlux service.
public Product getProduct(Long id) {
    return productRepository.findById(id).block();
}
~~~

Hoặc:

~~~java
// Không tự subscribe trong Controller.
public void create(CreateProductRequest request) {
    productRepository.save(toProduct(request)).subscribe();
}
~~~

Các cách này có vấn đề:

- `block()` chặn thread chờ database, làm giảm khả năng phục vụ đồng thời.
- `subscribe()` tạo subscription độc lập; Controller không còn quản lý kết quả.
- Lỗi có thể xảy ra sau khi HTTP response đã được gửi.
- Transaction, cancellation và tracing có thể bị tách khỏi luồng request.
- Client không nhận được response đúng với kết quả database.

Hãy trả publisher:

~~~java
public Mono<Product> create(CreateProductRequest request) {
    return productRepository.save(toProduct(request));
}
~~~

WebFlux subscribe ở ranh giới framework và phối hợp response với publisher.

## 18. Flux và cách WebFlux ghi response

`Mono<T>` biểu diễn tối đa một phần tử; `Flux<T>` biểu diễn không, một hoặc nhiều phần tử. Với endpoint danh sách, Controller có thể trả Flux:

~~~java
@GetMapping(value = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<ProductResponse> streamProducts() {
    return productService.streamProducts();
}
~~~

NDJSON cho phép ghi từng object JSON trên một dòng khi publisher phát dữ liệu. Client có thể xử lý từng phần tử mà không cần đợi toàn bộ danh sách.

Nếu trả `application/json` thông thường, message writer có thể encode Flux thành một JSON array; response có thể cần giữ hoặc xử lý cấu trúc collection theo cách của codec. Hãy chọn media type theo hợp đồng API và khả năng client.

Streaming có lợi khi tập dữ liệu lớn, nhưng cũng có nghĩa connection HTTP có thể mở lâu. Cần giới hạn kết quả, phân trang hoặc có timeout phù hợp. Không mở một transaction database dài chỉ để giữ transaction trong toàn bộ thời gian client nhận stream nếu không thực sự cần.

## 19. Backpressure từ HTTP tới database

Reactive Streams cho phép subscriber yêu cầu số lượng phần tử theo nhu cầu. WebFlux và Reactor có thể phối hợp backpressure trong pipeline; tuy nhiên, toàn bộ stack HTTP, codec và R2DBC driver cần hỗ trợ cơ chế này theo cách phù hợp.

Ví dụ:

~~~java
public Flux<ProductResponse> streamProducts() {
    return productRepository.findAll()
            .map(this::toResponse)
            .limitRate(64);
}
~~~

`limitRate(64)` điều tiết request upstream theo từng đợt. Nó không thay thế SQL LIMIT hoặc phân trang nếu API chỉ nên trả một tập dữ liệu giới hạn. Khi dữ liệu lớn, nên đưa giới hạn xuống database bằng Query/SQL để tránh đọc quá nhiều hàng.

Nếu client ngắt kết nối, WebFlux có thể hủy subscription; cancellation truyền qua pipeline và R2DBC infrastructure có cơ hội dừng việc đọc/giải phóng connection. Việc câu SQL dừng ngay trên server phụ thuộc driver/database.

## 20. Timeout và cancellation theo request

Có thể đặt timeout cho một use case:

~~~java
public Mono<ProductResponse> findProduct(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(this::toResponse)
            .timeout(Duration.ofSeconds(3));
}
~~~

Timeout Reactor giới hạn thời gian chờ publisher; khi hết hạn, upstream bị hủy và downstream nhận lỗi timeout. Đây không nhất thiết là statement timeout phía database. Nếu cần giới hạn thời gian SQL ở server, cấu hình timeout tương ứng với driver/database.

Khi client đóng kết nối, cancellation có thể xảy ra mà không phát lỗi nghiệp vụ thông thường. Không bắt cancellation rồi tự retry vô điều kiện, vì client có thể không còn cần kết quả.

## 21. Phân biệt lỗi HTTP, lỗi nghiệp vụ và lỗi database

Không nên biến mọi exception thành HTTP 500 giống nhau:

| Nhóm lỗi | Ví dụ | HTTP mapping thường gặp |
| --- | --- | --- |
| Request invalid | JSON sai, field bắt buộc thiếu | 400 Bad Request |
| Resource không tồn tại | Product ID không có | 404 Not Found |
| Xung đột nghiệp vụ | Email đã tồn tại, trạng thái không hợp lệ | 409 Conflict |
| Không được phép | User không có quyền | 403 Forbidden |
| Database unavailable | Connection refused, pool exhausted | 503 Service Unavailable hoặc 500 theo chính sách |
| Lỗi không dự kiến | Null bug, mapping bug | 500 Internal Server Error |

Mapping phải dựa trên hợp đồng API. Không trả 404 cho mọi lỗi repository; một lỗi connection không có nghĩa resource không tồn tại. Cũng không trả SQL exception message trực tiếp cho client.

## 22. Tránh N+1 trong Service

Ví dụ:

~~~java
public Flux<OrderResponse> findOrders() {
    return orderRepository.findAll()
            .flatMap(order ->
                    customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer))
            );
}
~~~

Với 100 Order, có thể phát sinh 1 truy vấn lấy Order và 100 truy vấn lấy Customer. `flatMap` có thể chạy các truy vấn bất đồng bộ, nhưng tổng số round trip vẫn lớn.

Các lựa chọn tốt hơn:

- JOIN bằng `DatabaseClient` để tạo DTO/read model.
- Lấy Order theo trang, gom các customer ID và truy vấn Customer theo lô.
- Thiết kế query projection nếu dữ liệu response cần từ nhiều bảng.

Ví dụ JOIN:

~~~sql
SELECT o.id AS order_id,
       o.status,
       c.id AS customer_id,
       c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

Tách lớp không có nghĩa phải gọi đúng một repository cho mọi response. Service có thể dùng repository hoặc DatabaseClient tùy query shape, miễn logic nghiệp vụ vẫn ở đúng nơi.

## 23. Truyền dữ liệu giữa các lớp bằng DTO và command

Không nên dùng cùng một class cho request, entity database và response nếu các cấu trúc có mục đích khác nhau:

| Kiểu | Hướng dữ liệu | Ví dụ trường |
| --- | --- | --- |
| Request DTO | Client → Controller | name, price |
| Command | Controller → Service | name, price, actorId, context |
| Entity | Service ↔ Repository | id, name, price, status, version |
| Response DTO | Service → Controller → Client | id, name, price |

Tách kiểu dữ liệu giúp:

- Không cho client sửa các trường nội bộ.
- Tránh lộ cột nhạy cảm trong entity.
- API ổn định khi schema thay đổi.
- Validation phù hợp từng operation.
- Dễ kiểm thử và version hóa API.

Với ứng dụng nhỏ, có thể dùng một DTO cho command/response nếu hợp đồng thực sự giống nhau. Không nên tách class chỉ để tăng số lượng file mà không có khác biệt về trách nhiệm.

## 24. Logging, tracing và correlation ID

Một HTTP request đi qua nhiều lớp. Khi xảy ra lỗi, cần nối log của Controller, Service và Repository bằng correlation ID hoặc trace ID.

Những thông tin hữu ích:

- HTTP method và route template.
- Trace/correlation ID.
- Tên use case.
- Thời gian xử lý service và database.
- Loại lỗi đã phân loại.
- Trạng thái transaction hoặc retry nếu có.

Không log password, access token, dữ liệu cá nhân nhạy cảm hoặc toàn bộ request body một cách mặc định. Khi log SQL, cần tránh ghi tham số nhạy cảm.

Reactor Context có thể mang thông tin correlation/observability xuyên qua pipeline. Không dùng ThreadLocal tùy tiện để giữ request context trong reactive flow vì các operator có thể chạy trên thread khác.

## 25. Kiểm thử từng lớp

Mỗi lớp nên được kiểm thử theo trách nhiệm:

### Repository integration test

Kiểm tra mapping entity, derived query, constraint, insert/update/delete và SQL trên database thật hoặc Testcontainers.

~~~java
StepVerifier.create(productRepository.findByStatus("ACTIVE"))
        .expectNextMatches(product ->
                product.status().equals("ACTIVE")
        )
        .verifyComplete();
~~~

### Service unit test

Mock repository để kiểm tra quy tắc nghiệp vụ, trường hợp empty/error và cách phối hợp publisher. Không dùng mock để chứng minh SQL hoặc transaction database hoạt động đúng.

### Controller/WebFlux test

Dùng `WebTestClient` để gửi HTTP request và kiểm tra status, header, body, validation và exception mapping:

~~~java
webTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

Test không tìm thấy:

~~~java
webTestClient.get()
        .uri("/api/products/999")
        .exchange()
        .expectStatus().isNotFound();
~~~

### End-to-end test

Kiểm tra toàn bộ HTTP → Controller → Service → Repository → database để xác nhận cấu hình WebFlux, serialization, mapping, transaction và exception handler phối hợp đúng.

## 26. Một ví dụ luồng hoàn chỉnh

Các kiểu dữ liệu:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}

public record ProductResponse(
        Long id,
        String name,
        BigDecimal price
) {}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductResponse> create(CreateProductRequest request) {
        Product product = new Product(
                null,
                request.name().trim(),
                request.price(),
                "ACTIVE"
        );

        return repository.save(product)
                .map(saved -> new ProductResponse(
                        saved.id(),
                        saved.name(),
                        saved.price()
                ));
    }

    public Mono<ProductResponse> findById(Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)
                ))
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<ProductResponse>> create(
            @Valid @RequestBody Mono<CreateProductRequest> request) {

        return request.flatMap(service::create)
                .map(response -> ResponseEntity
                        .created(URI.create(
                                "/api/products/" + response.id()
                        ))
                        .body(response));
    }

    @GetMapping("/{id}")
    public Mono<ProductResponse> findById(@PathVariable Long id) {
        return service.findById(id);
    }
}
~~~

Luồng POST:

1. WebFlux nhận POST /api/products.
2. Body được decode thành CreateProductRequest.
3. Bean Validation kiểm tra name và price.
4. Controller chuyển request publisher cho Service.
5. Service tạo Product entity và gọi repository.save.
6. Spring Data R2DBC chuyển entity thành dữ liệu ghi và driver thực thi INSERT.
7. Database trả kết quả; entity đã lưu được phát ra.
8. Service map entity thành ProductResponse.
9. Controller tạo HTTP 201 cùng Location header.
10. WebFlux serialize response và gửi cho client.

Không lớp nào tự gọi `subscribe()`. Publisher giữ nguyên từ repository qua service tới controller, để WebFlux điều phối subscription, lỗi và cancellation.

## 27. Các lỗi thường gặp trong luồng request

1. **Controller gọi trực tiếp nhiều repository.** Quy tắc nghiệp vụ và điều phối bị phân tán khỏi Service.
2. **Service trả entity database trực tiếp cho mọi endpoint.** API bị phụ thuộc cấu trúc persistence và có thể lộ trường nội bộ.
3. **Dùng block() trong Controller/Service.** Chặn thread và làm mất lợi ích reactive.
4. **Tự subscribe() trong service.** Caller không theo dõi được kết quả và lỗi.
5. **Dùng map khi hàm trả publisher.** Tạo publisher lồng; cần flatMap.
6. **Dùng flatMap cho phép chuyển đổi thuần túy.** map đơn giản và rõ hơn.
7. **Chỉ kiểm tra uniqueness ở Java.** Request đồng thời vẫn có thể tạo trùng; cần unique constraint.
8. **Đọc rồi save mà không kiểm soát concurrency.** Có thể xảy ra lost update.
9. **Trả Flux không giới hạn cho endpoint danh sách.** Có thể tiêu thụ quá nhiều dữ liệu và giữ HTTP connection lâu.
10. **Nhầm lỗi database với not-found.** Connection failure không đồng nghĩa entity không tồn tại.
11. **Gọi repository trong vòng lặp tạo N+1.** Dùng JOIN hoặc truy vấn theo lô.
12. **Đặt transaction ở Controller cho mọi trường hợp.** Transaction thường thuộc use case ở Service.
13. **Gửi side effect ngoài database trước khi commit.** Có thể xảy ra email/message dù transaction rollback.
14. **Không xử lý cancellation.** Client ngắt kết nối có thể khiến pipeline bị hủy; không tự retry hoặc giữ resource vô hạn.
15. **Không kiểm thử HTTP boundary.** Unit test service không chứng minh routing, serialization và status code hoạt động đúng.

## Quy tắc lựa chọn nhanh

- Controller nhận HTTP input, gọi Service và trả `Mono`/`Flux`.
- Service điều phối use case, validation nghiệp vụ và transaction.
- Repository thực hiện CRUD/query reactive trên entity.
- Dùng request/response DTO để giữ API tách khỏi schema.
- Dùng `map` cho chuyển đổi đồng bộ và `flatMap` cho thao tác trả publisher.
- Dùng `switchIfEmpty` để xử lý kết quả không có dữ liệu theo quy tắc nghiệp vụ.
- Dùng `@Transactional` hoặc `TransactionalOperator` ở Service khi nhiều thao tác phải commit/rollback cùng nhau.
- Không gọi `block()` hoặc `subscribe()` trong Controller/Service.
- Dùng JOIN hoặc query theo lô để tránh N+1.
- Giới hạn hoặc phân trang `Flux` khi tập dữ liệu lớn.
- Ánh xạ lỗi nghiệp vụ sang HTTP status bằng exception handler.
- Kiểm thử repository, service và HTTP endpoint ở đúng tầng.

Luồng Controller → Service → Repository giúp phân chia rõ ranh giới HTTP, nghiệp vụ và persistence trong ứng dụng Spring WebFlux kết hợp Spring Data R2DBC. Controller tiếp nhận và trả HTTP response; Service phối hợp quy tắc nghiệp vụ, publisher và transaction; Repository truy cập database qua R2DBC. Khi giữ `Mono`/`Flux` xuyên suốt, dùng DTO phù hợp, xử lý lỗi có chủ đích và để WebFlux quản lý subscription, ứng dụng có thể tận dụng I/O bất đồng bộ mà vẫn giữ mã nguồn dễ đọc, dễ kiểm thử và dễ mở rộng.
