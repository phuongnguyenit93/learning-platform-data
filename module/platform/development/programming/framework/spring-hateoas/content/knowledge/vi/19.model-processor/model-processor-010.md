# Kiểm thử processor

Trong Spring HATEOAS, `RepresentationModelProcessor<T>` cho phép bổ sung hoặc điều chỉnh một representation sau khi controller hoặc assembler đã tạo xong model. Processor thường dùng cho những liên kết cần được bổ sung xuyên nhiều luồng, chẳng hạn link thanh toán cho đơn hàng đang chờ thanh toán hoặc link hỗ trợ theo ngữ cảnh người dùng. Kiểm thử processor cần xác nhận logic xử lý model, điều kiện thêm link và việc Spring tự động áp dụng processor trước khi response được tuần tự hóa.

`RepresentationModelProcessor<T>` có một phương thức `process(T model)` và trả về model sau xử lý. Kiểu generic `T` xác định loại representation mà processor nhắm tới, ví dụ `EntityModel<OrderResponse>` hoặc `CollectionModel<EntityModel<OrderResponse>>`. Spring HATEOAS phân tích kiểu này để chọn processor phù hợp khi xử lý giá trị trả về từ controller Spring MVC.

## Processor khác assembler như thế nào?

Assembler tạo representation từ đối tượng nghiệp vụ. Processor nhận representation đã được tạo và điều chỉnh thêm. Hai thành phần có thể cùng tham gia vào một response nhưng giải quyết hai trách nhiệm khác nhau.

| Thành phần | Thời điểm | Trách nhiệm | Ví dụ |
|---|---|---|---|
| `RepresentationModelAssembler` | Khi chuyển domain object thành model | Tạo content và các link cốt lõi của tài nguyên | `Order` thành `EntityModel<OrderResponse>` với `self`, `customer` |
| `RepresentationModelProcessor` | Sau khi model được tạo | Bổ sung hoặc điều chỉnh thông tin hypermedia theo mối quan tâm dùng chung | Thêm link `payment` cho đơn hàng đang chờ thanh toán |

Ví dụ, `OrderController` và `OrderModelAssembler` chỉ cần hiểu về đơn hàng. Một processor riêng có thể bổ sung link thanh toán mà không buộc phần xử lý đơn hàng phải phụ thuộc trực tiếp vào `PaymentController`.

Processor nên tập trung vào việc điều chỉnh representation. Tránh biến nó thành nơi thực hiện thao tác ghi dữ liệu hoặc điều phối quy trình nghiệp vụ. Nếu link phụ thuộc capability hoặc quyền người dùng, processor có thể nhận thông tin từ một service chuyên trách; endpoint đích vẫn phải kiểm tra quyền khi client gửi request.

## Cách Spring áp dụng processor

Một processor được đăng ký thành Spring bean, chẳng hạn bằng `@Component` hoặc `@Bean`. Với Spring MVC, cơ chế xử lý giá trị trả về sẽ tìm processor có kiểu generic phù hợp với `RepresentationModel` mà controller trả về, gọi `process(...)`, rồi chuyển model đã xử lý cho bước ghi HTTP response.

```mermaid
flowchart TD
    A[HTTP request] --> B[Controller gọi service / assembler]
    B --> C[EntityModel hoặc CollectionModel]
    C --> D[Spring tìm RepresentationModelProcessor phù hợp]
    D --> E[process(model)]
    E --> F[RepresentationModel đã xử lý]
    F --> G[HTTP message converter]
    G --> H[HAL JSON response]
```

Điểm quan trọng khi kiểm thử là gọi trực tiếp `processor.process(model)` chỉ kiểm tra logic bên trong processor. Nó không xác nhận processor đã được đăng ký thành bean hoặc Spring MVC đã tự động gọi processor. Muốn xác nhận toàn bộ luồng, cần có kiểm thử tích hợp gọi endpoint thực tế.

## Ví dụ processor thêm link thanh toán

Giả sử API trả đơn hàng với trạng thái và ID:

```java
import java.util.UUID;

public enum OrderStatus {
    AWAITING_PAYMENT,
    PAID,
    CANCELLED
}

public record OrderResponse(UUID id, OrderStatus status) {}
```

