# Bổ sung liên kết và biểu diễn bằng RepresentationModelProcessor

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của RepresentationModelProcessor trong Spring HATEOAS và Spring Data REST.
- Bổ sung link tùy chỉnh vào representation của một entity.
- Tạo URL bằng WebMvcLinkBuilder và ánh xạ method của controller.
- Thêm link có điều kiện dựa trên trạng thái nghiệp vụ.
- Phân biệt việc bổ sung hypermedia link với việc thay đổi cấu trúc dữ liệu JSON.
- Kiểm thử các link được xuất hiện trong HAL response.

## 1. Representation trong Spring Data REST

Spring Data REST tự động xuất bản các repository thành REST resource. Khi client gọi một item endpoint, response thường chứa dữ liệu entity cùng các liên kết hypermedia trong thuộc tính **_links**.

Ví dụ:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Response có thể chứa:

~~~json
{
  "id": 42,
  "status": "SHIPPED",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "purchaseOrder": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

Các link cho biết client có thể điều hướng đến resource nào. Client nên dựa vào relation và href server cung cấp thay vì tự ghép URL từ quy ước nội bộ.

Tuy nhiên, API đôi khi cần công bố thêm một hành động hoặc tài nguyên nghiệp vụ mà repository không tự tạo link, ví dụ:

- Link xem thông tin vận chuyển của đơn hàng.
- Link tải hóa đơn khi đơn đã thanh toán.
- Link xem lịch sử xử lý hoặc trạng thái kiểm duyệt.
- Link mở một thao tác nghiệp vụ được cung cấp bởi custom controller.

Spring HATEOAS cung cấp **RepresentationModelProcessor** để bổ sung hoặc điều chỉnh hypermedia link trên representation trước khi response được trả về client.

## 2. RepresentationModelProcessor hoạt động như thế nào?

RepresentationModelProcessor là một extension point của Spring HATEOAS. Processor nhận một đối tượng representation model, xử lý model đó và trả lại model.

Khai báo tổng quát:

~~~java
public interface RepresentationModelProcessor<T extends RepresentationModel<?>>
        extends Ordered {

    T process(T model);
}
~~~

Trong ứng dụng Spring Data REST, các kiểu representation thường gặp gồm:

- **EntityModel<T>**: biểu diễn một entity hoặc một đối tượng đơn.
- **CollectionModel<T>**: biểu diễn một collection resource.
- **PagedModel<T>**: biểu diễn collection có thông tin phân trang.
- Một lớp tự định nghĩa kế thừa **RepresentationModel<T>**.

Một processor thường được đăng ký như Spring bean bằng **@Component**. Spring HATEOAS tìm processor phù hợp với kiểu representation đang được xây dựng và gọi phương thức **process**.

Trong processor, có thể:

1. Đọc nội dung representation nếu cần.
2. Kiểm tra trạng thái hoặc dữ liệu đã có trong model.
3. Tạo một hoặc nhiều Link.
4. Thêm link bằng **model.add(...)**.
5. Trả lại model.

Processor thường bổ sung hypermedia metadata. Nó không tự tạo endpoint, không tự lưu dữ liệu và không thay thế logic nghiệp vụ của controller hoặc service.

## 3. Tạo endpoint nghiệp vụ để link có đích đến

Giả sử ứng dụng có PurchaseOrder và cần công bố link xem thông tin vận chuyển khi đơn hàng đã được gửi đi.

Trước tiên, tạo controller cung cấp endpoint tương ứng:

~~~java
@RestController
@RequestMapping("/order-operations")
public class OrderOperationsController {

    private final OrderTrackingService trackingService;

    public OrderOperationsController(OrderTrackingService trackingService) {
        this.trackingService = trackingService;
    }

    @GetMapping("/{orderId}/tracking")
    public ResponseEntity<TrackingView> tracking(
            @PathVariable Long orderId) {

        TrackingView tracking = trackingService.findByOrderId(orderId);
        return ResponseEntity.ok(tracking);
    }
}
~~~

Endpoint này chịu trách nhiệm xử lý request thật. RepresentationModelProcessor chỉ công bố đường dẫn đến endpoint cho client.

Nếu controller chưa tồn tại hoặc route không xử lý request, link được thêm vào response vẫn có thể dẫn đến 404. Vì vậy cần kiểm tra cả link lẫn endpoint đích.

## 4. Bổ sung link vào EntityModel

Với item resource của PurchaseOrder, có thể viết processor như sau:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class PurchaseOrderRepresentationProcessor
        implements RepresentationModelProcessor<EntityModel<PurchaseOrder>> {

    @Override
    public EntityModel<PurchaseOrder> process(
            EntityModel<PurchaseOrder> model) {

        PurchaseOrder order = model.getContent();

        if (order != null && order.getStatus() == OrderStatus.SHIPPED) {
            model.add(
                linkTo(methodOn(OrderOperationsController.class)
                    .tracking(order.getId()))
                    .withRel("tracking")
            );
        }

        return model;
    }
}
~~~

Giải thích:

- **RepresentationModelProcessor<EntityModel<PurchaseOrder>>** giới hạn processor vào representation đơn chứa PurchaseOrder.
- **model.getContent()** lấy entity được representation hiện tại bao bọc.
- Điều kiện **OrderStatus.SHIPPED** quyết định khi nào link tracking được công bố.
- **methodOn(...)** mô tả lời gọi đến method controller để Spring HATEOAS xác định đích liên kết.
- **linkTo(...)** tạo link dựa trên mapping của controller.
- **withRel("tracking")** đặt relation name mà client dùng để nhận biết link.
- **model.add(...)** thêm link vào representation.
- Trả lại chính model giúp giữ nguyên các link mặc định và các link do processor khác đã thêm.

Khi đơn hàng có trạng thái SHIPPED, HAL response có thể có thêm:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "tracking": {
      "href": "http://localhost:8080/order-operations/42/tracking"
    }
  }
}
~~~

