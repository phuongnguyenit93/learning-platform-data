# Processor cho representation

Trong Spring HATEOAS, **`RepresentationModelProcessor`** là cơ chế hậu xử lý một representation model trước khi model được chuyển thành HTTP response. Processor nhận một kiểu model cụ thể, có thể bổ sung hoặc điều chỉnh các link, rồi trả lại model đã xử lý. Cách này hữu ích khi nhiều endpoint cần cùng một quy tắc liên kết hoặc khi một link chỉ nên xuất hiện theo trạng thái tài nguyên và quyền của người gọi.

Ví dụ, một đơn hàng đang chờ xử lý và người dùng hiện tại có quyền hủy có thể cung cấp link `cancel`. Khi đơn hàng đã được giao hoặc người gọi không có quyền, representation không công bố link đó. Processor giúp tập trung quy tắc tạo link vào một thành phần riêng, thay vì lặp lại trong từng controller.

## Processor nằm ở đâu trong quá trình tạo representation?

Một luồng xử lý thường gồm các bước:

1. Controller lấy dữ liệu nghiệp vụ từ service hoặc repository.
2. Assembler chuyển đối tượng nghiệp vụ thành `EntityModel`, `CollectionModel` hoặc một kiểu `RepresentationModel` phù hợp và gắn những link cơ bản.
3. Spring HATEOAS tìm các `RepresentationModelProcessor` đã được đăng ký có kiểu phù hợp với model được trả về, rồi áp dụng chúng trong quá trình xử lý response.
4. Message converter tuần tự hóa model thành representation theo media type đã chọn, ví dụ HAL JSON.

Processor làm việc với representation model đã được tạo. Nó không thay thế controller, không tự truy vấn hoặc chuyển đổi mọi domain object thành DTO, và cũng không thay thế message converter. Trách nhiệm của nó là xử lý model theo kiểu mà processor khai báo.

## Giao diện `RepresentationModelProcessor`

Giao diện có dạng tổng quát `RepresentationModelProcessor<T extends RepresentationModel<?>>`. Kiểu `T` xác định loại representation model mà processor nhận và trả về. Phương thức chính là:

```java
T process(T model);
```

Processor có thể thêm link vào model rồi trả lại chính model đó, hoặc tạo và trả về một model đã điều chỉnh. Trong ứng dụng Spring, processor thường được đăng ký như một bean, ví dụ với `@Component`, để hạ tầng Spring HATEOAS có thể phát hiện và áp dụng.

Một điểm quan trọng là kiểu generic phải khớp với model mà endpoint thực sự trả về. Nếu endpoint trả `EntityModel<OrderRepresentation>`, một processor khai báo cho `EntityModel<CustomerRepresentation>` sẽ không xử lý model đơn hàng đó. Hãy chọn kiểu rõ ràng và giữ hợp đồng giữa controller, assembler và processor nhất quán.

## Ví dụ: thêm link hủy đơn hàng theo điều kiện

Giả sử API dùng DTO sau làm nội dung của representation:

```java
import java.math.BigDecimal;

public record OrderRepresentation(
    Long id,
    String status,
    BigDecimal total
) {}
```

Controller cung cấp endpoint chi tiết và endpoint hủy:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService orderQueryService;
    private final OrderCommandService orderCommandService;

    OrderController(OrderQueryService orderQueryService,
                    OrderCommandService orderCommandService) {
        this.orderQueryService = orderQueryService;
        this.orderCommandService = orderCommandService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        return orderQueryService.getModel(id);
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        return orderQueryService.getAllModels();
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable Long id) {
        orderCommandService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

`orderQueryService` và `orderCommandService` đại diện cho các thành phần nghiệp vụ của ứng dụng. Link hủy được tạo trong processor:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderActionProcessor implements
        RepresentationModelProcessor<EntityModel<OrderRepresentation>> {

    private final OrderActionPolicy actionPolicy;

    OrderActionProcessor(OrderActionPolicy actionPolicy) {
        this.actionPolicy = actionPolicy;
    }

    @Override
    public EntityModel<OrderRepresentation> process(
            EntityModel<OrderRepresentation> model) {

        OrderRepresentation order = model.getContent();
        if (order == null) {
            return model;
        }

        if (actionPolicy.canCancel(order.id())) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel"));
        }

        return model;
    }
}
```

`OrderActionPolicy.canCancel(id)` là chính sách của ứng dụng, cần xác định liệu đơn hàng còn ở trạng thái cho phép hủy và người gọi hiện tại có quyền thực hiện hành động đó hay không. Processor chỉ công bố link khi chính sách trả về `true`. Link được tạo bằng `methodOn(...)` nên URI được suy ra từ mapping của controller, giảm việc ghép chuỗi URL thủ công.

Khi response được tuần tự hóa thành HAL JSON, một đơn hàng đủ điều kiện có thể có cấu trúc như sau:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancel"
    }
  }
}
```

Nếu chính sách từ chối thao tác, link `cancel` không xuất hiện. Client có thể kiểm tra relation `cancel` để quyết định có hiển thị nút hủy hay không; client không cần tự suy luận từ chuỗi trạng thái hoặc tự tạo endpoint.

## Processor và assembler khác nhau thế nào?

Hai thành phần đều có thể thêm link nhưng phục vụ các điểm khác nhau trong quá trình xây representation:

| Thành phần | Đầu vào | Trách nhiệm phù hợp |
| --- | --- | --- |
| Controller | HTTP request và tham số route | Điều phối use case, gọi service và trả model. |
| `RepresentationModelAssembler` | Domain object hoặc DTO nguồn | Tạo representation model, ánh xạ dữ liệu và các link gắn với tài nguyên. |
| `RepresentationModelProcessor` | Representation model đã được tạo | Hậu xử lý một kiểu model, bổ sung quy tắc link dùng chung hoặc có điều kiện. |