Processor chỉ thêm link `payment` khi đơn hàng đang chờ thanh toán. Nó cũng kiểm tra relation đã có để tránh thêm trùng link nếu model đã được xử lý trước đó:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class PaymentLinkProcessor
        implements RepresentationModelProcessor<EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> process(EntityModel<OrderResponse> model) {
        OrderResponse order = model.getContent();

        if (order != null
                && order.status() == OrderStatus.AWAITING_PAYMENT
                && !model.hasLink("payment")) {
            model.add(Link.of("/api/payments/" + order.id()).withRel("payment"));
        }

        return model;
    }
}
```

Processor có kiểu `RepresentationModelProcessor<EntityModel<OrderResponse>>`, nên nó nhắm tới representation `EntityModel<OrderResponse>`. Nó không xử lý một DTO bất kỳ hoặc `EntityModel<CustomerResponse>`. Điều kiện trạng thái giúp link chỉ xuất hiện khi khả năng thanh toán được công bố. Việc kiểm tra `hasLink("payment")` giúp xử lý lặp lại an toàn hơn.

## Unit test cho phương thức process()

Unit test nên kiểm tra từng nhánh logic bằng cách tạo model trực tiếp rồi gọi `process(...)`. Không cần khởi động Spring context nếu processor không phụ thuộc bean khác.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;

class PaymentLinkProcessorTest {

    private final PaymentLinkProcessor processor = new PaymentLinkProcessor();

    @Test
    void addsPaymentLinkWhenOrderAwaitsPayment() {
        UUID id = UUID.fromString("2c13c6a2-53e4-4ef4-9b6b-8d3a9a1c0123");
        EntityModel<OrderResponse> model = EntityModel.of(
                new OrderResponse(id, OrderStatus.AWAITING_PAYMENT)
        );

        EntityModel<OrderResponse> result = processor.process(model);

        assertTrue(result.hasLink("payment"));
        assertEquals("/api/payments/" + id,
                result.getRequiredLink("payment").getHref());
    }

    @Test
    void doesNotAddPaymentLinkWhenOrderIsAlreadyPaid() {
        UUID id = UUID.randomUUID();
        EntityModel<OrderResponse> model = EntityModel.of(
                new OrderResponse(id, OrderStatus.PAID)
        );

        EntityModel<OrderResponse> result = processor.process(model);

        assertFalse(result.hasLink("payment"));
    }
}
```

Hai test kiểm tra trường hợp link phải xuất hiện và trường hợp link phải vắng mặt. Có thể bổ sung test khi model đã có link `payment` để xác nhận processor không thêm relation trùng. Nếu processor nhận một collaborator như `PaymentCapabilityService`, hãy mock collaborator và kiểm tra processor sử dụng kết quả capability đúng cách.

Unit test này không xác nhận cơ chế generic dispatch của Spring. Nó chỉ xác nhận rằng khi được gọi với một model, processor xử lý model đó đúng.

## Kiểm thử Spring MVC tự động gọi processor

Để xác nhận processor được đăng ký và áp dụng tự động, tạo một controller trả `EntityModel<OrderResponse>`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        OrderResponse order = new OrderResponse(id, OrderStatus.AWAITING_PAYMENT);

        return EntityModel.of(
                order,
                Link.of("/api/orders/" + id).withSelfRel()
        );
    }
}
```

Vì `PaymentLinkProcessor` là `@Component`, Spring Boot sẽ đăng ký bean khi package của nó được component scan. Kiểm thử tích hợp bằng MockMvc xác nhận link được thêm vào response HAL:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PaymentLinkProcessorMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void processorAddsPaymentLinkToControllerResponse() throws Exception {
        UUID id = UUID.fromString("2c13c6a2-53e4-4ef4-9b6b-8d3a9a1c0123");

        mockMvc.perform(get("/api/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.payment.href")
                    .value("/api/payments/" + id));
    }
}
```

Test này đi qua Spring MVC return-value handling và HTTP message converter. Nếu unit test `process(...)` thành công nhưng assertion `_links.payment` trong MockMvc thất bại, hãy kiểm tra processor có phải Spring bean không, generic type có khớp kiểu model controller trả về không và cấu hình Spring HATEOAS có được nạp trong test context không.

## Kiểm thử processor cho loại model khác

