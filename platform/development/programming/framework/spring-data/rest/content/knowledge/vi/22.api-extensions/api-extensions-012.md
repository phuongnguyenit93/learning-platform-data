# Ranh giới giữa mở rộng Spring Data REST và chuyển sang API dùng DTO riêng

## Bối cảnh

Spring Data REST có thể xuất bản Spring Data repository thành REST API với collection resource, item resource, association link, phân trang, sắp xếp và hypermedia. Cách này giúp tạo API CRUD nhanh, nhất quán và giảm lượng controller phải viết thủ công.

Tuy nhiên, repository và domain model được thiết kế cho persistence và nghiệp vụ bên trong ứng dụng. Chúng không phải lúc nào cũng là hợp đồng API phù hợp cho mọi client. Khi API cần một hình dạng dữ liệu khác, quy trình nghiệp vụ nhiều bước, quyền truy cập theo ngữ cảnh hoặc phải giữ tương thích lâu dài, việc tiếp tục mở rộng trực tiếp repository resource có thể làm ranh giới giữa domain và API trở nên khó kiểm soát.

Có ba hướng thường dùng:

1. **Tiếp tục dùng Spring Data REST** khi CRUD resource phản ánh đúng domain và hợp đồng công khai.
2. **Mở rộng Spring Data REST** khi vẫn muốn giữ hypermedia/repository resource nhưng cần thêm metadata, projection, validation, event handling hoặc một thao tác gắn chặt với resource hiện có.
3. **Tạo API riêng với DTO** khi client cần hợp đồng độc lập với entity, use case có orchestration rõ ràng hoặc representation không còn phù hợp với mô hình repository.

Không có quy tắc rằng DTO luôn tốt hơn entity hoặc custom controller luôn tốt hơn Spring Data REST. Quyết định nên dựa vào hợp đồng API, mức độ phức tạp của use case, bảo mật, khả năng thay đổi và chi phí bảo trì.

## 1. Bắt đầu từ ranh giới domain và hợp đồng API

Hãy phân biệt ba lớp:

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain model | Mô hình trạng thái và quy tắc nghiệp vụ | Order, Customer, OrderLine |
| Persistence model | Cách lưu và truy vấn dữ liệu | JPA entity, repository, association |
| API contract | Dữ liệu và thao tác mà client được phép sử dụng | JSON response, request DTO, HAL links |

Trong ứng dụng đơn giản, ba lớp này có thể trông gần giống nhau. Spring Data REST tận dụng điều đó để xuất bản repository trực tiếp. Nhưng khi hệ thống phát triển, các lớp thường có lý do thay đổi khác nhau:

- Entity thay đổi vì schema, quan hệ hoặc tối ưu truy vấn.
- Domain thay đổi vì nghiệp vụ.
- API thay đổi theo nhu cầu client, phiên bản, quy định bảo mật hoặc khả năng tương thích.

Nếu API công khai phụ thuộc trực tiếp vào mọi thay đổi của entity, một refactor persistence có thể vô tình trở thành breaking change đối với client.

Ví dụ, entity Order có thể chứa customer, internalNote, paymentToken và danh sách line items. Client công khai chỉ cần orderNumber, trạng thái, tổng tiền và ngày tạo. Việc trả nguyên entity khiến API phải kiểm soát rất chặt trường nào được serialize và có nguy cơ để lộ dữ liệu nội bộ.

DTO tạo một hợp đồng tường minh:

    public record OrderSummaryDto(
        Long id,
        String orderNumber,
        String status,
        BigDecimal total,
        Instant createdAt
    ) {}

API có thể trả đúng các trường cần thiết mà không buộc client phụ thuộc vào cấu trúc entity.

## 2. Khi nào nên giữ Spring Data REST?

Giữ repository resource khi các điều kiện sau phần lớn đúng:

- Resource gần với aggregate/domain object mà repository quản lý.
- CRUD chuẩn là cách client tương tác chủ yếu.
- Các association link phản ánh đúng quan hệ mà client cần khám phá.
- Phân trang, sắp xếp, search resource và hypermedia đã đáp ứng nhu cầu.
- Quyền đọc/ghi có thể biểu diễn rõ ở cấp repository, domain và security.
- Không cần biến một request thành chuỗi nghiệp vụ phức tạp.
- Hình dạng representation có thể được kiểm soát mà không làm lộ persistence detail.

Ví dụ, một ứng dụng nội bộ quản lý danh mục sản phẩm có thể phù hợp với repository resource:

    @RepositoryRestResource(
        path = "products",
        collectionResourceRel = "products"
    )
    public interface ProductRepository
            extends JpaRepository<Product, Long> {
    }

Client có thể khám phá collection, đọc item, theo association link và dùng paging/sorting mà không cần controller CRUD thủ công.

Một dấu hiệu tốt để giữ Spring Data REST là client thực sự hưởng lợi từ hypermedia và thao tác chủ yếu là đọc/ghi tài nguyên. Nếu mọi client đều phải gọi một tập endpoint được thiết kế thủ công và không dùng các link/metadata của repository resource, lợi ích của việc xuất bản repository có thể không còn lớn.

## 3. Những cách mở rộng vẫn nằm trong Spring Data REST

Trước khi tạo API hoàn toàn riêng, hãy xem yêu cầu có thể giải quyết bằng cơ chế mở rộng hiện có hay không.

### 3.1 Projection cho representation đọc

Projection cho phép công bố một góc nhìn giới hạn của resource mà không cần thay đổi entity:

    @Projection(
        name = "summary",
        types = Product.class
    )
    public interface ProductSummary {

        String getName();

        BigDecimal getPrice();

        String getCategory();
    }

Client có thể yêu cầu projection qua tham số `projection` nếu projection được công bố theo cấu hình Spring Data REST:

    GET /products/42?projection=summary

Projection phù hợp khi:

- Chỉ cần chọn tập trường khác nhau cho representation đọc.
- Cấu trúc vẫn là góc nhìn của cùng một resource.
- Không cần tính toán nghiệp vụ hoặc phối hợp nhiều nguồn dữ liệu phức tạp.
- Có thể chấp nhận cách thức projection của Spring Data REST.

Projection không tự trở thành một write DTO. Nó không thay thế validation đầu vào, authorization hay một command model riêng. Với response có cấu trúc hoàn toàn khác hoặc phải tổng hợp nhiều aggregate, DTO chuyên biệt thường rõ ràng hơn.

### 3.2 Excerpt projection

Excerpt projection có thể dùng để định nghĩa representation mặc định cho các item được nhúng trong collection resource. Đây là lựa chọn hữu ích khi collection cần hiển thị ít trường hơn item detail.

    @RepositoryRestResource(
        path = "products",
        excerptProjection = ProductSummary.class
    )
    public interface ProductRepository
            extends JpaRepository<Product, Long> {
    }

Hãy xác định rõ client cần summary cho collection hay cần một API tổng hợp riêng. Excerpt projection giải quyết hình dạng representation của repository resource, không phải một quy trình nghiệp vụ.

### 3.3 Resource processor và hypermedia link

Nếu resource đã phù hợp nhưng cần bổ sung link hoặc metadata dẫn đường, có thể dùng `RepresentationModelProcessor`:

    @Component
    public class ProductModelProcessor
            implements RepresentationModelProcessor<EntityModel<Product>> {

        @Override
        public EntityModel<Product> process(
                EntityModel<Product> model) {

            model.add(Link.of("/catalog/help")
                    .withRel("catalog-help"));

            return model;
        }
    }

Ví dụ chỉ minh họa ý tưởng thêm link; trong ứng dụng thực tế, nên tạo link theo cơ chế URI builder/hypermedia phù hợp để tránh hard-code host hoặc base path.

Resource processor phù hợp khi cần làm giàu representation bằng link, affordance hoặc metadata. Nó không nên trở thành nơi thực hiện nghiệp vụ ghi dữ liệu hoặc truy vấn tổng hợp nặng.

### 3.4 Repository event handler

