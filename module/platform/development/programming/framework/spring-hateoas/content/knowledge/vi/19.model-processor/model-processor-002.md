# Xử lý model sau assembler

## Mục tiêu

Trong Spring HATEOAS, assembler chuyển domain object thành representation và thường gắn các link cần thiết cho tài nguyên. Sau bước đó, ứng dụng đôi khi cần bổ sung một số link hoặc metadata dùng chung cho nhiều response. RepresentationModelProcessor cung cấp một điểm mở rộng để xử lý representation model sau khi controller trả về model và trước khi model được serialize thành HTTP response.

Processor phù hợp với các thay đổi mang tính dùng chung, chẳng hạn bổ sung link tới collection, tài liệu API hoặc một tài nguyên liên quan cho mọi representation thuộc một kiểu nhất định. Nó giúp tách phần bổ sung xuyên suốt khỏi logic chuyển đổi từng entity trong assembler.

Sau bài học, bạn có thể:

- Giải thích vai trò của RepresentationModelProcessor.
- Phân biệt processor với RepresentationModelAssembler.
- Đăng ký processor như một Spring bean và xác định kiểu model mà nó xử lý.
- Bổ sung link sau khi assembler tạo representation.
- Chọn đúng phạm vi xử lý cho item model và collection model.
- Kiểm thử link do processor thêm vào response.

## RepresentationModelProcessor hoạt động ở đâu?

Luồng xử lý phổ biến trong một endpoint Spring MVC dùng Spring HATEOAS:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Controller]
    B --> C[Service / domain]
    C --> D[RepresentationModelAssembler]
    D --> E[EntityModel hoặc CollectionModel]
    E --> F[RepresentationModelProcessor]
    F --> G[HTTP message converter]
    G --> H[HAL JSON response]
~~~

Assembler tạo representation từ dữ liệu miền. Sau khi controller trả về một RepresentationModel, cơ chế tích hợp của Spring HATEOAS tìm các processor phù hợp trong application context và gọi chúng trước khi serialize response. Processor nhận model, có thể thêm link hoặc điều chỉnh model, rồi trả lại model.

Bạn không cần gọi processor thủ công trong controller. Đăng ký processor thành Spring bean để Spring HATEOAS tự áp dụng trong luồng xử lý hypermedia. Cơ chế này dành cho representation model, không phải một callback chung cho mọi DTO hoặc mọi object Java được controller trả về.

Processor phải nằm trong application context có cấu hình tích hợp web của Spring HATEOAS. Với Spring Boot, starter HATEOAS thường cung cấp auto-configuration cần thiết. Với ứng dụng Spring MVC cấu hình thủ công, bật hypermedia support bằng @EnableHypermediaSupport. @Component chỉ đăng ký bean; nếu package không được component scan, hãy khai báo processor bằng @Bean trong cấu hình.

## Khai báo một processor

RepresentationModelProcessor<T> là interface nhận và trả về kiểu T, trong đó T là một kiểu kế thừa RepresentationModel. Ví dụ, controller trả EntityModel<OrderResponse>; processor có thể nhắm đúng kiểu này:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderCollectionLinkProcessor
        implements RepresentationModelProcessor<EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> process(
            EntityModel<OrderResponse> model) {

        if (!model.hasLink(IanaLinkRelations.COLLECTION)) {
            model.add(linkTo(methodOn(OrderController.class)
                    .findAll())
                    .withRel(IanaLinkRelations.COLLECTION));
        }

        return model;
    }
}
~~~

Trong ví dụ:

1. @Component đăng ký processor thành bean để Spring HATEOAS phát hiện.
2. Generic type EntityModel<OrderResponse> xác định kiểu representation mà processor nhận.
3. process(...) bổ sung link collection nếu link đó chưa có.
4. Phương thức trả về model đã xử lý để framework tiếp tục serialize.

methodOn(...) chỉ tham chiếu mapping của controller để tạo URI; nó không thực thi findAll() hoặc gọi service. Kiểm tra hasLink(...) trước khi thêm giúp tránh tạo link trùng nếu assembler hoặc một processor khác đã cung cấp relation đó.

Generic type là một phần quan trọng của cách Spring HATEOAS chọn processor. Processor cho EntityModel<OrderResponse> được thiết kế cho representation item có kiểu đó; processor cho CollectionModel<EntityModel<OrderResponse>> nhắm tới representation collection tương ứng. Khi đổi kiểu trả về của controller hoặc kiểu model trong assembler, hãy rà soát lại processor và kiểm thử HTTP để xác nhận processor vẫn được áp dụng.

