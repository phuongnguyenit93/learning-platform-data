# Processor theo kiểu model

Trong Spring HATEOAS, RepresentationModelAssembler chịu trách nhiệm tạo representation từ domain object. Tuy nhiên, có những liên kết cần bổ sung sau khi model đã được tạo, chẳng hạn liên kết thanh toán cho đơn hàng, liên kết hỗ trợ cho khách hàng hoặc liên kết phụ thuộc vào quyền của người dùng hiện tại. Nếu đưa tất cả các mối quan tâm này vào assembler hoặc controller chính, các lớp đó dễ biết quá nhiều về những chức năng thuộc module khác.

Spring HATEOAS cung cấp RepresentationModelProcessor để xử lý một representation model sau khi nó được tạo. Điểm quan trọng là processor được khai báo với kiểu model cụ thể bằng generic. Ví dụ, RepresentationModelProcessor<EntityModel<OrderDto>> chỉ nhắm đến model đơn hàng dạng EntityModel<OrderDto>. Spring HATEOAS dùng khai báo kiểu này để chọn processor phù hợp với model đang được trả về.

Bài học này giải thích cách hoạt động của processor theo kiểu model, cách đăng ký bean, cách bổ sung liên kết mà không trộn trách nhiệm giữa các controller, cách xử lý collection rỗng và cách kiểm thử kết quả hypermedia.

## 1. Model processor giải quyết vấn đề gì?

Giả sử OrderController quản lý vòng đời đơn hàng. Controller và OrderModelAssembler tạo representation chứa mã đơn, trạng thái, tổng tiền và link self. Một module thanh toán lại cần bổ sung link để client khám phá thông tin thanh toán của đơn hàng đang chờ thanh toán.

Nếu thêm logic thanh toán trực tiếp vào OrderModelAssembler, assembler phải phụ thuộc vào PaymentController hoặc các quy tắc riêng của module thanh toán. Nếu đưa logic vào OrderController, controller đơn hàng phải biết thêm về chức năng thanh toán. Khi có nhiều module cần bổ sung liên kết, các lớp này sẽ ngày càng phức tạp.

RepresentationModelProcessor cho phép xử lý model sau khi assembler đã hoàn tất:

~~~mermaid
flowchart TD
    A["Domain object: Order"] --> B["OrderModelAssembler"]
    B --> C["EntityModel<OrderDto>"]
    C --> D["PaymentLinkProcessor"]
    D --> E["Representation đã bổ sung link"]
    E --> F["HAL serializer"]
    F --> G["HTTP response"]
~~~

Luồng xử lý:

1. Service truy xuất domain object và thực hiện use case.
2. Assembler chuyển domain object thành representation model.
3. Processor nhận model đã tạo và bổ sung hoặc điều chỉnh liên kết theo kiểu model mà nó hỗ trợ.
4. Spring tuần tự hóa model đã xử lý thành media type mà client yêu cầu.

Processor phù hợp với những thay đổi mang tính bổ sung hoặc xuyên suốt nhiều endpoint. Nó không thay thế assembler và không nên trở thành nơi thực hiện toàn bộ nghiệp vụ.

## 2. RepresentationModelProcessor là gì?

Interface của Spring HATEOAS nằm trong package org.springframework.hateoas.server:

~~~java
public interface RepresentationModelProcessor<
        T extends RepresentationModel<?>
> {

    T process(T model);
}
~~~

T là kiểu representation model mà processor xử lý. Một số kiểu phổ biến:

| Kiểu model | Mục đích |
| --- | --- |
| EntityModel<OrderDto> | Model của một đơn hàng |
| CollectionModel<OrderDto> | Model của collection đơn hàng chứa các DTO |
| PagedModel<OrderDto> | Model của collection có metadata phân trang |
| OrderRepresentation | Kiểu model tùy chỉnh kế thừa RepresentationModel |

Phương thức process nhận model đã được tạo và trả về model sau xử lý. Processor có thể thêm link, thay đổi link hoặc điều chỉnh dữ liệu representation nếu hợp đồng API cho phép.