Spring Data REST có các repository event handler như `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleAfterCreate` và `@HandleAfterSave`.

Ví dụ:

    @Component
    public class ProductEventHandler {

        @HandleBeforeCreate
        public void beforeCreate(Product product) {
            product.normalizeName();
        }
    }

Event handler hữu ích cho logic gắn trực tiếp với vòng đời lưu repository, chẳng hạn chuẩn hóa một giá trị hoặc kiểm tra điều kiện đơn giản.

Không nên đưa toàn bộ use case vào event handler. Nếu một thao tác cần phối hợp nhiều repository, gọi dịch vụ thanh toán, phát sự kiện, kiểm soát transaction và trả kết quả riêng, application service với API DTO thường minh bạch hơn.

### 3.5 Custom controller trong vùng Spring Data REST

Khi vẫn muốn bổ sung một endpoint gắn với repository resource và cách định tuyến của Spring Data REST, có thể cân nhắc `@RepositoryRestController`. Cơ chế này phù hợp cho phần mở rộng nhỏ trong cùng mô hình hypermedia.

Ví dụ khái niệm:

    @RepositoryRestController
    public class ProductRestController {

        private final ProductService productService;

        public ProductRestController(ProductService productService) {
            this.productService = productService;
        }

        // Endpoint bổ sung được ánh xạ trong base path
        // của Spring Data REST theo cấu hình ứng dụng.
    }

Custom controller vẫn phải có ranh giới rõ. Nếu endpoint có hợp đồng độc lập, DTO riêng, versioning riêng và workflow lớn, một `@RestController` ở API layer thường dễ hiểu hơn việc cố đặt mọi thứ trong namespace repository.

## 4. Khi nào nên chuyển sang API riêng dùng DTO?

Nên cân nhắc custom API khi một hoặc nhiều dấu hiệu sau xuất hiện:

### 4.1 Representation khác xa entity

Client cần response tổng hợp từ nhiều aggregate, nhiều repository hoặc nhiều hệ thống:

    {
      "orderId": 42,
      "customer": {
        "displayName": "An Nguyen"
      },
      "items": [
        {
          "productName": "Keyboard",
          "quantity": 2
        }
      ],
      "payment": {
        "displayStatus": "PAID"
      },
      "availableActions": [
        "cancel",
        "download-invoice"
      ]
    }

Đây là một view model cho use case. Nó không nhất thiết tương ứng với một entity hay repository cụ thể. DTO giúp đặt tên và định nghĩa cấu trúc response theo nhu cầu client.

### 4.2 Request là một command, không phải cập nhật entity

Ví dụ người dùng xác nhận đơn hàng:

    public record ConfirmOrderRequest(
        String confirmationCode,
        String note
    ) {}

    public record ConfirmOrderResponse(
        Long orderId,
        String status,
        Instant confirmedAt
    ) {}

Endpoint:

    POST /api/v1/orders/42/confirm

Đây là một command nghiệp vụ. Client không nên gửi toàn bộ entity Order để yêu cầu chuyển trạng thái. Application service kiểm tra quyền, trạng thái hiện tại, mã xác nhận và các điều kiện khác rồi thực hiện transition.

### 4.3 Cần điều phối nhiều bước hoặc nhiều aggregate

Một request có thể cần:

1. Tải Order.
2. Kiểm tra trạng thái và quyền của người dùng.
3. Xác minh tồn kho.
4. Gọi dịch vụ thanh toán.
5. Cập nhật trạng thái Order.
6. Ghi audit và phát domain event.
7. Trả kết quả theo hợp đồng của use case.

Đây là orchestration của application layer. Để logic này trong repository event handler hoặc setter của entity khiến luồng xử lý khó quan sát và khó kiểm thử.

### 4.4 Cần kiểm soát input/output chặt chẽ

DTO cho phép xác định rõ:

- Trường nào client được gửi.
- Trường nào server tự tính.
- Trường nào chỉ xuất hiện trong response.
- Validation theo use case.
- Giá trị mặc định và quy tắc tương thích.
- Cách biểu diễn lỗi.

