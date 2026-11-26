# Tránh processor ẩn logic

Spring HATEOAS cung cấp **RepresentationModelProcessor** để bổ sung hoặc điều chỉnh hypermedia sau khi representation đã được tạo. Cơ chế này hữu ích khi một mối quan hệ cần được công bố trên nhiều response, chẳng hạn mọi biểu diễn đơn hàng đều có thêm link đến chức năng thanh toán do một controller khác quản lý.

Tuy nhiên, processor được Spring HATEOAS tự động áp dụng cho các representation model phù hợp với kiểu generic mà processor khai báo. Controller thường không gọi processor trực tiếp, nên một bean được thêm vào ApplicationContext có thể làm thay đổi response ở nhiều endpoint mà người đọc controller không nhìn thấy. Nếu đưa truy vấn dữ liệu, quy tắc nghiệp vụ, kiểm tra quyền hoặc quyết định trạng thái vào processor, logic quan trọng sẽ bị ẩn khỏi luồng xử lý chính.

Bài học này giải thích cách hoạt động của processor, phân biệt phần việc phù hợp với processor và assembler, nhận diện các dấu hiệu logic bị ẩn, xử lý thứ tự và kiểu model, cũng như kiểm thử để bảo đảm response không thay đổi ngoài dự kiến.

Các ví dụ dùng representation đơn hàng với kiểu trạng thái rõ ràng:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

enum OrderStatus {
    AWAITING_PAYMENT, PROCESSING, DELIVERED
}

record OrderRepresentation(
    UUID id,
    OrderStatus status,
    BigDecimal total
) {}
~~~

Các lớp controller, service và domain còn lại đại diện cho thành phần sẵn có trong ứng dụng.

Handler đích của link thanh toán có thể được khai báo như sau:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/payments")
public class PaymentController {

    @GetMapping("/orders/{orderId}")
    public EntityModel<PaymentRepresentation> forOrder(
            @PathVariable UUID orderId) {
        return paymentAssembler.toModel(
            paymentService.findForOrder(orderId)
        );
    }
}
~~~

## 1. RepresentationModelProcessor làm gì?

**RepresentationModelProcessor<T>** là SPI trong package **org.springframework.hateoas.server**. Nó nhận một representation model, thực hiện hậu xử lý và trả về model đã xử lý:

~~~java
public interface RepresentationModelProcessor<
        T extends RepresentationModel<?>> {

    T process(T model);
}
~~~

Processor thường được đăng ký như một Spring bean. Trong Spring MVC, hạ tầng Spring HATEOAS phát hiện các processor và áp dụng chúng cho giá trị trả về từ controller khi kiểu model phù hợp.

Ví dụ, hệ thống đơn hàng đã có **EntityModel<OrderRepresentation>** với link self. Một chức năng thanh toán do **PaymentController** quản lý cần bổ sung link thanh toán vào biểu diễn đơn hàng. Có thể dùng processor để thêm link đó mà không buộc assembler đơn hàng phải biết chi tiết controller thanh toán.

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class PaymentLinkProcessor implements
        RepresentationModelProcessor<EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> process(
            EntityModel<OrderRepresentation> model) {

        OrderRepresentation order = model.getContent();

        Link payment = linkTo(
            methodOn(PaymentController.class).forOrder(order.id())
        ).withRel("payments");

        if (!model.hasLink("payments")) {
            model.add(payment);
        }

        return model;
    }
}
~~~

Processor này có một trách nhiệm hẹp: thêm relation **payments** vào representation đơn hàng. Nó không truy vấn database, không thay đổi trạng thái đơn hàng và không thực hiện thanh toán.

Spring HATEOAS tự áp dụng processor phù hợp trong luồng xử lý response của Spring MVC. Vì vậy, controller chỉ cần trả representation model như bình thường; không cần gọi **process(...)** thủ công.

## 2. Vì sao processor có thể làm logic bị ẩn?

Xét controller:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    Order order = service.findById(id);
    return assembler.toModel(order);
}
~~~

Đọc riêng controller, ta thấy response được tạo từ assembler. Nhưng nếu ApplicationContext còn có các processor sau:

- Processor thêm link thanh toán.
- Processor thêm link quản trị.
- Processor đổi relation hoặc xóa link cũ.
- Processor đọc quyền người dùng rồi thay đổi các link.
- Processor truy vấn dữ liệu liên quan trước khi thêm link.

