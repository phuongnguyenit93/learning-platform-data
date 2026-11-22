# Trả EntityModel, CollectionModel, PagedModel và ResponseEntity

Khi xây dựng API bằng Spring MVC, một endpoint có thể trả về dữ liệu domain trực tiếp hoặc dùng các kiểu của Spring HATEOAS để mô tả tài nguyên cùng các liên kết điều hướng. EntityModel, CollectionModel và PagedModel giúp biểu diễn tài nguyên theo HAL/HATEOAS; ResponseEntity cho phép kiểm soát HTTP status, header và body của response.

Bốn kiểu này giải quyết hai lớp vấn đề khác nhau. Các model HATEOAS mô tả nội dung và liên kết mà client có thể khám phá. ResponseEntity mô tả cách server gửi kết quả qua HTTP. Có thể kết hợp chúng, ví dụ trả về ResponseEntity<EntityModel<OrderSummary>> khi cần vừa có liên kết tài nguyên vừa đặt status hoặc header cụ thể.

## 1. Vì sao cần các kiểu model của Spring HATEOAS?

Một API REST cơ bản có thể trả JSON của entity:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50
}
~~~

Client nhận được dữ liệu nhưng phải biết trước các URL để thực hiện thao tác tiếp theo. Khi dùng HATEOAS, response có thể chứa các link như self, collection, cancel hoặc payment. Client khám phá hành động có thể thực hiện từ liên kết server cung cấp.

Ví dụ:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/42"
    },
    "orders": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Spring HATEOAS cung cấp các lớp model để gắn link vào representation:

- EntityModel<T> bao bọc một tài nguyên đơn lẻ.
- CollectionModel<T> biểu diễn một tập hợp tài nguyên không có metadata phân trang chuẩn.
- PagedModel<T> biểu diễn một trang tài nguyên, có metadata về trang và các link điều hướng.
- ResponseEntity<T> bao bọc HTTP response, cho phép đặt status, header và body kiểu T.

EntityModel, CollectionModel và PagedModel thuộc Spring HATEOAS. ResponseEntity thuộc Spring MVC, trong package org.springframework.http. Không nên coi ResponseEntity là một loại HATEOAS model.

## 2. Trả về một tài nguyên bằng EntityModel

EntityModel<T> phù hợp khi endpoint trả về một tài nguyên đơn lẻ cùng các liên kết của nó. Tạo model bằng EntityModel.of(content), sau đó thêm các link cần thiết.

Ví dụ domain DTO:

~~~java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal total
) {
}
~~~

Controller có thể trả về EntityModel:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderSummary> getOrder(@PathVariable Long id) {
        OrderSummary order = orderService.findSummary(id);

        return EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).getOrder(id))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).listOrders())
                .withRel("orders")
        );
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderSummary>> listOrders() {
        return CollectionModel.empty();
    }
}
~~~

Trong ví dụ:

- EntityModel.of(order, links...) tạo representation cho một đơn hàng.
- withSelfRel() tạo quan hệ self trỏ tới tài nguyên hiện tại.
- withRel("orders") tạo một quan hệ có tên orders.
- linkTo(methodOn(...)) tạo URL dựa trên mapping của controller, tránh tự nối chuỗi URL.

Các import chính:

~~~java
import org.springframework.hateoas.EntityModel;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Khi response được chuyển đổi bằng cấu hình Spring HATEOAS phù hợp, model sẽ được serialize thành representation có nội dung tài nguyên và phần _links. Nếu API dùng HAL, hãy bảo đảm ứng dụng có cấu hình message converter và media type HAL tương ứng.

EntityModel không tự tải dữ liệu từ repository và cũng không tự quyết định quyền truy cập. Controller hoặc service vẫn phải truy xuất dữ liệu, kiểm tra nghiệp vụ và tạo model.

## 3. Trả về một tập hợp bằng CollectionModel

CollectionModel<T> dùng khi endpoint trả về nhiều tài nguyên nhưng không cần metadata phân trang kiểu Page. T thường là EntityModel<OrderSummary>, nhưng cũng có thể là một representation model khác.

Ví dụ tạo từng item model rồi bọc chúng trong CollectionModel:

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderSummary>> listOrders() {
    List<OrderSummary> orders = orderService.findAllSummaries();

    List<EntityModel<OrderSummary>> items = orders.stream()
        .map(order -> EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).getOrder(order.id()))
                .withSelfRel()
        ))
        .toList();

    return CollectionModel.of(
        items,
        linkTo(methodOn(OrderController.class).listOrders())
            .withSelfRel()
    );
}
~~~