Điều này đặc biệt hữu ích với dữ liệu nhạy cảm, trường nội bộ, trường chỉ đọc hoặc những thao tác có side effect.

### 4.5 Cần versioning và tương thích client độc lập

Một API công khai có thể cần duy trì `/api/v1` trong khi entity tiếp tục thay đổi. DTO cho phép giữ hợp đồng v1 ổn định và triển khai v2 với representation khác mà không phải giữ nguyên cấu trúc persistence.

### 4.6 Cần query hoặc hiệu năng chuyên biệt

Một dashboard có thể cần phép tổng hợp, projection SQL, read model hoặc cache khác hẳn repository CRUD. API DTO có thể gọi query service tối ưu cho use case đó thay vì ép repository resource trả về một graph entity lớn.

## 5. Thiết kế API riêng với DTO

Một custom API thường có cấu trúc:

    @RestController
    @RequestMapping("/api/v1/orders")
    public class OrderApiController {

        private final OrderApplicationService orderService;

        public OrderApiController(
                OrderApplicationService orderService) {
            this.orderService = orderService;
        }

        @GetMapping("/{id}")
        public OrderDetailDto getOrder(@PathVariable Long id) {
            return orderService.getDetail(id);
        }

        @PostMapping("/{id}/confirm")
        public ConfirmOrderResponse confirm(
                @PathVariable Long id,
                @Valid @RequestBody ConfirmOrderRequest request) {
            return orderService.confirm(id, request);
        }
    }

Controller chịu trách nhiệm HTTP: route, status code, request binding và response. Application service điều phối use case. Repository vẫn là cổng truy cập dữ liệu.

Một cấu trúc package minh họa:

    order/
      api/
        OrderApiController.java
        OrderDetailDto.java
        ConfirmOrderRequest.java
        ConfirmOrderResponse.java
      application/
        OrderApplicationService.java
      domain/
        Order.java
        OrderStatus.java
      persistence/
        OrderRepository.java

Đây là cách phân lớp tham khảo; có thể tổ chức theo feature hoặc module tùy kiến trúc hiện có. Điều quan trọng là API không phải nơi trực tiếp thao tác tùy tiện với persistence.

## 6. Mapping giữa entity và DTO

Mapping nên được thực hiện tại ranh giới application/API bằng code tường minh hoặc mapper có kiểm soát.

Ví dụ:

    public record OrderDetailDto(
        Long id,
        String orderNumber,
        String status,
        BigDecimal total
    ) {}

    public final class OrderMapper {

        private OrderMapper() {
        }

        public static OrderDetailDto toDetail(Order order) {
            return new OrderDetailDto(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus().name(),
                order.getTotal()
            );
        }
    }

Application service:

    @Service
    public class OrderApplicationService {

        private final OrderRepository repository;

        public OrderApplicationService(OrderRepository repository) {
            this.repository = repository;
        }

        @Transactional(readOnly = true)
        public OrderDetailDto getDetail(Long id) {
            Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

            return OrderMapper.toDetail(order);
        }
    }

Mapping tường minh giúp người đọc thấy chính xác trường nào được đưa ra ngoài. Với mapping lớn, có thể dùng MapStruct hoặc công cụ tương tự, nhưng vẫn cần review mapping như một phần của hợp đồng API.

Tránh trả JPA entity trực tiếp từ custom API chỉ để tiết kiệm vài dòng code. Lazy loading, quan hệ hai chiều, vòng tham chiếu JSON, field nhạy cảm và thay đổi schema đều có thể làm response khó kiểm soát.

## 7. Validation và lỗi ở API DTO

Request DTO có thể dùng Jakarta Bean Validation:

    public record CreateProductRequest(
        @NotBlank
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
    ) {}

Controller nhận request:

    @PostMapping
    public ResponseEntity<ProductDto> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductDto created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

Validation ở DTO kiểm tra cấu trúc và ràng buộc đầu vào. Quy tắc nghiệp vụ như “không thể xác nhận đơn đã hủy” vẫn nên được kiểm tra trong domain/application service, vì quy tắc đó phải đúng dù lệnh đến từ REST, message consumer hay batch job.