Kiểu trả về phải tương thích với kiểu đầu vào đã khai báo. Ví dụ, processor nhận EntityModel<OrderDto> phải trả EntityModel<OrderDto>. Không thể nhận EntityModel<OrderDto> rồi trả CollectionModel<OrderDto> từ cùng processor.

## 3. Processor được chọn theo generic model type

Điểm cốt lõi của chủ đề là kiểu generic quyết định processor nào có thể xử lý model:

~~~java
public class OrderProcessor
        implements RepresentationModelProcessor<EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> process(EntityModel<OrderDto> model) {
        // Xử lý model đơn hàng.
        return model;
    }
}
~~~

Processor trên nhắm đến EntityModel<OrderDto>. Nó không phải processor chung cho mọi EntityModel và cũng không phải processor cho CollectionModel<OrderDto>.

Có thể hình dung các khai báo:

| Khai báo processor | Model được nhắm đến |
| --- | --- |
| RepresentationModelProcessor<EntityModel<OrderDto>> | EntityModel chứa OrderDto |
| RepresentationModelProcessor<EntityModel<CustomerDto>> | EntityModel chứa CustomerDto |
| RepresentationModelProcessor<CollectionModel<OrderDto>> | CollectionModel chứa OrderDto |
| RepresentationModelProcessor<PagedModel<OrderDto>> | PagedModel chứa OrderDto |

Spring HATEOAS phân tích generic declaration của các processor đã đăng ký để xác định processor phù hợp. Điều này giúp các module đăng ký processor chuyên biệt mà không cần controller gọi thủ công từng processor.

Không nên dùng RepresentationModelProcessor<RepresentationModel<?>> chỉ để xử lý mọi model nếu logic thực tế chỉ áp dụng cho một loại tài nguyên. Khai báo kiểu càng cụ thể thì phạm vi tác động càng dễ hiểu và kiểm thử.

## 4. Tạo processor cho EntityModel<OrderDto>

Ví dụ hệ thống đơn hàng có trạng thái:

~~~java
public enum OrderStatus {
    AWAITING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

DTO được dùng trong representation:

~~~java
import java.math.BigDecimal;

public record OrderDto(
        Long id,
        OrderStatus status,
        BigDecimal total
) {
}
~~~

PaymentController cung cấp endpoint để xem thông tin thanh toán theo đơn hàng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/payments")
public class PaymentController {

    @GetMapping("/orders/{orderId}")
    public EntityModel<PaymentDto> forOrder(
            @PathVariable Long orderId
    ) {
        // Truy vấn thông tin thanh toán của đơn hàng.
        return paymentService.getModelForOrder(orderId);
    }
}
~~~

Processor bổ sung link payment khi đơn hàng đang chờ thanh toán:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class PaymentLinkProcessor
        implements RepresentationModelProcessor<EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> process(EntityModel<OrderDto> model) {
        OrderDto order = model.getContent();

        if (order.status() == OrderStatus.AWAITING_PAYMENT
                && !model.hasLink("payment")) {
            model.add(linkTo(methodOn(PaymentController.class)
                    .forOrder(order.id())).withRel("payment"));
        }

        return model;
    }
}
~~~

Processor chỉ quan tâm đến EntityModel<OrderDto>. Nó đọc trạng thái và mã đơn hàng từ payload, sau đó thêm link đến PaymentController khi điều kiện phù hợp. Điều kiện hasLink giúp tránh thêm lại relation payment nếu model đã có liên kết đó.

Link được tạo bằng WebMvcLinkBuilder nên dựa trên mapping của PaymentController. Nếu mapping thay đổi, processor vẫn tham chiếu đến phương thức controller thay vì phải sửa một chuỗi URL được hard-code.

Trước khi processor chạy, response của đơn hàng có thể chỉ có link self:

~~~json
{
  "id": 42,
  "status": "AWAITING_PAYMENT",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    }
  }
}
~~~

Sau khi processor thêm relation payment, HAL representation có thể trở thành:

~~~json
{
  "id": 42,
  "status": "AWAITING_PAYMENT",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "payment": {
      "href": "https://api.example.com/api/payments/orders/42"
    }
  }
}
~~~

## 5. Đăng ký processor vào Spring ApplicationContext

Processor cần được đăng ký thành Spring bean để cơ chế xử lý representation tìm thấy nó. Có thể dùng @Component như ví dụ trước hoặc khai báo @Bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentProcessorConfiguration {

    @Bean
    PaymentLinkProcessor paymentLinkProcessor() {
        return new PaymentLinkProcessor();
    }
}
~~~

Chỉ cần đăng ký một cách. Nếu lớp đã có @Component và nằm trong phạm vi component scan, không khai báo thêm @Bean cho cùng instance.

Trong Spring MVC, Spring HATEOAS tích hợp processor vào quá trình xử lý giá trị trả về của controller. Khi controller trả một RepresentationModel phù hợp, các processor đã đăng ký được xem xét và áp dụng trước khi representation được tuần tự hóa.

Điều này có nghĩa controller không cần viết:

~~~java
return paymentLinkProcessor.process(orderAssembler.toModel(order));
~~~

Controller vẫn trả model do assembler tạo. Hạ tầng Spring HATEOAS thực hiện bước hậu xử lý dựa trên generic model type của processor.

## 6. Phân biệt assembler và processor

RepresentationModelAssembler và RepresentationModelProcessor đều làm việc với representation nhưng có vai trò khác nhau:

| Tiêu chí | RepresentationModelAssembler | RepresentationModelProcessor |
| --- | --- | --- |
| Đầu vào | Domain object hoặc dữ liệu nguồn | RepresentationModel đã được tạo |
| Đầu ra | RepresentationModel mới | RepresentationModel cùng kiểu đã xử lý |
| Mục đích | Ánh xạ dữ liệu và tạo link cơ bản cho resource | Bổ sung hoặc điều chỉnh representation sau assembly |
| Kiến thức chính | Domain type và API representation | Model type và mối quan tâm cần bổ sung |
| Thường được dùng ở | Controller hoặc service trình bày | Hạ tầng hậu xử lý model của Spring HATEOAS |

Assembler phù hợp với các trường dữ liệu và link cốt lõi của resource. Processor phù hợp với những liên kết bổ sung thuộc một module khác hoặc một mối quan tâm dùng chung.

Ví dụ, OrderModelAssembler tạo link self, customer và cancel dựa trên dữ liệu đơn hàng. PaymentLinkProcessor thêm link payment cho các đơn hàng đang chờ thanh toán. Hai thành phần có trách nhiệm riêng và không cần phụ thuộc trực tiếp vào nhau.

## 7. Processor theo kiểu CollectionModel

Processor cũng có thể nhắm đến collection model. Ví dụ sau dùng CollectionModel<OrderDto>, nghĩa là collection chứa các DTO trực tiếp:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderCollectionProcessor
        implements RepresentationModelProcessor<CollectionModel<OrderDto>> {

    @Override
    public CollectionModel<OrderDto> process(
            CollectionModel<OrderDto> model
    ) {
        if (!model.hasLink("self")) {
            model.add(linkTo(methodOn(OrderController.class)
                    .all()).withSelfRel());
        }

        return model;
    }
}
~~~

Processor này nhắm đến CollectionModel<OrderDto>, không phải CollectionModel<EntityModel<OrderDto>>. Hai kiểu generic khác nhau và cần được khai báo đúng với kiểu controller thực sự trả về.

Nếu controller trả CollectionModel<EntityModel<OrderDto>>, processor cần khai báo đúng kiểu collection đó:

~~~java
RepresentationModelProcessor<
        CollectionModel<EntityModel<OrderDto>>
>
~~~

Không nên giả định processor của EntityModel<OrderDto> sẽ tự động xử lý mọi collection chứa các EntityModel<OrderDto>. Cần xác định rõ model nào là đối tượng trả về ở cấp controller và model nào là phần tử nằm bên trong collection.

## 8. Collection rỗng và Java type erasure