Ví dụ, assembler của đơn hàng có thể luôn thêm `self`, `orders` và `customer`. Processor có thể bổ sung `cancel` khi trạng thái và quyền hiện tại cho phép. Nếu một link chỉ thuộc về một endpoint hoặc một cách biểu diễn riêng, đặt nó trong assembler thường dễ theo dõi hơn. Nếu một quy tắc cần áp dụng nhất quán cho mọi model cùng kiểu, processor có thể là lựa chọn phù hợp.

Không nên để cả assembler lẫn processor cùng chịu trách nhiệm thêm một relation giống nhau. Hãy xác định một nơi sở hữu mỗi quy tắc link để tránh liên kết trùng lặp và hành vi khó dự đoán.

## Dùng processor cho collection hoặc nhiều loại model

Processor có thể khai báo cho kiểu model khác, chẳng hạn một collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderCollectionProcessor implements
        RepresentationModelProcessor<CollectionModel<EntityModel<OrderRepresentation>>> {

    @Override
    public CollectionModel<EntityModel<OrderRepresentation>> process(
            CollectionModel<EntityModel<OrderRepresentation>> model) {

        model.add(linkTo(methodOn(OrderController.class).all())
            .withSelfRel());
        return model;
    }
}
```

Ví dụ giả định `OrderController.all()` trả về đúng kiểu collection được khai báo. Processor này bổ sung link `self` cho collection. Trong ứng dụng thực tế, nếu assembler đã thêm link đó thì không cần thêm lần nữa; ví dụ chỉ minh họa việc chọn kiểu model cho processor.

Có thể đăng ký nhiều processor cho các loại model khác nhau. Hãy giữ mỗi processor tập trung vào một quy tắc dễ hiểu, tránh tạo một processor tổng quát chứa quá nhiều nhánh điều kiện theo nhiều loại tài nguyên.

## Link, affordance và giới hạn của processor

Một link như `cancel` cho client biết có đường dẫn mang quan hệ hủy đơn. Tuy nhiên, link đơn thuần không nhất thiết mô tả đầy đủ HTTP method, các trường request body hoặc kiểu dữ liệu đầu vào. Nếu client cần biết chi tiết tương tác, Spring HATEOAS hỗ trợ gắn affordance với link và biểu diễn chúng qua media type có khả năng thể hiện affordance.

Processor có thể bổ sung link hoặc affordance nếu đó là quy tắc hậu xử lý của model. Dù vậy, việc link xuất hiện hay vắng mặt chỉ là tín hiệu điều hướng cho client. Server vẫn phải xác thực, phân quyền và kiểm tra trạng thái nghiệp vụ ở endpoint khi nhận request. Người dùng có thể gọi trực tiếp URI hủy dù link không xuất hiện, vì vậy không được dùng việc ẩn link như một biện pháp bảo mật.

Processor cũng không nên thực hiện nghiệp vụ làm thay đổi dữ liệu. Phương thức `process` nên tập trung vào representation và link; thao tác ghi dữ liệu thuộc command service được gọi từ endpoint tương ứng. Nếu processor cần quyết định link theo trạng thái hoặc quyền, hãy dựa vào một policy/service có trách nhiệm rõ ràng và cân nhắc chi phí truy vấn để tránh phát sinh nhiều truy vấn cho collection lớn.

## Kiểm thử processor qua HTTP response

Nên kiểm thử response cuối cùng để xác nhận processor thực sự được đăng ký và link được tuần tự hóa đúng. Ví dụ với MockMvc và HAL JSON:

```java
mockMvc.perform(get("/orders/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với trường hợp không được phép hủy, kiểm tra relation không được công bố:

```java
mockMvc.perform(get("/orders/43")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Các đoạn kiểm thử giả định `MockMvc`, `MediaTypes.HAL_JSON`, `jsonPath` và dữ liệu kiểm thử đã được cấu hình. Nên kiểm tra ít nhất các tình huống: trạng thái cho phép và người dùng có quyền; trạng thái không cho phép; người dùng thiếu quyền; model không có nội dung nếu ứng dụng cho phép trường hợp đó; và URI link được tạo đúng theo mapping. Nếu processor phụ thuộc vào người dùng hiện tại, thiết lập security context tương ứng trong từng test.

## Những lỗi thiết kế thường gặp

- **Khai báo sai kiểu generic:** processor không được áp dụng cho model endpoint trả về. Đối chiếu kiểu trả về thực tế của controller với kiểu processor.
- **Đặt mọi logic vào processor:** processor trở thành nơi tập trung nghiệp vụ, truy vấn và điều phối. Giữ nghiệp vụ trong service hoặc policy, chỉ để processor quyết định cách biểu diễn.
- **Thêm link lặp:** assembler và processor cùng tạo một relation. Chỉ định rõ thành phần chịu trách nhiệm cho từng link.
- **Tưởng link là bảo mật:** client vẫn có thể tự gửi request. Endpoint phải kiểm tra quyền và trạng thái độc lập.
- **Không kiểm thử response cuối:** unit test gọi trực tiếp `process()` không xác nhận cấu hình Spring, thứ tự xử lý hoặc serialization. Bổ sung integration test qua HTTP khi cần xác nhận hợp đồng.

`RepresentationModelProcessor` phù hợp khi cần hậu xử lý representation theo một quy tắc có thể tái sử dụng. Kết hợp assembler để tạo model ban đầu, processor để bổ sung link theo chính sách và integration test để kiểm tra response giúp API Spring HATEOAS giữ được các quan hệ hypermedia nhất quán khi số lượng endpoint tăng lên.