API riêng cũng có thể chuẩn hóa lỗi bằng `@RestControllerAdvice` và Problem Details:

    @RestControllerAdvice
    public class ApiExceptionHandler {

        @ExceptionHandler(OrderNotFoundException.class)
        public ProblemDetail handleNotFound(
                OrderNotFoundException exception) {
            ProblemDetail problem = ProblemDetail
                    .forStatus(HttpStatus.NOT_FOUND);
            problem.setTitle("Order not found");
            problem.setDetail(exception.getMessage());
            return problem;
        }
    }

Hãy giữ thông tin lỗi đủ hữu ích cho client nhưng không tiết lộ SQL, stack trace, token hoặc dữ liệu nội bộ.

## 8. Bảo mật và quyền truy cập

Dù dùng Spring Data REST hay custom DTO API, authorization vẫn phải được thiết kế theo tài nguyên và hành động.

Với Spring Data REST, có thể kết hợp Spring Security, repository event, method security và cấu hình exposure. Tuy nhiên, ẩn một link hoặc một trường không thay thế authorization ở server.

Với custom API, có thể bảo vệ method/use case:

    @PreAuthorize("@orderAuthorization.canRead(#id, authentication)")
    public OrderDetailDto getDetail(Long id) {
        // ...
    }

Ví dụ minh họa kiểm soát truy cập ở application service; biểu thức cụ thể phụ thuộc bean và chính sách bảo mật của ứng dụng.

DTO giúp giới hạn dữ liệu trả về, nhưng không tự ngăn truy cập trái phép. Luôn kiểm tra quyền trước khi tải/trả dữ liệu nhạy cảm và trước mỗi command có side effect.

## 9. Có thể dùng song song hai kiểu API không?

Có. Một ứng dụng có thể tiếp tục xuất bản repository resource cho CRUD nội bộ và đồng thời cung cấp custom API cho use case phức tạp.

Ví dụ:

    /data/products
    /data/products/42

    /api/v1/catalog/search
    /api/v1/orders/42/confirm
    /api/v1/orders/42/summary

Trong ví dụ này:

- `/data` là base path dành cho Spring Data REST repository resources.
- `/api/v1` là namespace cho hợp đồng API do ứng dụng quản lý.
- Custom API có thể gọi cùng application service/domain logic với các luồng khác.
- Không nên tạo hai bộ quy tắc nghiệp vụ khác nhau cho cùng một thao tác chỉ vì có hai endpoint.

Tách namespace giúp người vận hành và client nhận biết API nào được sinh từ repository, API nào là hợp đồng use case. Nếu cả hai đều có quyền ghi cùng aggregate, phải bảo đảm validation, transaction và domain invariant dùng chung.

## 10. Bảng quyết định

| Nhu cầu | Hướng phù hợp |
| --- | --- |
| CRUD đơn giản, resource gần domain | Spring Data REST |
| Thay đổi tập trường đọc của cùng resource | Projection hoặc excerpt projection |
| Thêm link/metadata hypermedia | RepresentationModelProcessor |
| Logic đơn giản gắn với vòng đời repository | Repository event handler |
| Endpoint nhỏ gắn với repository resource | @RepositoryRestController |
| Request/response khác entity rõ rệt | Custom API với DTO |
| Command có nhiều bước nghiệp vụ | Controller + application service + DTO |
| Tổng hợp nhiều aggregate hoặc nguồn dữ liệu | Query service/read model + DTO |
| API versioning độc lập với entity | Custom API với DTO |
| Quyền và dữ liệu trả về phụ thuộc use case | Custom API với DTO và authorization rõ ràng |

Có thể dùng quy tắc thực tế: nếu yêu cầu chỉ thay đổi cách trình bày hoặc điều hướng của cùng repository resource, ưu tiên cơ chế mở rộng Spring Data REST. Nếu yêu cầu định nghĩa một use case và hợp đồng độc lập, tạo custom API.

## 11. Các dấu hiệu đang mở rộng sai chỗ