## Assembler và processor có trách nhiệm khác nhau

Hai thành phần đều có thể thêm link, nhưng điểm áp dụng và mục đích khác nhau:

| RepresentationModelAssembler | RepresentationModelProcessor |
|---|---|
| Chuyển một domain object thành representation. | Xử lý representation đã được tạo. |
| Thường gắn links phụ thuộc dữ liệu hoặc trạng thái của entity. | Thường bổ sung links hoặc metadata dùng chung cho một kiểu model. |
| Được gọi rõ ràng từ controller hoặc từ assembler collection/paging. | Được Spring HATEOAS gọi tự động khi representation phù hợp đi qua luồng xử lý. |
| Có thể tạo self, cancel, approve dựa trên trạng thái đơn hàng. | Có thể thêm collection, profile hoặc help cho nhóm response cùng kiểu. |

Ví dụ, assembler có thể tạo link cancel chỉ khi đơn hàng đang ở trạng thái PENDING, vì đây là quyết định gắn với từng đơn hàng. Processor có thể bổ sung link collection cho mọi EntityModel<OrderResponse> để client luôn có đường quay về danh sách.

Không chuyển toàn bộ logic assembler sang processor. Assembler vẫn là nơi thích hợp để ánh xạ domain object, tạo DTO và công bố hành động phụ thuộc trạng thái. Processor nên tập trung vào những thay đổi có thể áp dụng sau bước đó.

## Ví dụ hoàn chỉnh: assembler tạo item, processor bổ sung collection link

Giả sử endpoint chi tiết trả về EntityModel<OrderResponse>:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> findById(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> findAll() {
        return assembler.toCollectionModel(orderService.findAll());
    }
}
~~~

Assembler tạo nội dung và link self:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        return EntityModel.of(
                OrderResponse.from(order),
                linkTo(methodOn(OrderController.class)
                        .findById(order.getId())).withSelfRel());
    }
}
~~~

Sau đó OrderCollectionLinkProcessor ở phần trước thêm link collection vào model. Kết quả response chi tiết có thể chứa cả hai relation:

~~~json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/order-42"
    },
    "collection": {
      "href": "/api/orders"
    }
  }
}
~~~

Assembler không cần biết processor nào sẽ bổ sung link collection. Điều đó giảm sự phụ thuộc giữa chuyển đổi từng entity và chính sách điều hướng dùng chung.

## Xử lý collection model

Processor phải khai báo đúng kiểu representation mà controller trả về. Nếu controller trả CollectionModel<EntityModel<OrderResponse>> và muốn thêm link ở cấp collection, có thể tạo processor riêng:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderCollectionProcessor
        implements RepresentationModelProcessor<
                CollectionModel<EntityModel<OrderResponse>>> {

    @Override
    public CollectionModel<EntityModel<OrderResponse>> process(
            CollectionModel<EntityModel<OrderResponse>> model) {

        if (!model.hasLink(IanaLinkRelations.SELF)) {
            model.add(linkTo(methodOn(OrderController.class)
                    .findAll()).withSelfRel());
        }

        return model;
    }
}
~~~

Processor này xử lý link ở cấp collection. Links self hoặc action của từng item vẫn nên được tạo bởi item assembler. Không giả định processor của CollectionModel sẽ tự chạy đệ quy trên từng EntityModel nằm bên trong; hãy gắn link item tại nơi tạo item và kiểm thử cả hai cấp.

Một processor khác có thể nhắm tới custom model, ví dụ OrderModel extends RepresentationModel<OrderModel>. Kiểu generic phải khớp representation mà controller thực sự trả về. Nếu controller đổi từ EntityModel<OrderResponse> sang OrderModel, cần điều chỉnh processor tương ứng.

## Chọn phạm vi và tránh xử lý trùng

Trước khi tạo processor, xác định chính xác nhóm representation cần bổ sung:

- Chỉ item đơn hàng: dùng RepresentationModelProcessor<EntityModel<OrderResponse>>.
- Chỉ collection đơn hàng: dùng RepresentationModelProcessor<CollectionModel<EntityModel<OrderResponse>>>.
- Một custom representation: dùng đúng lớp custom kế thừa RepresentationModel.

Không dùng một processor quá tổng quát nếu chỉ một nhóm tài nguyên cần link đó. Processor nhắm tới RepresentationModel<?> có thể ảnh hưởng nhiều loại response hơn dự kiến và làm hợp đồng API khó theo dõi.