Processor có thể nhắm tới `CollectionModel` thay vì `EntityModel`. Ví dụ, processor cấp collection thêm link tìm kiếm vào danh sách đơn hàng:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderCollectionProcessor implements
        RepresentationModelProcessor<CollectionModel<EntityModel<OrderResponse>>> {

    @Override
    public CollectionModel<EntityModel<OrderResponse>> process(
            CollectionModel<EntityModel<OrderResponse>> model
    ) {
        if (!model.hasLink("search")) {
            model.add(Link.of("/api/orders/search").withRel("search"));
        }
        return model;
    }
}
```

Khi collection có phần tử, cơ chế dispatch có thể phân tích kiểu của các phần tử để xác định processor phù hợp. Nhưng với collection rỗng, Java type erasure khiến runtime không thể suy ra đầy đủ kiểu phần tử chỉ từ nội dung collection. Theo mặc định, processor nhắm tới collection có thể không được gọi cho một `CollectionModel` rỗng.

Để cung cấp kiểu phần tử dự phòng, tạo collection rỗng cùng `fallbackType`:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

CollectionModel<EntityModel<OrderResponse>> emptyOrders =
        CollectionModel.<EntityModel<OrderResponse>>empty()
                .withFallbackType(
                        new ParameterizedTypeReference<EntityModel<OrderResponse>>() {}
                );
```

Hoặc với collection chứa một kiểu phần tử đơn giản, dùng `CollectionModel.empty(OrderModel.class)` hoặc `withFallbackType(OrderModel.class)`. Khi test processor cho collection, cần có ít nhất một trường hợp collection rỗng để phát hiện lỗi dispatch do thiếu thông tin kiểu.

## Kiểm thử processor cho collection rỗng

Unit test gọi trực tiếp `process(...)` vẫn có thể thành công dù Spring không tự chọn processor cho collection rỗng. Vì vậy, nên có một test tích hợp trả collection rỗng qua controller và xác nhận link do processor thêm vẫn xuất hiện.

Ví dụ phương thức controller:

```java
@GetMapping
public CollectionModel<EntityModel<OrderResponse>> all() {
    return CollectionModel.<EntityModel<OrderResponse>>empty()
            .withFallbackType(
                    new ParameterizedTypeReference<EntityModel<OrderResponse>>() {}
            );
}
```

Trong MockMvc, gọi `GET /api/orders` với `Accept: application/hal+json` và xác nhận:

```java
mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.href").value("/api/orders/search"));
```

Test này kiểm tra đồng thời việc giữ fallback type, generic matching, đăng ký processor và HAL serialization. Nếu bỏ `withFallbackType(...)`, processor có thể không được gọi cho collection rỗng dù test gọi trực tiếp `process(...)` vẫn pass.

## Kiểm thử nhiều processor và tính ổn định

Một ứng dụng có thể có nhiều processor cùng nhắm tới một loại representation, ví dụ processor thêm link thanh toán và processor thêm link hỗ trợ. Khi đó, kiểm thử nên xác nhận response cuối có đủ các relation cần thiết và không có link ngoài điều kiện.

Nếu một processor phụ thuộc vào thay đổi của processor khác, tránh dựa vào thứ tự ngầm định. Hãy thiết kế các processor độc lập hoặc gom logic có thứ tự bắt buộc vào một thành phần có trách nhiệm rõ ràng. Khi dự án chủ động cấu hình thứ tự bean, hãy kiểm tra hành vi thực tế trong integration test thay vì chỉ kiểm tra từng `process(...)` riêng lẻ.

Processor nên có tính lặp an toàn (idempotent) khi có thể: chạy lại không tạo thêm link trùng hoặc làm thay đổi response ngoài dự kiến. Có thể kiểm tra điều này bằng cách gọi `process(...)` hai lần trên cùng model và xác nhận mỗi relation chỉ có một link theo hợp đồng.

## Kiểm thử processor có phụ thuộc service hoặc quyền

Spring HATEOAS cho phép processor dùng service để quyết định thêm, bỏ hoặc điều chỉnh link dựa trên trạng thái hoặc ngữ cảnh người dùng. Khi đó, unit test nên mock dependency và kiểm tra cả nhánh cho phép lẫn nhánh từ chối.