thì response thực tế không còn được quyết định chỉ bởi controller và assembler.

Đây là điểm khiến processor dễ che giấu logic: nó hoạt động ở một giai đoạn hậu xử lý tự động và có thể tác động đến nhiều endpoint cùng trả về kiểu model tương thích.

Một số hệ quả thường gặp:

1. **Khó truy vết response:** developer đọc controller và assembler nhưng không thấy nơi thêm hoặc thay đổi link.
2. **Phạm vi ảnh hưởng rộng:** một processor có thể tác động đến nhiều controller cùng trả về kiểu representation.
3. **Khó kiểm soát điều kiện:** logic phụ thuộc trạng thái hoặc người dùng có thể bị phân tán qua nhiều processor.
4. **Khó kiểm thử đầy đủ:** unit test assembler không chạy qua cơ chế tự động áp dụng processor.
5. **Phụ thuộc thứ tự:** nhiều processor cùng sửa một model có thể tạo kết quả khó đoán nếu chúng phụ thuộc vào thay đổi của nhau.

Processor không phải cơ chế xấu. Vấn đề xuất hiện khi dùng nó để giấu những quyết định mà người đọc luồng nghiệp vụ cần nhìn thấy.

## 3. Phân chia trách nhiệm giữa assembler, service và processor

Một cách tổ chức dễ hiểu là để mỗi thành phần sở hữu một loại quyết định.

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Controller | Nhận request, gọi service và chọn response HTTP | Trả tài nguyên đơn hàng hoặc 404 |
| Service/domain | Thực thi quy tắc nghiệp vụ và kiểm tra điều kiện | Xác định đơn hàng có thể thanh toán hay hủy |
| RepresentationModelAssembler | Tạo DTO/model, ánh xạ dữ liệu và link đặc thù tài nguyên | Tạo self, customer, cancel |
| RepresentationModelProcessor | Bổ sung hypermedia dùng chung sau khi model đã được tạo | Thêm link thanh toán chung cho mọi đơn hàng |
| Security layer | Xác thực và phân quyền request | Chặn người dùng không có quyền hủy đơn |

Assembler phù hợp với những link phụ thuộc trực tiếp vào tài nguyên và trạng thái nghiệp vụ của nó. Service hoặc domain model nên sở hữu quy tắc quyết định hành động có hợp lệ hay không. Processor phù hợp với việc bổ sung liên kết chung, tách biệt với trách nhiệm tạo representation ban đầu.

Một nguyên tắc hữu ích: nếu cần đọc controller để hiểu một quyết định nghiệp vụ, hãy đặt quyết định đó trong service/domain hoặc assembler được controller gọi rõ ràng. Chỉ dùng processor khi hậu xử lý tự động là một đặc tính có chủ đích của hợp đồng hypermedia.

## 4. Ví dụ: đặt logic hành động trong assembler

Giả sử link **cancel** chỉ được công bố khi đơn hàng đang ở trạng thái cho phép hủy. Đây là quy tắc nghiệp vụ ảnh hưởng trực tiếp đến khả năng thao tác của tài nguyên.

Không nên giấu điều kiện này trong một processor toàn cục nếu nó chỉ thuộc về biểu diễn đơn hàng. Hãy đặt điều kiện trong assembler:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus(),
            order.getTotal()
        );

        var model = EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(order.getId()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Khi đọc **toModel**, người review nhìn thấy ngay điều kiện tạo link cancel. Quy tắc **canCancel()** thuộc domain model hoặc được quyết định bởi service/domain policy; assembler chỉ dùng kết quả để xây representation.

Nếu khả năng hủy phụ thuộc quyền của người dùng, hãy để security/domain service xác định quyền và truyền kết quả phù hợp vào quá trình tạo representation. Không xem sự xuất hiện hoặc vắng mặt của link là cơ chế bảo vệ endpoint. Endpoint cancel vẫn phải kiểm tra quyền và trạng thái ở phía server khi nhận request.

## 5. Khi nào processor là lựa chọn phù hợp?

Processor phù hợp khi cần bổ sung một đặc tính hypermedia có phạm vi rõ ràng, dùng chung cho một kiểu representation và không làm thay đổi quy tắc nghiệp vụ cốt lõi.

Các trường hợp thường phù hợp:

- Bổ sung link đến chức năng thuộc một bounded context khác mà nhiều response cùng cần.
- Thêm link tài liệu hoặc profile dùng chung cho một kiểu representation.
- Bổ sung một relation chuẩn hóa ở cấp collection.
- Thêm một link điều hướng dựa trên dữ liệu đã có sẵn trong model.
- Áp dụng một quy tắc trình bày hypermedia thống nhất cho mọi representation thuộc một kiểu cụ thể.

Ví dụ tài liệu trợ giúp cho mọi đơn hàng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderDocumentationProcessor implements
        RepresentationModelProcessor<EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> process(
            EntityModel<OrderRepresentation> model) {

        if (!model.hasLink("describedby")) {
            model.add(
                Link.of("/docs/orders")
                    .withRel("describedby")
                    .withTitle("Tài liệu về tài nguyên đơn hàng")
            );
        }

        return model;
    }
}
~~~