Processor nên có thể được áp dụng an toàn. Kiểm tra relation đã tồn tại trước khi thêm, tránh tạo link lặp khi nhiều thành phần cùng cung cấp một relation. Nếu nhiều processor cùng xử lý một kiểu model, giữ mỗi processor có một trách nhiệm rõ ràng và kiểm thử kết quả cuối cùng; đừng để thứ tự xử lý ngầm quyết định nội dung nghiệp vụ.

## Khi nào nên dùng processor?

Processor phù hợp khi một thay đổi được áp dụng cho nhiều response cùng kiểu và không cần biết endpoint nào đã tạo model. Ví dụ:

- Thêm link profile trỏ tới tài liệu mô tả representation.
- Bổ sung link collection cho các item thuộc cùng một resource type.
- Thêm link help hoặc tài liệu hướng dẫn chung.
- Chuẩn hóa một metadata hypermedia dùng chung cho nhiều endpoint.

Assembler phù hợp hơn khi:

- Link phụ thuộc dữ liệu của từng entity.
- Hành động phụ thuộc trạng thái hiện tại, như cancel hoặc approve.
- Cấu trúc response thay đổi theo use case hoặc endpoint cụ thể.
- Cần chuyển đổi domain object thành DTO/custom model.

Nếu logic chỉ áp dụng cho một endpoint và không cần tái sử dụng, có thể thêm link trực tiếp trong assembler hoặc controller. Processor không phải lớp bắt buộc cho mọi response HATEOAS.

## Kiểm thử processor

Kiểm thử HTTP bằng MockMvc xác minh processor đã được Spring HATEOAS gọi và link xuất hiện trong response:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.collection.href")
                .value("http://localhost/api/orders"));
~~~

Host tuyệt đối trong assertion phụ thuộc cấu hình MockMvc và request context. Nếu môi trường test dùng base URL khác, hãy kiểm tra path hoặc cấu hình host phù hợp thay vì cố định địa chỉ không ổn định.

Có thể kiểm thử riêng phương thức process(...) để xác minh processor không thêm relation trùng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

EntityModel<OrderResponse> input = EntityModel.of(response);

EntityModel<OrderResponse> once = processor.process(input);
EntityModel<OrderResponse> twice = processor.process(once);

assertThat(twice.getLinks(IanaLinkRelations.COLLECTION)).hasSize(1);
~~~

Test này giả định processor kiểm tra hasLink(...) trước khi thêm collection relation. Ngoài ra, nên có test cho collection processor để xác minh link self được đặt ở cấp collection và links của từng item vẫn giữ nguyên.

## Những lỗi thường gặp

- **Nhầm processor với assembler:** assembler tạo representation từ domain object; processor xử lý model đã được tạo.
- **Gọi processor thủ công trong controller:** với Spring HATEOAS integration, đăng ký bean để framework áp dụng trong luồng xử lý model.
- **Chọn sai generic type:** processor chỉ nên nhắm tới kiểu representation mà controller thực sự trả về.
- **Mong processor collection xử lý mọi item đệ quy:** tạo link item trong assembler của item; processor collection xử lý model cấp collection.
- **Thêm link trùng:** kiểm tra relation trước khi thêm hoặc xác định một nơi duy nhất sở hữu relation đó.
- **Đưa quy tắc nghiệp vụ vào processor dùng chung:** hành động phụ thuộc trạng thái nên được quyết định ở service/domain và phản ánh trong assembler.
- **Dùng processor quá rộng:** processor tổng quát có thể làm thay đổi những representation không liên quan.
- **Không kiểm thử response cuối:** kiểm thử riêng processor chưa chứng minh framework đã tự áp dụng bean trong HTTP flow.

## Quy trình xử lý model sau assembler

1. Xác định phần dữ liệu và links thuộc trách nhiệm assembler.
2. Tìm metadata hoặc link dùng chung cần bổ sung sau khi model được tạo.
3. Chọn đúng kiểu model làm generic type của RepresentationModelProcessor<T>.
4. Đăng ký processor bằng @Component hoặc khai báo bean trong cấu hình Spring.
5. Trong process(...), bổ sung link cần thiết, kiểm tra relation hiện có và trả model.
6. Dùng MockMvc xác minh processor được áp dụng trong response thực tế và không tạo link trùng.

RepresentationModelProcessor bổ sung một bước xử lý sau assembler để các quy tắc hypermedia dùng chung không phải lặp lại ở mọi nơi tạo model. Khi giới hạn processor đúng kiểu representation và giữ logic theo trạng thái trong assembler, API có thể tái sử dụng links chung mà vẫn giữ rõ trách nhiệm của từng thành phần.