Khi đơn chưa được gửi đi, processor không thêm relation tracking. Client có thể dùng sự hiện diện của link để biết hành động đó có được công bố trong trạng thái hiện tại hay không.

## 5. Vì sao nên dùng WebMvcLinkBuilder?

Có thể tạo link bằng chuỗi URL cố định:

~~~java
model.add(Link.of(
    "/order-operations/" + order.getId() + "/tracking"
).withRel("tracking"));
~~~

Cách này đơn giản nhưng khiến processor phụ thuộc trực tiếp vào path. Khi controller đổi base path, đổi mapping hoặc ứng dụng chạy dưới một context path khác, chuỗi URL có thể bị lỗi thời.

Với **WebMvcLinkBuilder**, có thể tham chiếu trực tiếp method controller:

~~~java
Link trackingLink = linkTo(
    methodOn(OrderOperationsController.class)
        .tracking(order.getId())
).withRel("tracking");

model.add(trackingLink);
~~~

Lợi ích:

- URL được suy ra từ mapping controller.
- Giảm việc lặp lại path trong nhiều nơi.
- Dễ refactor endpoint hơn.
- Link được tạo theo cấu hình web hiện tại của ứng dụng.

Đối với một URI bên ngoài hoặc một URI đã được cung cấp từ cấu hình, **Link.of(uri).withRel("...")** vẫn là lựa chọn phù hợp. Không nên tự dựng URL bằng cách nối chuỗi nếu có thể tham chiếu controller method.

## 6. Bổ sung nhiều link và link có điều kiện

Một representation có thể công bố nhiều khả năng điều hướng:

~~~java
@Override
public EntityModel<PurchaseOrder> process(
        EntityModel<PurchaseOrder> model) {

    PurchaseOrder order = model.getContent();

    if (order == null) {
        return model;
    }

    if (order.getStatus() == OrderStatus.SHIPPED) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .tracking(order.getId()))
                .withRel("tracking")
        );
    }

    if (order.getStatus() == OrderStatus.PAID) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .invoice(order.getId()))
                .withRel("invoice")
        );
    }

    return model;
}
~~~

Ví dụ này giả định controller có các method **tracking(...)** và **invoice(...)** tương ứng.

Có thể áp dụng các nguyên tắc sau:

- Chỉ công bố link khi hành động hợp lệ theo trạng thái nghiệp vụ.
- Dùng relation name ngắn gọn, ổn định và có ý nghĩa.
- Không thêm nhiều link trùng relation nếu client không có quy tắc xử lý rõ ràng.
- Giữ điều kiện hiển thị link đồng nhất với quy tắc nghiệp vụ tại endpoint.
- Endpoint đích vẫn phải kiểm tra quyền và trạng thái khi request thực sự được gửi.

Việc ẩn link không phải là cơ chế phân quyền. Client có thể tự tạo request đến URL đã biết; controller/service phải tự xác thực và từ chối thao tác không hợp lệ.

## 7. Bổ sung link cho collection và paged representation

Ngoài item resource, đôi khi cần bổ sung link ở cấp collection, ví dụ:

- Link tạo đơn hàng mới.
- Link tải báo cáo tổng hợp.
- Link đến tài liệu hướng dẫn hoặc bộ lọc nâng cao.
- Link đến một thao tác áp dụng cho cả collection.