Link **describedby** có cùng ý nghĩa cho mọi representation đơn hàng. Processor không cần biết endpoint nào đã tạo model và không cần đọc trạng thái đơn hàng để quyết định nghiệp vụ.

Nếu một link chỉ xuất hiện ở một endpoint hoặc phụ thuộc vào một quyết định nghiệp vụ phức tạp, assembler thường là nơi phù hợp hơn.

## 6. Dấu hiệu processor đang chứa quá nhiều logic

Hãy xem lại thiết kế nếu **process(...)** có một hoặc nhiều dấu hiệu sau:

| Dấu hiệu | Vì sao đáng lo | Hướng xử lý |
|---|---|---|
| Gọi repository hoặc query database | Response phụ thuộc I/O ẩn ở giai đoạn hậu xử lý | Chuẩn bị dữ liệu trong service trước khi assemble |
| Gọi REST client hoặc message broker | Tạo thêm phụ thuộc và lỗi mạng ngoài luồng controller | Điều phối trong service/application layer |
| Thực thi chuyển trạng thái hoặc ghi dữ liệu | Processor biến bước dựng response thành nơi có side effect | Đưa hành động vào service/domain command |
| Tự quyết định quyền truy cập | Có thể làm client hiểu link là quyền thực thi | Dùng Spring Security và kiểm tra quyền tại endpoint |
| Chứa nhiều nhánh nghiệp vụ | Quy tắc quan trọng bị tách khỏi luồng chính | Đưa policy vào domain/service, assembler chỉ dùng kết quả |
| Thay đổi content của model | Dữ liệu response bị biến đổi sau khi assembler hoàn tất | Ánh xạ content ở assembler hoặc DTO mapper |
| Phụ thuộc processor khác chạy trước | Kết quả khó hiểu khi thứ tự thay đổi | Thiết kế processor độc lập hoặc khai báo thứ tự rõ |
| Tạo link với nhiều quy tắc riêng từng endpoint | Processor trở thành nơi tập hợp logic controller | Tạo link trong assembler tương ứng |

Một processor có thể đọc content để tạo link. Tuy nhiên, đọc dữ liệu đã có sẵn khác với tự truy xuất dữ liệu mới hoặc thực thi nghiệp vụ. Hãy giữ processor nhanh, dễ dự đoán và tập trung vào việc làm giàu hypermedia.

## 7. Không dùng processor làm hàng rào bảo mật

Một link không phải token cấp quyền. Việc bỏ link **cancel** khỏi response chỉ giúp client nhận biết thao tác không được công bố ở thời điểm đó; nó không ngăn request được gửi trực tiếp.

Ví dụ, client có thể giữ response cũ khi đơn hàng còn ở trạng thái PROCESSING. Sau đó đơn hàng chuyển sang DELIVERED, nhưng client vẫn gửi request đến URI cancel đã lưu.

Endpoint phải kiểm tra lại điều kiện:

~~~java
@PostMapping("/{id}/cancellation")
public ResponseEntity<Void> cancel(@PathVariable UUID id) {
    Order order = service.findById(id);

    authorizationService.assertCanCancel(order);
    service.cancel(order);

    return ResponseEntity.noContent().build();
}
~~~

Processor có thể bổ sung link dựa trên representation, nhưng không thay thế xác thực, phân quyền hoặc kiểm tra trạng thái ở endpoint. Không đặt logic từ chối request hoặc thay đổi HTTP status trong processor.