Một trường hợp dễ bỏ sót là collection rỗng. Spring HATEOAS xác định processor phù hợp bằng cách phân tích generic declaration và, với CollectionModel, có thể kiểm tra các phần tử bên trong collection. Tuy nhiên, khi collection rỗng, runtime không còn phần tử để suy ra kiểu payload. Java type erasure cũng không giữ đầy đủ generic type của đối tượng ở runtime.

Vì vậy, processor cho CollectionModel mặc định không được gọi với collection rỗng nếu hạ tầng không thể suy ra kiểu phần tử.

Có thể cung cấp fallback type ngay khi tạo collection rỗng:

~~~java
CollectionModel<OrderDto> emptyOrders =
        CollectionModel.empty(OrderDto.class);
~~~

Hoặc cung cấp fallback type cho collection có thể rỗng:

~~~java
CollectionModel<OrderDto> orders =
        CollectionModel.of(orderDtos)
                .withFallbackType(OrderDto.class);
~~~

Fallback type cho phép Spring HATEOAS suy ra payload type để lựa chọn processor thích hợp ngay cả khi collection không có phần tử.

Nếu processor cần áp dụng cả khi danh sách không có dữ liệu, hãy kiểm thử riêng trường hợp rỗng. Không nên chỉ kiểm thử collection có một hoặc nhiều phần tử rồi kết luận processor luôn được gọi.

## 9. Điều kiện nghiệp vụ và quyền người dùng

Processor có thể bổ sung link dựa trên trạng thái tài nguyên:

~~~java
if (order.status() == OrderStatus.AWAITING_PAYMENT) {
    model.add(paymentLink);
}
~~~

Trong một ứng dụng thực tế, khả năng thực hiện thao tác có thể còn phụ thuộc người dùng hiện tại. Ví dụ, chỉ nhân viên có quyền mới được xem liên kết hoàn tiền. Processor có thể sử dụng một policy hoặc authorization service để quyết định có công bố link hay không.

Nếu processor cần service:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class RefundLinkProcessor
        implements RepresentationModelProcessor<EntityModel<OrderDto>> {

    private final OrderActionPolicy actionPolicy;

    public RefundLinkProcessor(OrderActionPolicy actionPolicy) {
        this.actionPolicy = actionPolicy;
    }

    @Override
    public EntityModel<OrderDto> process(EntityModel<OrderDto> model) {
        OrderDto order = model.getContent();

        if (actionPolicy.canRefund(order)) {
            model.add(linkTo(methodOn(PaymentController.class)
                    .refund(order.id())).withRel("refund"));
        }

        return model;
    }
}
~~~

Ví dụ giả định OrderActionPolicy đã được cấu hình để xét quyền của principal hiện tại và trạng thái đơn hàng. Policy nên cung cấp quyết định rõ ràng; processor không nên tự chứa toàn bộ logic phân quyền.

Không nên gọi repository riêng cho từng model nếu có thể chuẩn bị dữ liệu cần thiết ở service hoặc projection. Nếu processor được gọi cho một collection có nhiều phần tử, truy vấn bổ sung từng phần tử có thể tạo N+1 query. Hãy cân nhắc tải thông tin quyền hoặc trạng thái theo lô, hoặc đưa các dữ liệu cần thiết vào model.

Link không thay thế kiểm tra bảo mật ở endpoint. Người dùng có thể lưu một URI cũ và gọi lại sau khi quyền hoặc trạng thái thay đổi. Controller và service vẫn phải xác thực, phân quyền và kiểm tra invariant tại thời điểm thực thi.

## 10. Giữ processor stateless và tránh tác động ngoài ý muốn

Processor thường được đăng ký như một Spring bean dùng chung. Hãy thiết kế processor stateless:

- Không lưu model đang xử lý vào field.
- Không ghi dữ liệu request hoặc principal hiện tại vào field dùng chung.
- Không sửa trạng thái domain object trong processor.
- Không thực hiện side effect như thanh toán, hủy đơn hoặc ghi giao dịch.
- Chỉ thay đổi representation được truyền vào và trả lại đúng kiểu model.