Hãy đánh giá lại ranh giới khi thấy một số dấu hiệu:

- Projection chứa nhiều logic tính toán và gọi dịch vụ.
- Repository event handler điều phối nhiều repository hoặc gọi hệ thống bên ngoài.
- Entity phải chứa các trường chỉ phục vụ một màn hình cụ thể.
- Client phải gửi cả entity dù chỉ muốn thực hiện một command.
- Controller phải lọc thủ công nhiều trường nhạy cảm ở mọi endpoint.
- Custom endpoint liên tục được thêm vào repository resource dù không còn dùng hypermedia.
- Một thay đổi entity gây breaking change cho nhiều client không liên quan.
- Cùng một nghiệp vụ được thực thi khác nhau giữa repository event và custom controller.

Các dấu hiệu này không tự động chứng minh thiết kế sai. Chúng là tín hiệu cần xem lại trách nhiệm của từng lớp và chi phí bảo trì trong thực tế.

## 12. Lộ trình chuyển đổi an toàn

Khi cần chuyển một endpoint từ repository resource sang API DTO, hãy thực hiện từng bước:

1. Ghi lại hợp đồng hiện tại: URI, method, status code, representation, link, validation và authorization.
2. Xác định use case thực sự mà client cần, gồm input, output và side effect.
3. Thiết kế request/response DTO độc lập với entity.
4. Đưa logic nghiệp vụ vào application service hoặc domain service dùng chung.
5. Tạo endpoint mới với namespace/version rõ ràng.
6. Kiểm thử mapping, validation, quyền truy cập, transaction và lỗi.
7. Cho client chuyển sang endpoint mới theo kế hoạch tương thích.
8. Theo dõi usage và chỉ ngừng export endpoint cũ khi đã có bằng chứng không còn client phụ thuộc.

Nếu endpoint cũ là API công khai, tránh thay đổi representation đột ngột. Có thể duy trì hai đường dẫn trong giai đoạn chuyển tiếp, nhưng phải dùng chung nghiệp vụ và xác định thời điểm kết thúc hỗ trợ.

## 13. Bài thực hành

Giả sử hệ thống có `OrderRepository` được Spring Data REST xuất bản. Client hiện dùng:

    GET /data/orders/42
    PATCH /data/orders/42

Product owner bổ sung hai yêu cầu:

- Màn hình quản trị cần một response tổng hợp Order, Customer, Payment và các action khả dụng.
- Người dùng cần xác nhận đơn hàng bằng mã xác nhận; thao tác này phải kiểm tra tồn kho, thanh toán và trạng thái đơn.

Thực hiện:

1. Xác định phần nào vẫn phù hợp với repository resource.
2. Thiết kế `OrderSummaryDto` cho màn hình quản trị.
3. Thiết kế `ConfirmOrderRequest` và `ConfirmOrderResponse`.
4. Xây dựng `OrderApplicationService` điều phối xác nhận.
5. Tạo `POST /api/v1/orders/{id}/confirm`.
6. Giữ `OrderRepository` làm persistence port và dùng chung domain invariant.
7. Kiểm tra quyền đọc summary và quyền thực hiện command.
8. Viết test cho trường hợp xác nhận thành công, sai mã, hết hàng, thanh toán thất bại và đơn đã hủy.
9. Quyết định endpoint nào tiếp tục dùng Spring Data REST và endpoint nào thuộc custom API.

Câu hỏi tự kiểm tra:

- Khi nào projection đủ dùng và khi nào cần DTO riêng?
- Vì sao một command như confirm order không nên được mô hình hóa thành việc client gửi lại toàn bộ entity?
- Logic nhiều bước nên nằm ở controller, repository event handler hay application service?
- DTO bảo vệ API khỏi thay đổi entity như thế nào?
- Có thể dùng Spring Data REST và custom API trong cùng ứng dụng không?
- Khi chuyển endpoint cũ, cần giữ lại những thông tin hợp đồng nào để tránh breaking change?

## Tài liệu tham khảo

- [Spring Data REST Reference — Customizing the exposed REST API](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Framework Reference — REST Clients and Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