Nếu link phụ thuộc quyền người dùng, hãy quyết định quyền ở security/domain layer và tạo representation từ kết quả đã xác định. Nếu dùng processor để thêm link theo quyền, bảo đảm việc kiểm tra quyền chỉ là phần trình bày nhất quán và endpoint vẫn thực thi kiểm tra độc lập.

## 8. Phạm vi áp dụng theo generic type

Processor khai báo kiểu model mà nó xử lý:

~~~java
@Component
public class PaymentLinkProcessor implements
        RepresentationModelProcessor<EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> process(
            EntityModel<OrderRepresentation> model) {
        // ...
        return model;
    }
}
~~~

Spring HATEOAS phân tích kiểu generic của các processor đã đăng ký để tìm processor phù hợp với representation model được trả về. Vì vậy, kiểu generic là một phần quan trọng của phạm vi áp dụng.

Ví dụ:

| Processor khai báo | Model mục tiêu |
|---|---|
| **RepresentationModelProcessor<EntityModel<OrderRepresentation>>** | Representation đơn hàng dạng EntityModel |
| **RepresentationModelProcessor<EntityModel<CustomerRepresentation>>** | Representation khách hàng dạng EntityModel |
| **RepresentationModelProcessor<CollectionModel<EntityModel<OrderRepresentation>>>** | Collection đơn hàng có phần tử EntityModel |
| **RepresentationModelProcessor<OrderModel>** | Model tùy chỉnh OrderModel |

Không nên dùng một processor với kiểu quá tổng quát rồi kiểm tra hàng loạt **instanceof** hoặc ép kiểu content bên trong. Kiểu generic cụ thể giúp Spring HATEOAS giới hạn processor và giúp người đọc hiểu phạm vi tác động ngay tại khai báo.

Processor cũng cần được đăng ký như Spring bean để hạ tầng phát hiện. Có thể dùng **@Component** hoặc khai báo **@Bean** trong cấu hình:

~~~java
@Configuration
public class HypermediaConfiguration {

    @Bean
    PaymentLinkProcessor paymentLinkProcessor() {
        return new PaymentLinkProcessor();
    }
}
~~~

Không đăng ký cùng một processor bằng nhiều cách, vì điều đó có thể khiến cùng một xử lý được áp dụng lặp lại.

## 9. Cẩn thận với CollectionModel rỗng

Với **CollectionModel**, hạ tầng cần xác định kiểu phần tử để chọn processor phù hợp. Khi collection có phần tử, Spring HATEOAS có thể kiểm tra các phần tử thực tế. Khi collection rỗng, Java type erasure khiến runtime không thể suy ra kiểu payload từ content.

Theo mặc định, processor nhắm đến một kiểu phần tử có thể không được gọi cho collection rỗng nếu hạ tầng không xác định được kiểu. Hãy khai báo fallback type khi collection có thể rỗng:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.core.ParameterizedTypeReference;

CollectionModel<EntityModel<OrderRepresentation>> orders =
    CollectionModel.empty(
        new ParameterizedTypeReference<
            EntityModel<OrderRepresentation>>() {}
    );
~~~

Hoặc gắn fallback type vào collection được tạo từ truy vấn:

~~~java
CollectionModel<EntityModel<OrderRepresentation>> orders =
    CollectionModel.of(items)
        .withFallbackType(
            new ParameterizedTypeReference<
                EntityModel<OrderRepresentation>>() {}
        );
~~~

Ví dụ processor ở cấp collection:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderCollectionProcessor implements
        RepresentationModelProcessor<
            CollectionModel<EntityModel<OrderRepresentation>>> {

    @Override
    public CollectionModel<EntityModel<OrderRepresentation>> process(
            CollectionModel<EntityModel<OrderRepresentation>> model) {

        if (!model.hasLink(IanaLinkRelations.SELF)) {
            model.add(
                linkTo(methodOn(OrderController.class).all())
                    .withSelfRel()
            );
        }

        return model;
    }
}
~~~

Nếu collection rỗng và không có fallback type, processor có thể không được chọn. Vì vậy, test cần có cả collection có phần tử lẫn collection rỗng. Đây là vấn đề suy luận kiểu runtime, không phải do phương thức **process(...)** không xử lý được collection rỗng.

## 10. Tránh phụ thuộc thứ tự giữa các processor

Một ứng dụng có thể có nhiều processor cùng áp dụng cho một kiểu model. Ví dụ:

- Processor A thêm link customer.
- Processor B kiểm tra link customer rồi thêm link customer-profile.
- Processor C chuẩn hóa hoặc loại bỏ một relation.