Processor có thể được gọi ở nhiều request đồng thời. Nếu lưu trạng thái request trong field, dữ liệu của hai request có thể trộn lẫn. Hãy dùng tham số model và các dependency an toàn theo thiết kế của Spring.

Nếu nhiều processor cùng thêm một relation, hãy quy định rõ trách nhiệm để tránh link trùng hoặc link có ý nghĩa khác nhau. Có thể kiểm tra model.hasLink("payment") trước khi thêm, hoặc dùng mapLink nếu mục tiêu là thay đổi link đã có. Không nên phụ thuộc vào thứ tự chạy giữa các processor để tạo ra kết quả đúng.

## 11. Processor trong Spring MVC, Spring Data REST và WebFlux

### Spring MVC

Spring HATEOAS tích hợp RepresentationModelProcessor vào quá trình xử lý giá trị trả về của controller MVC. Các bean processor được chọn theo kiểu model và được áp dụng trước khi response được tuần tự hóa.

### Spring Data REST

Spring Data REST cũng tích hợp Spring HATEOAS và có thể phát hiện các bean RepresentationModelProcessor để điều chỉnh representation được exporter tạo ra. Đây là cách hữu ích để thêm link vào tài nguyên được xuất bản từ repository mà không sửa controller do Spring Data REST quản lý.

### Spring WebFlux

RepresentationModelProcessor được tài liệu hóa như một SPI hậu xử lý representation trong luồng Spring MVC. Không nên mặc định rằng cơ chế handler return value của MVC tự động áp dụng y hệt cho Mono hoặc Flux trong WebFlux.

Trong WebFlux, nếu cần áp dụng logic tương tự, hãy kết hợp xử lý model trực tiếp trong reactive pipeline hoặc sử dụng ReactiveRepresentationModelAssembler để tạo representation và link theo ServerWebExchange. Ví dụ:

~~~java
return orderService.findById(id)
        .flatMap(order -> assembler.toModel(order, exchange))
        .map(paymentLinkPolicy::process);
~~~

Trong ví dụ, paymentLinkPolicy là một thành phần ứng dụng có phương thức process nhận và trả đúng kiểu model. Việc dùng map giữ xử lý trong pipeline mà không gọi block().

## 12. Kiểm thử processor bằng unit test

Unit test xác nhận processor thêm link khi trạng thái phù hợp và giữ nguyên model khi điều kiện không phù hợp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;

class PaymentLinkProcessorTest {

    private final PaymentLinkProcessor processor =
            new PaymentLinkProcessor();

    @Test
    void addsPaymentLinkWhenOrderAwaitsPayment() {
        OrderDto dto = new OrderDto(
                42L,
                OrderStatus.AWAITING_PAYMENT,
                BigDecimal.valueOf(1250000)
        );
        EntityModel<OrderDto> model = EntityModel.of(dto);

        EntityModel<OrderDto> result = processor.process(model);

        assertThat(result.hasLink("payment")).isTrue();
    }

    @Test
    void doesNotAddPaymentLinkWhenOrderIsPaid() {
        OrderDto dto = new OrderDto(
                42L,
                OrderStatus.PAID,
                BigDecimal.valueOf(1250000)
        );
        EntityModel<OrderDto> model = EntityModel.of(dto);

        EntityModel<OrderDto> result = processor.process(model);

        assertThat(result.hasLink("payment")).isFalse();
    }
}
~~~

Nếu processor có dependency như policy hoặc service, dùng constructor injection và mock dependency trong unit test. Không cần khởi động toàn bộ Spring context chỉ để kiểm tra logic thêm link.

## 13. Kiểm thử processor được tự động áp dụng trong MVC

Unit test chỉ chứng minh process hoạt động. Một kiểm thử tích hợp MVC cần xác nhận processor được đăng ký và Spring HATEOAS thực sự gọi nó khi controller trả model.