Ví dụ về cách kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Service xác nhận đơn hàng có thể thanh toán | Có link `payment` |
| Service xác nhận đơn hàng đã thanh toán | Không có link `payment` |
| Người dùng không có quyền thanh toán | Không công bố link `payment` |
| Service lỗi | Lỗi được xử lý theo chính sách ứng dụng, không âm thầm tạo link sai |

Không gọi hệ thống ngoài hoặc database thật trong unit test processor. Dùng mock hoặc fake collaborator để kiểm tra quyết định biểu diễn. Với integration test, chỉ bật những thành phần cần thiết và dùng dữ liệu test có thể kiểm soát.

## Processor trong Spring Data REST

Nếu ứng dụng dùng Spring Data REST, `RepresentationModelProcessor<EntityModel<T>>` còn là extension point để điều chỉnh representation của entity do repository exporter tạo ra. Spring Data REST tự phát hiện các bean processor phù hợp và gọi chúng khi tạo representation cho entity tương ứng.

Đường đi này khác với controller Spring MVC tự viết. Vì vậy, nếu processor được dùng cho endpoint repository export, hãy kiểm thử endpoint Spring Data REST thực tế. Test một controller tự viết không chứng minh repository exporter cũng đang áp dụng processor đúng như mong đợi.

## Những lỗi thường gặp khi kiểm thử processor

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Chỉ gọi `process()` trong unit test | Chưa kiểm tra Spring có tự gọi processor hay không | Bổ sung MockMvc integration test |
| Processor không được đăng ký thành bean | Spring không phát hiện processor | Dùng `@Component` hoặc khai báo `@Bean` |
| Generic type không khớp | Processor không được chọn cho model trả về | Khai báo đúng `RepresentationModelProcessor<EntityModel<...>>` hoặc kiểu collection tương ứng |
| Test collection chỉ có phần tử | Không phát hiện lỗi dispatch của collection rỗng | Kiểm thử empty collection và dùng `withFallbackType(...)` |
| Chỉ kiểm tra link tồn tại | `href` có thể sai hoặc relation không đúng | Kiểm tra cả relation và URI |
| Processor thêm link không điều kiện | Client thấy thao tác không phù hợp trạng thái | Kiểm thử trạng thái cho phép và không cho phép |
| Processor tạo link trùng khi chạy lại | Response có nhiều link cùng relation | Kiểm tra link đã tồn tại và test tính idempotent |
| Test controller tự viết thay cho Spring Data REST | Không kiểm tra đúng pipeline exporter | Gọi endpoint repository export trong test riêng |

## Checklist kiểm thử processor

1. Kiểm thử trực tiếp `process(model)` với từng trạng thái quan trọng.
2. Xác nhận content và các link cũ được giữ nguyên nếu processor chỉ có nhiệm vụ bổ sung link.
3. Xác nhận link mới có đúng relation và `href`.
4. Kiểm tra processor không thêm link khi điều kiện nghiệp vụ hoặc quyền không cho phép.
5. Đăng ký processor thành Spring bean và kiểm thử controller bằng MockMvc.
6. Kiểm tra response được tuần tự hóa theo media type hypermedia đã chọn.
7. Nếu xử lý `CollectionModel`, kiểm thử collection có phần tử và collection rỗng với fallback type.
8. Nếu có nhiều processor hoặc Spring Data REST, kiểm thử đúng pipeline tích hợp đang sử dụng.

## Kết luận

`RepresentationModelProcessor` giúp điều chỉnh representation sau khi assembler đã tạo model, đặc biệt phù hợp với các link cần bổ sung xuyên nhiều controller hoặc theo ngữ cảnh dùng chung. Kiểm thử đầy đủ cần kết hợp unit test cho `process(...)` và integration test để xác nhận Spring tự động áp dụng processor, generic type được khớp và response HAL chứa đúng link. Với `CollectionModel` rỗng, hãy cung cấp fallback type để cơ chế dispatch có đủ thông tin nhận diện processor.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Representation Model Processors](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.representation-model-processors): cách đăng ký và áp dụng processor, xử lý collection rỗng.
- [RepresentationModelProcessor API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html): hợp đồng `process(T model)`.
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html): `empty(...)` và `withFallbackType(...)`.
- [Spring Data REST – Customizing JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html): tích hợp processor với repository exporter.