Nếu processor B chỉ hoạt động khi A đã chạy, kết quả sẽ phụ thuộc thứ tự. Điều này làm logic khó đọc và dễ thay đổi khi thêm bean mới.

Ưu tiên thiết kế mỗi processor độc lập, không yêu cầu processor khác chạy trước. Nếu thứ tự thực sự là một phần của thiết kế, hãy khai báo thứ tự rõ ràng bằng cơ chế ordering của Spring như **@Order** hoặc **Ordered**, sau đó kiểm thử kết quả cuối cùng qua luồng MVC.

Không nên dùng thứ tự như một cách thay thế cho việc phân chia trách nhiệm. Nếu hai processor phải phối hợp chặt chẽ để tạo một representation, có thể chúng nên được gộp thành một assembler hoặc một component rõ ràng được gọi từ assembler.

## 11. Giữ processor idempotent và tránh link trùng

Processor có thể gặp một model đã có link do assembler thêm trước đó. Nếu processor luôn thêm cùng relation mà không kiểm tra, response có thể chứa nhiều link tương đương.

Dùng **hasLink(...)** để tránh thêm lặp:

~~~java
@Override
public EntityModel<OrderRepresentation> process(
        EntityModel<OrderRepresentation> model) {

    if (!model.hasLink("payments")) {
        model.add(
            linkTo(methodOn(PaymentController.class)
                .forOrder(model.getContent().id()))
                .withRel("payments")
        );
    }

    return model;
}
~~~

Nếu processor có thể được gọi nhiều lần trong test hoặc trong luồng tích hợp tùy chỉnh, việc kiểm tra trước khi thêm giúp kết quả ổn định hơn. Một processor tốt nên có hành vi idempotent: xử lý lại cùng một model không làm phát sinh thêm link trùng hoặc thay đổi kết quả không cần thiết.

Không nên xóa toàn bộ link hiện có rồi xây lại trong processor trừ khi đó là trách nhiệm được định nghĩa rõ. Hành vi đó có thể vô tình xóa self link, relation do assembler thêm hoặc affordance.

## 12. Kiểm thử processor trực tiếp

Unit test cho processor xác nhận logic hậu xử lý riêng biệt. Ví dụ:

~~~java
@Test
void addsPaymentLinkToOrderModel() {
    OrderRepresentation order = new OrderRepresentation(
        orderId,
        OrderStatus.AWAITING_PAYMENT,
        new BigDecimal("125000")
    );

    EntityModel<OrderRepresentation> model =
        EntityModel.of(order);

    EntityModel<OrderRepresentation> processed =
        processor.process(model);

    assertThat(processed.hasLink("payments")).isTrue();
}
~~~

Nếu processor có guard để tránh link trùng, kiểm thử thêm trường hợp model đã có relation:

~~~java
@Test
void doesNotAddDuplicatePaymentRelation() {
    EntityModel<OrderRepresentation> model =
        EntityModel.of(orderRepresentation)
            .add(existingPaymentLink);

    EntityModel<OrderRepresentation> processed =
        processor.process(model);

    assertThat(processed.getLinks("payments"))
        .containsExactly(existingPaymentLink);
}
~~~

Tên kiểu và trường trong ví dụ cần khớp với DTO của ứng dụng. Unit test này chỉ kiểm tra phương thức **process(...)**; nó chưa chứng minh Spring MVC tự động phát hiện và gọi processor.

## 13. Kiểm thử cơ chế tự động áp dụng processor

Vì processor được Spring HATEOAS áp dụng trong quá trình xử lý giá trị trả về của controller, cần có integration test để xác nhận bean được phát hiện và response HTTP thực sự chứa link.

Ví dụ với MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderProcessorIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void processorAddsPaymentLinkToMvcResponse() throws Exception {
        mockMvc.perform(get("/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.payments.href").exists());
    }
}
~~~

Test cần cấu hình dữ liệu đơn hàng hoặc mock service để endpoint trả đúng representation. Nếu dùng **@WebMvcTest**, hãy import processor bean vào test slice; nếu không, processor có thể không nằm trong ApplicationContext của test.

Nên có test âm để bảo vệ phạm vi áp dụng: một kiểu model khác không được nhận link chỉ dành cho đơn hàng. Cũng nên kiểm tra endpoint trả **CollectionModel** nếu ứng dụng có processor nhắm đến collection.