Ví dụ test slice:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import({OrderModelAssembler.class, PaymentLinkProcessor.class})
class OrderProcessorMvcTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void addsPaymentLinkToOrderResponse() throws Exception {
        Order order = new Order(
                42L,
                OrderStatus.AWAITING_PAYMENT,
                BigDecimal.valueOf(1250000)
        );
        when(orderService.getRequired(42L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.payment.href").exists());
    }
}
~~~

Đây là ví dụ test slice. Các kiểu Order, OrderDto, OrderService, OrderController, assembler và trạng thái cần được định nghĩa trong package ứng dụng. @Import đăng ký assembler và processor trong test context; service được mock để kiểm soát dữ liệu.

Nên kiểm thử thêm:

- Model thuộc kiểu khác không bị processor áp dụng.
- Processor không thêm link khi trạng thái không cho phép.
- Link không bị thêm trùng khi model đã có relation.
- Processor của collection hoạt động với collection có phần tử.
- Collection rỗng có fallback type khi cần processor chạy.
- HAL output chứa link relation và href đúng.
- Nhiều processor không tạo các relation mâu thuẫn.

## 14. Những lỗi thường gặp

**Dùng sai generic type.** Processor khai báo EntityModel<OrderDto> không nhắm đến EntityModel<CustomerDto> hoặc CollectionModel<OrderDto>. Hãy khai báo đúng kiểu controller trả về.

**Nhầm processor với assembler.** Assembler tạo model từ domain object; processor nhận model đã tạo và điều chỉnh nó. Không dùng processor để thay thế toàn bộ quy trình mapping.

**Quên đăng ký processor thành bean.** Processor không được phát hiện nếu không nằm trong ApplicationContext. Dùng @Component hoặc @Bean.

**Cho rằng mọi processor chạy trên mọi response.** Hạ tầng chọn processor theo kiểu model và generic declaration. Kiểm tra kiểu trả về thực tế của controller.

**Bỏ qua collection rỗng.** Type erasure khiến Spring HATEOAS không thể suy ra payload type từ collection không có phần tử. Dùng CollectionModel.empty(Payload.class) hoặc withFallbackType(Payload.class) khi cần.

**Đặt nghiệp vụ vào processor.** Không thực hiện thanh toán, hủy đơn hoặc thay đổi trạng thái trong process. Processor chỉ nên điều chỉnh representation.

**Thêm link trùng hoặc phụ thuộc thứ tự processor.** Xác định rõ module nào sở hữu relation, kiểm tra link hiện có và tránh phụ thuộc vào thứ tự thực thi.

**Dùng processor MVC như thể tự động hỗ trợ WebFlux.** Cơ chế handler của MVC không phải pipeline reactive. Trong WebFlux, áp dụng xử lý tường minh trong Mono/Flux pipeline hoặc dùng reactive assembler.

## 15. Ghi nhớ

RepresentationModelProcessor<T> là SPI hậu xử lý representation của Spring HATEOAS. Generic T xác định loại model mà processor nhắm đến, ví dụ EntityModel<OrderDto> hoặc CollectionModel<OrderDto>. Phương thức process nhận và trả về cùng kiểu model, cho phép bổ sung link hoặc điều chỉnh representation trước khi response được tuần tự hóa.

Hãy dùng assembler để tạo representation từ domain object và processor để bổ sung những mối quan tâm độc lập sau bước assembly. Đăng ký processor thành Spring bean để hạ tầng MVC phát hiện và áp dụng theo kiểu model. Giữ processor stateless, tránh truy vấn lặp lại và không đặt side effect nghiệp vụ trong process.

Với CollectionModel rỗng, generic type có thể không suy ra được do Java type erasure. Cung cấp fallback payload type nếu processor cần được áp dụng. Khi dùng WebFlux, xử lý tương tự một cách tường minh trong reactive pipeline thay vì giả định cơ chế MVC tự động áp dụng.

Kiểm thử cả logic processor, generic model type, collection rỗng và response HAL cuối cùng. Việc kiểm thử tích hợp giúp xác nhận processor đã được đăng ký và thực sự chạy trong pipeline trả response.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Representation Model Processors](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-processors)
- [RepresentationModelProcessor API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html)
- [RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