CollectionModel.of(items, links...) tạo collection representation. Mỗi phần tử có thể mang self link riêng; collection cũng có self link của chính nó.

Một response HAL minh họa:

~~~json
{
  "_embedded": {
    "orderSummaryList": [
      {
        "id": 42,
        "status": "CONFIRMED",
        "total": 125.50,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/42"
          }
        }
      },
      {
        "id": 43,
        "status": "DRAFT",
        "total": 80.00,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Tên thuộc tính trong _embedded có thể được điều chỉnh bằng cấu hình rel hoặc collection model phù hợp. Ví dụ trên chỉ minh họa cấu trúc HAL, không phải tên rel bắt buộc cho mọi ứng dụng.

CollectionModel phù hợp với danh sách nhỏ hoặc tập kết quả không phân trang. Với collection lớn, nên phân trang ở tầng truy vấn thay vì tải tất cả bản ghi rồi đóng gói vào một response.

## 4. Trả về dữ liệu phân trang bằng PagedModel

PagedModel<T> biểu diễn nội dung của một trang cùng metadata và các liên kết điều hướng. Nó phù hợp khi client cần biết trang hiện tại, kích thước trang, tổng số phần tử và cách chuyển tới trang khác.

Trong Spring Data, repository có thể trả về Page<T>:

~~~java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

Trong controller MVC, có thể dùng PagedResourcesAssembler<T> để chuyển Page<T> thành PagedModel<R>. Ví dụ:

~~~java
@GetMapping("/search")
public PagedModel<EntityModel<OrderSummary>> searchOrders(
        @RequestParam OrderStatus status,
        Pageable pageable,
        PagedResourcesAssembler<PurchaseOrder> assembler) {

    Page<PurchaseOrder> page =
        orderRepository.findByStatus(status, pageable);

    return assembler.toModel(page, orderModelAssembler);
}
~~~

orderModelAssembler chuyển từng PurchaseOrder thành EntityModel<OrderSummary>:

~~~java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
            PurchaseOrder,
            EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(PurchaseOrder order) {
        OrderSummary summary = new OrderSummary(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(
            summary,
            linkTo(methodOn(OrderController.class).getOrder(order.getId()))
                .withSelfRel()
        );
    }
}
~~~

Các kiểu thường dùng:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
~~~

PagedResourcesAssembler.toModel(page, assembler) tạo PagedModel từ Page và áp dụng assembler cho từng phần tử. Kết quả có thể chứa metadata page cùng các link first, prev, self, next và last tùy vị trí hiện tại.

Ví dụ cấu trúc HAL minh họa:

~~~json
{
  "_embedded": {
    "orderSummaryList": [
      {
        "id": 42,
        "status": "CONFIRMED",
        "total": 125.50,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/search?page=0&size=10"
    },
    "next": {
      "href": "http://localhost:8080/api/orders/search?page=1&size=10"
    },
    "last": {
      "href": "http://localhost:8080/api/orders/search?page=4&size=10"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 45,
    "totalPages": 5,
    "number": 0
  }
}
~~~

PagedModel giúp client điều hướng dựa trên link server cung cấp và không cần tự suy ra URL cho trang kế tiếp. Metadata page cũng giúp giao diện hiển thị số trang hoặc tổng số kết quả.

Nếu không dùng PagedResourcesAssembler, có thể tự tạo PagedModel bằng nội dung và metadata phù hợp. Tuy nhiên, cần bảo đảm các link điều hướng và thông tin page nhất quán với kết quả truy vấn thực tế.

## 5. Phân biệt CollectionModel và PagedModel

Cả hai đều biểu diễn nhiều tài nguyên, nhưng mục đích khác nhau:

| Kiểu | Nội dung | Metadata phân trang | Trường hợp phù hợp |
|---|---|---|---|
| CollectionModel<T> | Một tập hợp item. | Không có metadata Page chuẩn. | Danh sách nhỏ hoặc tập kết quả không phân trang. |
| PagedModel<T> | Các item của một trang. | Có page metadata và link điều hướng khi được tạo đúng cách. | Tập dữ liệu lớn, truy vấn theo trang. |

Không nên dùng CollectionModel để chứa hàng chục nghìn bản ghi chỉ vì endpoint cần trả về một collection. Hãy phân trang tại repository bằng Pageable, sau đó dùng PagedModel để biểu diễn kết quả.

PagedModel không tự thực hiện truy vấn database. Nó chỉ biểu diễn trang đã được truy vấn. Tầng repository/service vẫn chịu trách nhiệm giới hạn dữ liệu, sắp xếp và tính tổng số phần tử theo yêu cầu.

## 6. Dùng ResponseEntity để kiểm soát HTTP response

ResponseEntity<T> cho phép controller quyết định:

- HTTP status code.
- Response headers.
- Response body kiểu T.

Ví dụ trả về một tài nguyên với status 200:

~~~java
@GetMapping("/{id}")
public ResponseEntity<EntityModel<OrderSummary>> getOrder(
        @PathVariable Long id) {

    OrderSummary order = orderService.findSummary(id);
    EntityModel<OrderSummary> model = orderModelAssembler.toModel(order);

    return ResponseEntity.ok(model);
}
~~~

ResponseEntity.ok(body) tạo response HTTP 200 OK với body đã cho.

Khi tạo mới tài nguyên, có thể trả về 201 Created và Location:

~~~java
@PostMapping
public ResponseEntity<EntityModel<OrderSummary>> createOrder(
        @RequestBody CreateOrderRequest request) {

    OrderSummary created = orderService.create(request);
    EntityModel<OrderSummary> model =
        orderModelAssembler.toModel(created);

    URI location = linkTo(
        methodOn(OrderController.class).getOrder(created.id())
    ).toUri();

    return ResponseEntity.created(location).body(model);
}
~~~

ResponseEntity.created(location) đặt status 201 Created và header Location. body(model) đính kèm representation có các liên kết HATEOAS.

Một số cách trả response khác:

~~~java
return ResponseEntity.noContent().build();          // 204 No Content
return ResponseEntity.notFound().build();           // 404 Not Found
return ResponseEntity.accepted().body(result);      // 202 Accepted
return ResponseEntity.status(HttpStatus.CONFLICT)
    .body(errorModel);                              // 409 Conflict
~~~

Có thể thêm header tùy chỉnh:

~~~java
return ResponseEntity.ok()
    .header("X-Request-Id", requestId)
    .body(model);
~~~

Không nên dùng status 200 cho mọi tình huống. Hãy chọn status phản ánh kết quả HTTP: 201 khi tạo tài nguyên, 202 khi chấp nhận xử lý bất đồng bộ, 204 khi thành công mà không có body, 404 khi không tìm thấy và 409 khi xung đột nghiệp vụ phù hợp.

## 7. Kết hợp ResponseEntity với các model HATEOAS

ResponseEntity nhận một kiểu body bất kỳ. Vì vậy, có thể kết hợp nó với EntityModel, CollectionModel hoặc PagedModel.

Ví dụ:

~~~java
ResponseEntity<EntityModel<OrderSummary>>
ResponseEntity<CollectionModel<EntityModel<OrderSummary>>>
ResponseEntity<PagedModel<EntityModel<OrderSummary>>>
~~~

Các kiểu này thể hiện:

- ResponseEntity quản lý HTTP status và headers.
- EntityModel, CollectionModel hoặc PagedModel quản lý representation và links.

Ví dụ endpoint tìm kiếm trả trang kết quả:

~~~java
@GetMapping("/search")
public ResponseEntity<PagedModel<EntityModel<OrderSummary>>> search(
        Pageable pageable,
        PagedResourcesAssembler<PurchaseOrder> assembler) {

    Page<PurchaseOrder> page = orderService.findPage(pageable);
    PagedModel<EntityModel<OrderSummary>> model =
        assembler.toModel(page, orderModelAssembler);

    return ResponseEntity.ok()
        .header("X-Result-Count", Long.toString(page.getTotalElements()))
        .body(model);
}
~~~

Ở đây, PagedModel chứa các item và link phân trang; ResponseEntity đặt status 200 và thêm header X-Result-Count.

Nếu không cần điều chỉnh status hoặc header, controller có thể trả thẳng EntityModel, CollectionModel hoặc PagedModel. Spring MVC sẽ serialize object thành response body. Dùng ResponseEntity khi endpoint cần kiểm soát HTTP response một cách tường minh.

## 8. Khi nào nên dùng DTO và RepresentationModelAssembler?

Không nên luôn trả trực tiếp JPA entity ra API. Entity có thể chứa quan hệ lazy, trường nội bộ, dữ liệu nhạy cảm hoặc cấu trúc persistence không phù hợp với hợp đồng công khai.

DTO giúp định nghĩa chính xác dữ liệu được trả về:

~~~java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal total
) {
}
~~~

RepresentationModelAssembler<T, D> tách việc chuyển domain object sang representation model:

~~~java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
            PurchaseOrder,
            EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(PurchaseOrder order) {
        OrderSummary summary = new OrderSummary(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(
            summary,
            linkTo(methodOn(OrderController.class).getOrder(order.getId()))
                .withSelfRel()
        );
    }
}
~~~

Lợi ích:

- Controller gọn hơn vì không lặp logic tạo link.
- Representation không phụ thuộc trực tiếp vào cấu trúc entity.
- Có thể ẩn trường nội bộ hoặc nhạy cảm.
- Cùng một assembler có thể dùng cho item và collection.
- Có thể thay đổi link hoặc DTO mà ít ảnh hưởng service và persistence.

Assembler chỉ định hình representation. Việc truy vấn, kiểm tra quyền, xử lý nghiệp vụ và transaction vẫn thuộc service/repository phù hợp.

## 9. Spring Data REST mặc định và custom controller

Spring Data REST tự động công bố repository thành REST resources và tạo HAL links cho các thao tác được hỗ trợ. Với repository endpoint chuẩn, framework đã xây dựng representation và link discovery theo cấu hình của nó.

EntityModel, CollectionModel và PagedModel thường xuất hiện khi ứng dụng tự xây custom controller hoặc muốn tùy biến representation. Có thể dùng @RestController cho endpoint riêng, rồi trả các model HATEOAS như ví dụ ở trên.

Nếu dùng @RepositoryRestController để mở rộng endpoint trong vùng base path của Spring Data REST, cần chú ý cấu hình mapping và message converter để tránh xung đột với repository controller tự động. Chọn kiểu controller theo phạm vi endpoint và kiểm tra URL thực tế sau khi khởi động ứng dụng.

Không cần tự bọc mọi repository response mặc định bằng ResponseEntity chỉ để thêm HATEOAS. Hãy dùng custom endpoint khi có nhu cầu nghiệp vụ hoặc representation riêng; giữ cho các endpoint tự động của Spring Data REST theo cơ chế chuẩn của framework.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Response không có _links | Trả DTO/entity trực tiếp hoặc thiếu cấu hình HATEOAS/HAL. | Trả model HATEOAS và kiểm tra message converter/media type. |
| Link self sai URL | Tự nối chuỗi URL hoặc mapping controller thay đổi. | Dùng linkTo(methodOn(...)) để tạo link từ mapping. |
| Collection trả quá nhiều dữ liệu | Dùng CollectionModel cho tập kết quả lớn. | Phân trang ở repository và trả PagedModel. |
| PagedModel thiếu metadata hoặc link | Tự tạo model nhưng không truyền page metadata hoặc navigation links. | Dùng PagedResourcesAssembler hoặc tạo metadata/link nhất quán. |
| ResponseEntity trả sai status | Dùng ok() cho cả create, delete và conflict. | Chọn status theo kết quả HTTP và nghiệp vụ. |
| Lỗi serialize do entity relation | Trả entity JPA có quan hệ lazy hoặc vòng tham chiếu. | Dùng DTO và RepresentationModelAssembler. |
| Link trùng hoặc không đúng rel | Tạo nhiều link cùng quan hệ hoặc đặt rel không nhất quán. | Chuẩn hóa rel và kiểm tra representation trả về. |
| Controller không được gọi | Mapping xung đột với repository endpoint tự động. | Kiểm tra base path, controller mapping và loại controller. |

## 11. Quy trình kiểm tra response

Sau khi xây dựng controller:

1. Gọi GET một order và xác nhận response có nội dung cùng self link.
2. Gọi GET collection và xác nhận các item nằm trong _embedded, collection có self link.
3. Gọi endpoint phân trang và xác nhận page metadata cùng các link first/prev/next/last phù hợp.
4. Gửi POST tạo order và xác nhận status 201 cùng header Location.
5. Gọi endpoint trả 204 và xác nhận response không có body.
6. Kiểm tra Content-Type và cấu trúc HAL mà client thực sự nhận được.
7. Kiểm tra các DTO không đưa trường nội bộ hoặc dữ liệu nhạy cảm ra response.
8. Dùng request ở trang đầu, trang giữa và trang cuối để kiểm tra link điều hướng.
9. Xác nhận response status và headers đúng với thành công, không tìm thấy và xung đột nghiệp vụ.

EntityModel dùng cho một tài nguyên có link; CollectionModel dùng cho tập hợp không có page metadata chuẩn; PagedModel dùng cho kết quả phân trang; ResponseEntity kiểm soát HTTP status, headers và body. Kết hợp các kiểu này giúp custom endpoint Spring MVC trả representation dễ khám phá, phân trang rõ ràng và phản ánh đúng kết quả HTTP.