## 14. Kiểm thử và quan sát khi có nhiều processor

Khi response bị thay đổi ngoài dự kiến, hãy kiểm tra theo thứ tự:

1. Xác định kiểu model controller thực sự trả về.
2. Liệt kê các bean **RepresentationModelProcessor** trong ApplicationContext.
3. Đối chiếu generic type của từng processor với kiểu representation.
4. Kiểm tra processor nào được gọi trong integration test.
5. Xác định link được thêm, thay đổi hoặc xóa ở processor nào.
6. Kiểm tra ordering nếu các processor có phụ thuộc.
7. Kiểm tra collection rỗng có fallback type khi processor nhắm đến phần tử collection.

Có thể dùng log ở mức debug trong môi trường phát triển hoặc breakpoint trong **process(...)** để xác định processor nào tác động đến model. Không nên để log nhạy cảm như content đầy đủ, thông tin người dùng hoặc dữ liệu nghiệp vụ bí mật.

Một quy ước hữu ích là đặt tên processor theo kiểu model và mục tiêu link, ví dụ **OrderPaymentLinkProcessor** hoặc **OrderCollectionNavigationProcessor**. Tránh các tên chung chung như **GlobalModelProcessor** nếu bean thực tế chỉ sửa một nhóm tài nguyên.

## 15. Spring MVC và WebFlux

API **RepresentationModelProcessor** được tài liệu Spring HATEOAS mô tả là SPI xử lý representation model được trả về từ Spring MVC controller. Không nên mặc định rằng một bean processor sẽ tự động chạy trong mọi luồng WebFlux theo cùng cơ chế.

Với WebFlux, hãy tạo link trong reactive pipeline bằng **WebFluxLinkBuilder** và dùng **ReactiveRepresentationModelAssembler** để chuyển đổi dữ liệu. Nếu muốn dùng một quy tắc bổ sung chung, có thể tạo component riêng và gọi rõ ràng trong assembler reactive, giữ kết quả trong **Mono** thay vì chặn luồng bằng **block()**.

Ví dụ:

~~~java
public Mono<EntityModel<OrderRepresentation>> toModel(
        Order order, ServerWebExchange exchange) {

    return createBaseModel(order, exchange)
        .map(paymentLinkEnricher::addPaymentLink);
}
~~~

Ở đây **paymentLinkEnricher** là component ứng dụng do ta chủ động gọi; nó không được giả định là processor MVC tự động. Cách gọi tường minh giúp nhìn thấy bước bổ sung link trong reactive pipeline và dễ kiểm thử bằng StepVerifier.

## 16. Checklist để tránh processor ẩn logic

Trước khi thêm một **RepresentationModelProcessor**, hãy tự xác nhận:

1. Processor chỉ xử lý một kiểu representation có phạm vi rõ ràng.
2. Nhiệm vụ chính là bổ sung hypermedia dùng chung sau khi model đã được assemble.
3. Không truy vấn database hoặc gọi dịch vụ mạng trong **process(...)**.
4. Không thay đổi trạng thái domain hoặc thực thi nghiệp vụ.
5. Không dùng việc ẩn link làm cơ chế phân quyền.
6. Quy tắc hành động quan trọng nằm trong service/domain và được thể hiện rõ qua assembler.
7. Processor không phụ thuộc vào một processor khác nếu có thể tránh.
8. Có guard để không thêm link trùng.
9. Collection processor có test cho collection rỗng và fallback type.
10. Có unit test cho logic process và integration test cho cơ chế tự động áp dụng.
11. Các bean processor được đăng ký có chủ đích và có tên mô tả trách nhiệm.
12. WebFlux dùng luồng reactive tường minh thay vì giả định processor MVC tự chạy.

**RepresentationModelProcessor** phù hợp để bổ sung hypermedia chung sau khi assembler đã tạo representation. Khi giữ processor nhỏ, không có side effect và có phạm vi generic rõ ràng, cơ chế tự động này giúp chia sẻ link giữa các phần của API mà không làm mờ logic nghiệp vụ. Những quyết định về trạng thái, quyền và hành động vẫn cần được thể hiện ở service/domain và assembler để người đọc có thể lần theo luồng xử lý từ controller đến response.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation Model Processors](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RepresentationModelProcessor API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html)
- [RepresentationModelProcessorInvoker API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelProcessorInvoker.html)
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring Framework Ordering](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)