Spring HATEOAS cho phép viết processor cho các representation model khác nhau, chẳng hạn **CollectionModel** hoặc **PagedModel**.

Ví dụ về hình thức khai báo:

~~~java
@Component
public class PurchaseOrderCollectionProcessor
        implements RepresentationModelProcessor<
            CollectionModel<EntityModel<PurchaseOrder>>> {

    @Override
    public CollectionModel<EntityModel<PurchaseOrder>> process(
            CollectionModel<EntityModel<PurchaseOrder>> model) {

        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .createOrderDocumentation())
                .withRel("create-order-guide")
        );

        return model;
    }
}
~~~

Ví dụ minh họa trên giả định controller có method tương ứng để tạo link. Trong dự án thực tế, kiểu generic cần khớp với representation mà Spring Data REST phiên bản đang sử dụng.

Đặc biệt, collection có phân trang có thể được biểu diễn bằng **PagedModel**. Nếu processor không được gọi, hãy kiểm tra kiểu model thực tế và generic type của processor. Không nên giả định processor dành cho collection thường sẽ luôn khớp với mọi paged representation.

Hãy kiểm tra riêng item resource, collection resource và search resource nếu API cần bổ sung link cho nhiều loại response.

## 8. Custom representation model

RepresentationModelProcessor xử lý một representation đã được tạo. Nếu cần thay đổi cấu trúc dữ liệu JSON, ví dụ chỉ trả về một số trường hoặc tạo một DTO tổng hợp, hãy dùng projection hoặc custom controller trả về model riêng.

Ví dụ một model tùy chỉnh:

~~~java
public class OrderSummaryModel
        extends RepresentationModel<OrderSummaryModel> {

    private final Long id;
    private final String status;
    private final String customerName;

    public OrderSummaryModel(
            Long id,
            String status,
            String customerName) {
        this.id = id;
        this.status = status;
        this.customerName = customerName;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getCustomerName() {
        return customerName;
    }
}
~~~

Custom controller có thể trả về model này:

~~~java
@GetMapping("/{id}/summary")
public OrderSummaryModel summary(@PathVariable Long id) {
    OrderSummary summary = orderService.getSummary(id);

    return new OrderSummaryModel(
        summary.id(),
        summary.status(),
        summary.customerName()
    );
}
~~~

Sau đó có thể viết processor cho **OrderSummaryModel** để bổ sung link:

~~~java
@Component
public class OrderSummaryProcessor
        implements RepresentationModelProcessor<OrderSummaryModel> {

    @Override
    public OrderSummaryModel process(OrderSummaryModel model) {
        model.add(
            linkTo(methodOn(OrderOperationsController.class)
                .tracking(model.getId()))
                .withRel("tracking")
        );

        return model;
    }
}
~~~

Như vậy có hai trách nhiệm riêng:

- Custom controller/DTO quyết định dữ liệu nào xuất hiện trong body.
- RepresentationModelProcessor bổ sung các liên kết hypermedia cho model đó.

Không nên dùng processor như một cách thay thế projection hoặc serializer khi mục tiêu chính là thay đổi schema dữ liệu.

## 9. Những lưu ý khi triển khai

### Giữ processor nhẹ

Processor có thể được gọi trong quá trình tạo representation. Nếu mỗi lần xử lý một entity lại truy vấn thêm repository hoặc gọi dịch vụ bên ngoài, response collection có thể phát sinh N+1 query hoặc tăng độ trễ đáng kể.

Nên:

- Ưu tiên sử dụng các trường đã có trong model.
- Tránh truy vấn database riêng cho từng entity.
- Nếu cần dữ liệu bổ sung, cân nhắc truy vấn theo lô hoặc chuẩn bị dữ liệu ở tầng service phù hợp.
- Không thực hiện thao tác ghi dữ liệu hoặc side effect trong processor.

### Không làm mất link có sẵn

Nếu chỉ cần thêm link, hãy gọi **model.add(...)** trên model hiện tại rồi trả lại nó. Tạo một model mới từ entity có thể vô tình làm mất self link, association link hoặc link do Spring Data REST đã tạo.

### Chú ý lazy loading

Đọc thuộc tính lazy của entity trong processor có thể kích hoạt truy vấn bổ sung hoặc gây lỗi khi persistence context đã đóng. Chỉ truy cập các trường cần thiết và xác định rõ cách dữ liệu được tải.

### Đảm bảo link có thể sử dụng

Một link được công bố phải trỏ đến endpoint thực sự tồn tại. Kiểm tra:

- HTTP method mà endpoint hỗ trợ.
- Path variable và query parameter.
- Base path/context path.
- Media type của response.
- Quyền truy cập và điều kiện nghiệp vụ.

### Bảo vệ dữ liệu

Không đưa thông tin bí mật, token, thông tin xác thực hoặc dữ liệu nội bộ vào href. Relation và link nên mô tả khả năng điều hướng mà client được phép biết.

## 10. Kiểm thử RepresentationModelProcessor

Nên kiểm thử cả trường hợp link được thêm và trường hợp link không được thêm.

Ví dụ với MockMvc:

~~~java
@WebMvcTest
class PurchaseOrderRepresentationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private PurchaseOrderRepository repository;

    @Test
    void shouldExposeTrackingLinkWhenOrderIsShipped() throws Exception {
        PurchaseOrder order = new PurchaseOrder(
            42L,
            OrderStatus.SHIPPED
        );

        given(repository.findById(42L))
            .willReturn(Optional.of(order));

        mockMvc.perform(
                get("/orders/42")
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.tracking.href").exists());
    }
}
~~~

Đây là ví dụ cấu trúc kiểm thử; constructor, repository và cấu hình test cần điều chỉnh theo ứng dụng. Nếu endpoint repository được cấu hình khác, hãy dùng đúng route thực tế.

Bổ sung kiểm thử cho các trường hợp:

1. Đơn hàng SHIPPED có link tracking.
2. Đơn hàng chưa SHIPPED không có link tracking.
3. Link tracking trỏ đến đúng endpoint và đúng ID.
4. Request đến endpoint tracking được xử lý đúng.
5. Collection response vẫn giữ các link phân trang mặc định.
6. Các link association mặc định của Spring Data REST vẫn còn sau khi processor chạy.
7. Người dùng không có quyền vẫn bị từ chối tại endpoint, kể cả khi biết URL.

Có thể kiểm tra response HAL bằng JSON path, ví dụ:

~~~java
jsonPath("$._links.self.href").exists()
jsonPath("$._links.tracking.href").exists()
jsonPath("$._links.customer.href").exists()
~~~

Ngoài việc kiểm tra link xuất hiện, nên gọi thử endpoint đích để xác nhận link có thể điều hướng thực sự.

## 11. Quy trình triển khai thực tế

1. Xác định resource representation cần mở rộng: item, collection, paged collection hay custom model.
2. Xác định relation name có ý nghĩa và endpoint đích tương ứng.
3. Tạo hoặc xác nhận controller method xử lý endpoint đích.
4. Viết processor với generic type khớp representation cần xử lý.
5. Đăng ký processor bằng **@Component** trong package được Spring scan.
6. Dùng **linkTo(methodOn(...))** để tạo link từ controller mapping.
7. Thêm link bằng **model.add(...)** và trả lại model.
8. Kiểm tra điều kiện nghiệp vụ, quyền truy cập và hiệu năng.
9. Gọi repository endpoint với **Accept: application/hal+json**.
10. Kiểm tra relation và href trong response; gọi thử endpoint đích.
11. Kiểm tra các link mặc định không bị mất và collection pagination vẫn hoạt động.

## 12. Bài tập tự luyện

Cho PurchaseOrder có các trạng thái CREATED, PAID, SHIPPED và COMPLETED:

1. Tạo một endpoint custom để trả về thông tin tracking của đơn hàng.
2. Viết **RepresentationModelProcessor<EntityModel<PurchaseOrder>>** để bổ sung relation tracking khi đơn hàng ở trạng thái SHIPPED.
3. Thêm relation invoice khi đơn hàng đã PAID.
4. Giải thích vì sao processor không thay thế việc kiểm tra quyền tại controller.
5. Tạo một custom representation model chứa ID, status và customerName.
6. Viết processor cho custom model để bổ sung link đến trang chi tiết đơn hàng.
7. Viết kiểm thử xác nhận link xuất hiện đúng trạng thái và href trỏ đến đúng endpoint.
8. Giải thích vì sao truy vấn repository cho từng entity trong processor có thể gây N+1 query.

**Ghi nhớ:** RepresentationModelProcessor là nơi mở rộng hypermedia link trên representation. Dùng EntityModel processor cho item resource, chọn đúng collection/paged model khi cần xử lý collection, và dùng custom DTO/model khi muốn thay đổi cấu trúc dữ liệu. Link giúp client khám phá khả năng của API; endpoint vẫn chịu trách nhiệm xác thực, phân quyền và thực thi nghiệp vụ.

## Tài liệu tham khảo

- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/reference/server/representation-models.html)
- [Spring HATEOAS — Hypermedia and Link Building](https://docs.spring.io/spring-hateoas/reference/server/links.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
