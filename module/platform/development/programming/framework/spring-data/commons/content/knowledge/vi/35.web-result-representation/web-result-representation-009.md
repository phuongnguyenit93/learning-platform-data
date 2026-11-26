# DTO đầu ra để kiểm soát trường dữ liệu và hợp đồng API

## Mục tiêu và phạm vi

Một đối tượng mà repository trả về thường chứa nhiều thông tin hơn một client cần. Nếu đưa nguyên đối tượng đó qua HTTP, schema API có thể phụ thuộc vào entity, quan hệ dữ liệu và cấu hình serialization bên trong.

DTO đầu ra là kiểu dữ liệu được thiết kế cho response. Nó xác định rõ các trường được công khai, cách biểu diễn giá trị và ý nghĩa mà client có thể dựa vào.

Bài học thuộc chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**. Nội dung liên hệ DTO với repository, projection, phân trang và metadata của Spring Data Commons, đồng thời giữ rõ phần truy vấn và mapping phụ thuộc từng module store.

Sau bài học, bạn có thể:

1. Phân biệt entity/domain model, repository projection và response DTO.
2. Chọn trường đầu ra theo nhu cầu của người gọi.
3. Viết mapper tường minh cho ID, tiền tệ, thời gian và trạng thái.
4. Ánh xạ một trang dữ liệu mà vẫn giữ metadata.
5. Kiểm thử schema thực tế ở biên HTTP và quản lý thay đổi hợp đồng.

Các ví dụ sử dụng Java 17 trở lên. Phần controller giả định Spring MVC và JSON message converter phù hợp đã được cấu hình. Phần danh sách dùng Spring Data `PagedModel`, có từ Spring Data 3.3; nếu dự án chưa có kiểu này, có thể dùng envelope DTO do ứng dụng định nghĩa.

## 1. Ba kiểu dữ liệu có ba vai trò khác nhau

| Kiểu | Phục vụ ai? | Ví dụ trách nhiệm |
|---|---|---|
| Domain model hoặc entity | Nghiệp vụ và tầng lưu trữ | Danh tính, trạng thái nội bộ, liên kết aggregate |
| Repository projection | Nhu cầu đọc từ repository | Chọn các thuộc tính cần lấy hoặc cần biểu diễn |
| Response DTO | Client của API | Tên trường, kiểu JSON và giá trị công khai |

Một class có thể được dùng cho nhiều vai trò trong hệ thống nhỏ, nhưng cần hiểu sự đánh đổi. Tái sử dụng một kiểu không làm các trách nhiệm tự trở thành giống nhau.

Chẳng hạn, entity đơn hàng có thể có `tenantId`, email khách hàng, chi phí nhập hàng và ghi chú kiểm tra nội bộ. Endpoint tra cứu trạng thái đơn hàng có thể chỉ cần ID, tổng tiền, trạng thái công khai và thời điểm tạo.

Projection giúp lấy một phần dữ liệu. Response DTO quyết định dữ liệu nào trở thành hợp đồng HTTP. Việc repository dùng projection không tự giải quyết phân quyền hoặc thiết kế schema.

Luồng thường gặp:

~~~mermaid
flowchart LR
    A["Danh tính người gọi"] --> B["Phạm vi truy vấn được phép"]
    B --> C["Repository hoặc read port"]
    C --> D["Domain hoặc projection"]
    D --> E["Mapper đầu ra"]
    E --> F["Response DTO"]
    F --> G["JSON cho client"]
~~~

Mỗi bước có trách nhiệm riêng. Mapper chọn trường đầu ra không thay thế điều kiện giới hạn dữ liệu ở bước truy vấn.

## 2. Vì sao trả trực tiếp entity tạo phụ thuộc ngoài ý muốn?

Giả sử một entity có getter mới phục vụ nghiệp vụ nội bộ. Tùy cấu hình serializer, getter đó có thể làm xuất hiện một thuộc tính JSON mới. Client nhìn thấy một thay đổi dù controller không được sửa.

Những vấn đề thường gặp gồm:

- Entity thêm trường thì response cũng thay đổi theo.
- Tên property nội bộ trở thành tên trường public.
- Quan hệ dữ liệu làm JSON sâu hơn dự kiến.
- Getter hoặc quan hệ lazy trong một số store có thể tạo thêm thao tác đọc.
- Trạng thái hoặc metadata kỹ thuật bị đưa ra dù client không cần.
- Một kiểu được dùng đồng thời cho input và output dù hai hợp đồng khác nhau.

Không phải mọi store đều có proxy hoặc lazy loading giống JPA. Điểm chung là một graph domain không mặc nhiên là representation phù hợp cho HTTP.

Một DTO nhỏ giúp nhìn thấy ngay phạm vi công khai:

~~~java
public record OrderResponse(
    String id,
    Money total,
    String status,
    String createdAt
) {
    public record Money(
        String amount,
        String currency
    ) {
    }
}
~~~

Bốn component trên là bốn thuộc tính mà ví dụ muốn đưa ra. Tuy vậy, DTO vẫn đi qua JSON converter; cấu hình naming, module và annotation cần được kiểm tra bằng response thực tế.

DTO cũng có thể bị thiết kế sai. Nếu nó chứa `Object entity`, `Map<String, Object> allFields` hoặc một object domain lồng bên trong, phạm vi đầu ra lại trở nên khó kiểm soát.

## 3. Chọn hợp đồng trước khi viết mapper

Trong ví dụ, endpoint đọc một đơn hàng trả:

~~~json
{
  "id": "5dd5cbfa-626b-42fd-bf8d-510c606220d0",
  "total": {
    "amount": "123.45",
    "currency": "EUR"
  },
  "status": "processing",
  "createdAt": "2026-01-02T03:04:05Z"
}
~~~

Đây là schema do ứng dụng lựa chọn, không phải JSON mặc định của Spring Data.

| Trường | Hợp đồng đã chọn |
|---|---|
| `id` | Chuỗi biểu diễn ID công khai |
| `total.amount` | Chuỗi số thập phân, không dùng ký pháp số mũ |
| `total.currency` | Mã tiền tệ |
| `status` | Mã trạng thái công khai do API định nghĩa |
| `createdAt` | Chuỗi thời điểm theo ISO-8601, biểu diễn UTC trong ví dụ |

Các trường nội bộ không nằm trong schema:

| Dữ liệu nguồn | Có xuất hiện ở response này? | Lý do thiết kế |
|---|---|---|
| `tenantId` | Không | Dùng xác định phạm vi dữ liệu ở backend |
| `customerEmail` | Không | Endpoint này không cần thông tin liên hệ |
| `supplierCost` | Không | Thuộc thông tin vận hành nội bộ |
| `fraudReviewNote` | Không | Không thuộc hợp đồng tra cứu đơn hàng |

Không cần thêm một trường rồi đặt null chỉ để cho thấy nó đã bị ẩn. Với schema này, những trường trên không tồn tại trong response.

### Đầu ra cần tách khỏi đầu vào

Một request tạo đơn hàng không nên cho client tự đặt ID, tổng tiền đã tính toán hoặc trạng thái xử lý nội bộ chỉ vì response có các trường đó.

Vì vậy, một hệ thống có thể có `CreateOrderRequest`, `UpdateDeliveryRequest` và `OrderResponse` riêng. Chúng có thể dùng chung một vài kiểu giá trị, nhưng không cần dùng chung toàn bộ shape.

Tên DTO theo mục đích giúp người đọc hiểu hợp đồng hơn một class `OrderDto` chứa mọi trường của mọi endpoint.

## 4. Nguồn dữ liệu nội bộ dùng cho ví dụ

Để không phụ thuộc annotation của một module store cụ thể, ta dùng snapshot nội bộ làm đầu vào cho mapper:

~~~java
public enum OrderState {
    DRAFT,
    AWAITING_PAYMENT,
    PAYMENT_CAPTURED,
    PACKING,
    DISPATCHED,
    CANCELLED
}
~~~

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import java.util.UUID;

public record OrderSnapshot(
    UUID id,
    String tenantId,
    String customerEmail,
    BigDecimal totalAmount,
    Currency currency,
    OrderState state,
    Instant createdAt,
    BigDecimal supplierCost,
    String fraudReviewNote
) {
}
~~~

`OrderSnapshot` không được khẳng định là một entity có thể lưu trực tiếp trong mọi store. Nó là model nội bộ của ví dụ, do tầng đọc tạo ra từ entity hoặc projection phù hợp.

Tầng đọc phải bảo đảm các giá trị cần thiết như ID, số tiền, tiền tệ, trạng thái và thời điểm đã có giá trị hợp lệ. Những bất biến nghiệp vụ của số tiền được xử lý trước khi chuyển sang response.

Việc có thông tin nội bộ trong model này không yêu cầu đưa chúng ra HTTP. Mapper chỉ gọi những accessor cần thiết cho hợp đồng đã chọn.

### DTO không làm thay đổi giá trị nguồn

Khi response dùng một mã trạng thái hoặc định dạng khác, không sửa entity chỉ để vừa JSON. Tạo giá trị đầu ra mới.

Cũng không gán null vào entity trước khi serialize để “xóa trường”. Cách đó trộn thay đổi trạng thái nghiệp vụ với việc trình bày, có thể gây tác dụng phụ khi đối tượng vẫn được tầng lưu trữ quản lý.

## 5. Mapper tường minh cho hợp đồng công khai

Mapper dưới đây chỉ tạo những giá trị mà `OrderResponse` cần:

~~~java
import java.util.Objects;

public final class OrderResponseMapper {

    private OrderResponseMapper() {
    }

    public static OrderResponse toResponse(OrderSnapshot source) {
        Objects.requireNonNull(source, "order source is required");

        OrderResponse.Money total = new OrderResponse.Money(
            source.totalAmount().toPlainString(),
            source.currency().getCurrencyCode()
        );

        return new OrderResponse(
            source.id().toString(),
            total,
            publicStatus(source.state()),
            source.createdAt().toString()
        );
    }

    private static String publicStatus(OrderState state) {
        return switch (state) {
            case DRAFT -> "draft";
            case AWAITING_PAYMENT -> "pending_payment";
            case PAYMENT_CAPTURED, PACKING -> "processing";
            case DISPATCHED -> "shipped";
            case CANCELLED -> "cancelled";
        };
    }
}
~~~

Các class và record trong bài được hiểu là những đơn vị mã nguồn riêng trong cùng package ứng dụng khi thực hành.

Mapper không dùng phép sao chép tất cả property theo tên. Vì vậy, một trường mới được thêm vào `OrderSnapshot` không tự trở thành trường mới trong response.

Đây là lựa chọn rõ ràng cho ví dụ có ít trường và một số quy tắc chuyển đổi. Với hệ thống lớn, có thể dùng công cụ sinh mapper, nhưng cấu hình mapper vẫn phải thể hiện đúng tập trường và quy tắc của hợp đồng.

### 5.1. ID là một kiểu giá trị public

Ví dụ chuyển UUID thành chuỗi. Điều đó tách kiểu JSON khỏi kiểu định danh trong Java.

Với ID dạng số lớn, cần cân nhắc khả năng biểu diễn chính xác của client. Một số client JavaScript không giữ chính xác mọi giá trị trong miền Java `long` khi dùng `Number`. Chọn ID dạng chuỗi từ đầu có thể phù hợp nếu hợp đồng yêu cầu như vậy.

Không tự đổi một trường ID đã công bố từ số sang chuỗi mà không đánh giá tương thích.

### 5.2. Số tiền cần cả giá trị và đơn vị

Ví dụ dùng `BigDecimal.toPlainString()` để tránh tự chuyển sang số thực nhị phân hoặc ký pháp số mũ ở bước mapper.

`"123.45"` là chuỗi theo hợp đồng này. Một API khác có thể dùng JSON number hoặc số đơn vị nhỏ nhất, nhưng phải mô tả chính xác cách diễn giải.

Mapper trên không tự chuẩn hóa mọi tiền tệ về hai chữ số thập phân. Quy tắc scale, làm tròn và đơn vị tiền phải đến từ nghiệp vụ; không giả định mọi tiền tệ có cùng số chữ số phần lẻ.

### 5.3. Thời điểm cần quy ước rõ

`Instant.toString()` tạo biểu diễn thời điểm UTC theo định dạng ISO-8601. Ví dụ chọn chuỗi này làm giá trị đầu ra thay vì để cấu hình thời gian mặc định của serializer quyết định.

Nếu API cần độ chính xác cố định, timezone hoặc định dạng khác, phải định nghĩa thêm quy tắc. Một chuỗi thời gian đẹp mắt nhưng không chỉ rõ ý nghĩa vẫn có thể gây nhầm lẫn.

Các quy tắc về kiểu JSON và giới hạn tương tác số có thể đối chiếu trong [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html).

### 5.4. Trạng thái công khai không cần trùng enum nội bộ

Hai trạng thái `PAYMENT_CAPTURED` và `PACKING` cùng ánh xạ thành `processing`. Client chỉ cần biết đơn hàng đang được xử lý; chi tiết quy trình nội bộ có thể thay đổi.

Dùng trực tiếp `state.name()` sẽ gắn API với tên enum Java. Một lần đổi tên hoặc tách trạng thái nội bộ có thể thành thay đổi hợp đồng ngoài ý muốn.

Switch tường minh còn giúp lập trình viên phải xem xét ánh xạ khi thêm trạng thái mới. Tuy nhiên, thêm một mã trạng thái public vẫn có thể ảnh hưởng client, nhất là client sinh enum hoặc xử lý tập giá trị đóng.

## 6. Phân quyền dữ liệu phải xảy ra trước khi trình bày

DTO kiểm soát trường nào được đưa ra. Nó không tự kiểm tra người gọi được đọc bản ghi nào.

Ta định nghĩa cổng đọc có phạm vi tenant rõ ràng:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderReadPort {

    Optional<OrderSnapshot> findByIdAndTenantId(
        UUID id,
        String tenantId
    );

    Page<OrderSnapshot> findByTenantId(
        String tenantId,
        Pageable pageable
    );
}
~~~

Tenant của người gọi được cung cấp bởi một abstraction ngữ cảnh:

~~~java
public interface CurrentTenant {

    String requireTenantId();
}
~~~

Implementation của `CurrentTenant` phải lấy tenant từ ngữ cảnh người dùng đã được xác thực và kiểm tra phù hợp. Không coi một tham số tenant do client tùy ý gửi là bằng chứng được phép truy cập tenant đó.

Service thực hiện truy vấn rồi ánh xạ:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderQueryService {

    private final OrderReadPort orders;
    private final CurrentTenant currentTenant;

    public OrderQueryService(
        OrderReadPort orders,
        CurrentTenant currentTenant
    ) {
        this.orders = orders;
        this.currentTenant = currentTenant;
    }

    public OrderResponse get(UUID id) {
        String tenantId = currentTenant.requireTenantId();

        OrderSnapshot source = orders
            .findByIdAndTenantId(id, tenantId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Order not found"
            ));

        return OrderResponseMapper.toResponse(source);
    }

    public Page<OrderResponse> list(Pageable pageable) {
        String tenantId = currentTenant.requireTenantId();

        return orders.findByTenantId(tenantId, pageable)
            .map(OrderResponseMapper::toResponse);
    }
}
~~~

Ví dụ chọn 404 khi không tìm thấy đơn hàng trong phạm vi được phép. Đây là một chính sách minh họa; hệ thống cần thống nhất chính sách lỗi của mình.

Implementation của `OrderReadPort` phải thực thi phạm vi truy vấn như hợp đồng, đồng thời áp dụng các điều kiện nghiệp vụ/quyền khác nếu có. Interface không tự tạo cơ chế phân quyền chỉ nhờ tên phương thức.

Với danh sách, count và nội dung phải cùng thuộc phạm vi được phép. Không đọc mọi tenant, lọc nội dung ở mapper rồi giữ nguyên tổng toàn hệ thống.

## 7. Controller trả DTO và giữ phân trang

Controller không trả snapshot nội bộ:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderQueryService service;

    public OrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}",
        produces = "application/json"
    )
    public OrderResponse get(
        @PathVariable("id") UUID id
    ) {
        return service.get(id);
    }

    @GetMapping(produces = "application/json")
    public PagedModel<OrderResponse> list(
        @PageableDefault(size = 20, sort = "id")
        Pageable pageable
    ) {
        return new PagedModel<>(
            service.list(pageable)
        );
    }
}
~~~

Để chạy ứng dụng thật, cần cung cấp bean implementation cho `OrderReadPort` và `CurrentTenant`, cùng hạ tầng web/store tương ứng. Các port trong ví dụ giữ bài học tập trung vào ranh giới đầu ra.

`Page.map` chuyển từng phần tử sang DTO trong khi giữ thông tin phân trang. Nó không lọc bớt bản ghi và không tự chạy một truy vấn count mới. Xem API [Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html).

Envelope của danh sách và DTO của từng phần tử là hai quyết định riêng:

- `OrderResponse` kiểm soát trường của một đơn hàng.
- `PagedModel` kiểm soát representation phân trang bên ngoài.

`org.springframework.data.web.PagedModel` cung cấp representation ổn định cho trang, có từ Spring Data 3.3. Đây không phải lớp cùng tên của Spring HATEOAS. Tham khảo [Spring Data PagedModel](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedModel.html).

Nếu ứng dụng có envelope riêng, vẫn có thể dùng cùng `OrderResponse` làm kiểu phần tử. Không cần trả trực tiếp `PageImpl` chỉ vì nội dung đã được chuyển sang DTO.


## 8. Kết hợp response DTO với repository projection

Response DTO không có nghĩa phải đọc toàn bộ entity trước. Tầng repository có thể dùng projection để lấy dữ liệu phù hợp hơn, nếu module store hỗ trợ.

Ví dụ một interface projection cho nhu cầu đọc:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import java.util.UUID;

public interface OrderListProjection {

    UUID getId();

    BigDecimal getTotalAmount();

    Currency getCurrency();

    OrderState getState();

    Instant getCreatedAt();
}
~~~

Một chữ ký query minh họa:

~~~java
Page<OrderListProjection> findByTenantId(
    String tenantId,
    Pageable pageable
);
~~~

Chữ ký này được hiểu là nằm trong repository của domain đã được mapping. Không phải cứ khai báo interface là mọi store tự cung cấp cùng một chiến lược truy vấn.

Interface projection thường được Spring Data biểu diễn qua proxy. Closed projection có thể cho phép tối ưu việc lấy dữ liệu, còn khả năng cụ thể phụ thuộc module. Class-based projection là một lựa chọn khác với yêu cầu constructor và mapping tương ứng. Xem [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

Sau khi có projection, ứng dụng vẫn có thể ánh xạ sang `OrderResponse` để giữ tên trường và mã trạng thái public.

### Projection và response có thể thay đổi độc lập

Giả sử thay đổi store làm tầng đọc cần một projection khác, hoặc cần gộp dữ liệu từ hai nguồn. Nếu response DTO giữ nguyên hợp đồng, client không cần biết thay đổi đó.

Ngược lại, một phiên bản API mới có thể thêm `trackingUrl` trong khi projection hiện tại chưa có dữ liệu cần thiết. Đây là yêu cầu đọc mới cần thiết kế, không phải chỉ thêm một getter rồi hy vọng serializer tìm được dữ liệu.

Nếu dùng cùng một class làm repository projection và response DTO, hãy chấp nhận có chủ đích sự liên kết giữa constructor/query mapping và hợp đồng public. Với response có nhiều chuyển đổi như ví dụ tiền tệ và trạng thái, mapper riêng thường làm ranh giới dễ nhìn hơn.

### Tên trường JSON không tự đổi tên property truy vấn

Nếu response dùng `createdAt` nhưng domain đổi thành `createdOn`, mapper có thể giữ nguyên trường public.

Tuy nhiên, query derivation và `Sort` vẫn làm việc theo mô hình thuộc tính mà tầng truy vấn hỗ trợ. Annotation đổi tên JSON không tự đổi cách repository hiểu một khóa sort.

Nếu client được sort theo khóa public, cần bảng ánh xạ và tập khóa cho phép. Đừng công khai mọi property nội bộ chỉ vì chúng xuất hiện trong model.

## 9. Annotation serialization và DTO có vai trò bổ sung

Jackson cung cấp các annotation như `@JsonProperty`, `@JsonIgnore` và `@JsonInclude`. Chúng điều khiển representation, nhưng không tự xác định nghiệp vụ hoặc quyền đọc bản ghi.

Ví dụ giữ một tên JSON khi tên component Java khác:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record TimestampResponse(
    @JsonProperty("createdAt")
    String creationTime
) {
}
~~~

Trong cấu hình Jackson phù hợp, trường public vẫn mang tên `createdAt`.

Nếu dùng annotation trên DTO, có thể quản lý quy tắc JSON ngay tại kiểu dữ liệu public. Nếu dùng annotation trực tiếp trên domain, các quyết định serialization có thể ảnh hưởng nhiều nơi cùng dùng domain đó.

`@JsonIgnore` có thể hữu ích cho một thuộc tính cụ thể, nhưng một danh sách trường bị bỏ qua không thay thế việc xem xét toàn bộ những trường được công khai. Khi thêm field hoặc getter mới, cần xác định nó có trở thành JSON hay không.

Mô tả các annotation nằm trong tài liệu chính thức [Jackson Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations).

### Null và trường vắng mặt cần ý nghĩa rõ

Hai response sau không có cùng cấu trúc:

~~~json
{
  "deliveryEta": null
}
~~~

~~~json
{}
~~~

Hệ thống phải quyết định:

- Null có nghĩa là đã xét trường nhưng chưa có giá trị?
- Trường không hiện diện có nghĩa là không thuộc representation này?
- Một giá trị rỗng có nghĩa nghiệp vụ riêng hay chỉ là mặc định kỹ thuật?

Một DTO cho phép null không tự quy định nó sẽ bị bỏ qua hay vẫn được serialize. Chính sách `@JsonInclude` hoặc cấu hình converter có thể tác động đến điều đó.

Không dùng chuỗi rỗng, 0 hoặc một thời điểm giả để lấp giá trị chưa biết nếu chúng có thể bị client hiểu thành dữ liệu thật.

Trong `OrderResponse` chính của bài, bốn trường đều được kỳ vọng có giá trị. Nếu nguồn dữ liệu thiếu một giá trị bắt buộc, cần xử lý theo hợp đồng nghiệp vụ/lỗi thay vì âm thầm làm schema thay đổi.

## 10. Một DTO cho mỗi nhu cầu có ý nghĩa

Không nhất thiết phải có một class response riêng cho mọi endpoint. Có thể tái sử dụng một DTO khi ý nghĩa và phạm vi công khai thực sự giống nhau.

Ngược lại, một DTO khổng lồ dùng cho mọi nhóm người dùng thường tạo nhiều điều kiện:

~~~text
Nếu là danh sách: bỏ bớt trường.
Nếu là chi tiết: thêm quan hệ.
Nếu là vận hành: thêm chi phí.
Nếu là khách hàng: xóa ghi chú nội bộ.
~~~

Một lựa chọn dễ kiểm soát hơn là các representation riêng:

| Representation | Nhu cầu ví dụ |
|---|---|
| `OrderListResponse` | Hiển thị danh sách ngắn |
| `OrderDetailResponse` | Thông tin chi tiết được phép đọc |
| `OrderOperationsResponse` | Dữ liệu cho nghiệp vụ vận hành đã được cấp quyền |
| `OrderExportRow` | Các cột theo hợp đồng xuất dữ liệu |

Các kiểu có thể dùng chung một kiểu giá trị nhỏ như `MoneyResponse` nếu ý nghĩa giống nhau. Không cần lặp lại mọi thứ, cũng không cần buộc mọi response vào một mô hình kế thừa chung.

Điều kiện chọn DTO cho nghiệp vụ vận hành phải dựa trên ngữ cảnh đã được kiểm tra. Một query parameter như `view=operations` không tự cấp quyền xem thêm trường.

### Fields hoặc expand không phải quyền truy cập

Một số API cho client chọn `fields` hoặc mở rộng quan hệ bằng `expand`. Nếu có chức năng này, server cần ánh xạ các lựa chọn public vào tập trường được phép cho người gọi.

Không dùng trực tiếp tên field từ request để phản chiếu mọi property trên entity. Cũng không tự chọn class projection Java từ dữ liệu không được kiểm soát.

Việc không công khai một trường ở schema không làm bản thân giá trị đó được bảo vệ ở mọi kênh. Log, cache và những endpoint khác vẫn cần dùng đúng ngữ cảnh của chúng; phạm vi của DTO ở bài này là response đang thiết kế.

## 11. Graph lồng nhau và chi phí mapping

DTO có thể chứa các DTO khác:

~~~java
import java.util.List;

public record OrderDetailResponse(
    String id,
    List<LineResponse> lines
) {
    public record LineResponse(
        String productId,
        String productName,
        int quantity
    ) {
    }
}
~~~

Trong ví dụ này, quan hệ đầu ra kết thúc ở dữ liệu của dòng hàng. Nó không quay ngược về toàn bộ đơn hàng và không đưa nguyên product entity vào trong.

Những điểm cần quyết định khi dùng nested DTO:

- Một collection có luôn hiện diện dưới dạng mảng không?
- Thứ tự các phần tử có ý nghĩa gì?
- Số phần tử tối đa có thể lớn đến mức nào?
- Quan hệ đó đã được đọc hay mapper sẽ kích hoạt thêm thao tác lấy dữ liệu?
- Một endpoint riêng có phù hợp hơn cho collection lớn không?

Không gọi repository cho từng phần tử ngay trong mapper mà không tính đến số lượng truy vấn. Với một trang gồm nhiều đơn hàng, việc tra cứu từng khách hàng hoặc sản phẩm có thể tạo mẫu N+1.

Giải pháp có thể là projection, truy vấn theo lô, fetch phù hợp với module hoặc một mô hình đọc chuyên biệt. Không có một annotation fetch chung của Commons giải quyết giống nhau cho mọi store.

DTO giúp giới hạn graph JSON. Nó không tự làm query nhẹ hơn nếu backend đã đọc toàn bộ dữ liệu không cần thiết trước đó.

### Mapper nên dễ dự đoán

Trong ví dụ chính, mapper chỉ chuyển đổi dữ liệu đã có, không mở transaction hoặc gọi hệ thống ngoài.

Nếu response cần dữ liệu bổ sung từ dịch vụ khác, service nên điều phối việc lấy dữ liệu theo chính sách rõ ràng, rồi đưa đầu vào cần thiết cho bước mapping. Điều đó giúp nhìn thấy chi phí, lỗi và vòng đời công việc.

Metadata auditing như người tạo hoặc thời điểm sửa cũng cần được xem xét theo hợp đồng. Việc một field được hạ tầng auditing quản lý không có nghĩa nó tự động là trường cần công khai.

## 12. Công bố schema và quản lý thay đổi

Một DTO Java chỉ là một phần của hợp đồng. Client cần schema, mô tả ý nghĩa và ví dụ JSON.

Đoạn dưới là phần schema OpenAPI minh họa, không phải một tài liệu OpenAPI đầy đủ:

~~~yaml
components:
  schemas:
    MoneyResponse:
      type: object
      required:
        - amount
        - currency
      properties:
        amount:
          type: string
          description: Giá trị thập phân, không dùng ký pháp số mũ.
          example: "123.45"
        currency:
          type: string
          description: Mã tiền tệ.
          example: EUR

    OrderResponse:
      type: object
      required:
        - id
        - total
        - status
        - createdAt
      properties:
        id:
          type: string
          format: uuid
        total:
          $ref: '#/components/schemas/MoneyResponse'
        status:
          type: string
          enum:
            - draft
            - pending_payment
            - processing
            - shipped
            - cancelled
        createdAt:
          type: string
          format: date-time
          description: Thời điểm UTC theo ISO-8601.
~~~

Các ràng buộc trong schema phải phù hợp dữ liệu thật. Nếu một trường có thể null, cần mô tả nullability theo phiên bản schema đang dùng thay vì chỉ đánh dấu required rồi để client đoán.

`required` nói về sự hiện diện. Nó không tự giải thích toàn bộ ý nghĩa nghiệp vụ của giá trị. Tương tự, một trường có `format` không có nghĩa mọi công cụ sẽ xác minh toàn bộ quy tắc ứng dụng cần.

Tham khảo [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html) cho cách mô tả schema và response.

### Phân biệt thay đổi nội bộ với thay đổi public

| Thay đổi | Có nhất thiết đổi API? |
|---|---|
| Đổi tên field domain, mapper vẫn giữ output | Không |
| Đổi store nhưng cùng dữ liệu và representation | Không |
| Đổi mã `processing` thành `packing` | Có thay đổi ý nghĩa/giá trị public |
| Đổi amount từ chuỗi thành JSON number | Có thay đổi kiểu |
| Xóa trường đang được công bố | Có thay đổi schema |
| Thêm một giá trị enum public | Cần đánh giá client xử lý tập giá trị đóng |
| Thêm trường tùy chọn | Cần xét khả năng bỏ qua field mới của client |
| Đổi chính sách null thành vắng mặt | Có thể ảnh hưởng cách client đọc dữ liệu |

Không mặc định mọi SDK đều chấp nhận trường mới hoặc enum mới. Chính sách tương thích cần dựa vào các consumer đang được hỗ trợ.

Nếu representation cũ đã công khai entity, chuyển sang DTO có thể vẫn làm hỏng client đang đọc trường cũ. Cần xác định schema mục tiêu và kế hoạch chuyển tiếp thay vì coi việc đổi kiểu Java ở controller là luôn tương thích.

## 13. Kiểm thử các trường thực sự đi qua HTTP

Chỉ kiểm tra `mapper.toResponse(source)` chưa xác minh JSON converter có trả đúng tên và kiểu trường. Kiểm thử biên HTTP giúp kiểm tra representation mà client nhận.

Ví dụ dưới dùng Mockito và MockMvc với các class ở phần trước:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class OrderResponseContractTest {

    private static final UUID ORDER_ID = UUID.fromString(
        "5dd5cbfa-626b-42fd-bf8d-510c606220d0"
    );

    private final OrderReadPort orders = mock(OrderReadPort.class);

    private MockMvc web() {
        CurrentTenant tenant = () -> "tenant-a";

        OrderQueryService service =
            new OrderQueryService(orders, tenant);

        return standaloneSetup(new OrderController(service))
            .build();
    }

    private OrderSnapshot source() {
        return new OrderSnapshot(
            ORDER_ID,
            "tenant-a",
            "customer@example.invalid",
            new BigDecimal("123.45"),
            Currency.getInstance("EUR"),
            OrderState.PACKING,
            Instant.parse("2026-01-02T03:04:05Z"),
            new BigDecimal("70.00"),
            "MANUAL_REVIEW_ONLY"
        );
    }

    @Test
    void exposesOnlyThePublicContract() throws Exception {
        when(orders.findByIdAndTenantId(ORDER_ID, "tenant-a"))
            .thenReturn(Optional.of(source()));

        web().perform(get("/orders/{id}", ORDER_ID)
                .param("tenantId", "tenant-b"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", aMapWithSize(4)))
            .andExpect(jsonPath("$.id").value(ORDER_ID.toString()))
            .andExpect(jsonPath("$.total", aMapWithSize(2)))
            .andExpect(jsonPath("$.total.amount").value("123.45"))
            .andExpect(jsonPath("$.total.currency").value("EUR"))
            .andExpect(jsonPath("$.status").value("processing"))
            .andExpect(jsonPath("$.createdAt")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.tenantId").doesNotExist())
            .andExpect(jsonPath("$.customerEmail").doesNotExist())
            .andExpect(jsonPath("$.supplierCost").doesNotExist())
            .andExpect(jsonPath("$.fraudReviewNote").doesNotExist());

        verify(orders).findByIdAndTenantId(
            ORDER_ID,
            "tenant-a"
        );
    }

    @Test
    void returnsNotFoundForTheVisibleScope() throws Exception {
        when(orders.findByIdAndTenantId(ORDER_ID, "tenant-a"))
            .thenReturn(Optional.empty());

        web().perform(get("/orders/{id}", ORDER_ID))
            .andExpect(status().isNotFound());

        verify(orders).findByIdAndTenantId(
            ORDER_ID,
            "tenant-a"
        );
    }
}
~~~

Ví dụ cần JUnit, Mockito, spring-test, Hamcrest/JSONPath tương ứng và JSON converter hỗ trợ record. Đây là mẫu kiểm thử để người học áp dụng, không phải báo cáo rằng ứng dụng thực tế đã được chạy kiểm thử.

Test đầu dùng tenant từ context giả đã cung cấp cho service, dù request gửi thêm một query parameter khác. Nó xác minh cách sử dụng context trong ví dụ, không chứng minh cơ chế xác thực người dùng đã được triển khai đúng.

Kiểm tra số field ở root và object lồng giúp phát hiện những thuộc tính mới xuất hiện ngoài ý định. Khi thêm trường public có chủ đích, cập nhật schema và kiểm thử cùng thay đổi đó.

### Những kiểm tra nên có thêm

| Trường hợp | Điều cần xác nhận |
|---|---|
| Hai trạng thái nội bộ cùng mã public | Mapper giữ đúng chính sách |
| ID hoặc số tiền có miền giá trị đặc biệt | Kiểu JSON và biểu diễn không bị đổi ngoài ý muốn |
| Thời điểm có phần giây lẻ | Đúng chính sách định dạng/độ chính xác |
| Nguồn thiếu giá trị bắt buộc | Lỗi được xử lý có chủ đích |
| DTO có trường tùy chọn | Null/vắng mặt đúng schema |
| Danh sách có phân trang | Nội dung DTO và metadata cùng đúng |
| Một audience khác | Chọn đúng representation theo quyền đã kiểm tra |
| Nâng cấp converter | Không vô tình đổi tên hoặc kiểu trường |
| Thêm field nội bộ vào nguồn | Response public giữ nguyên tập trường |
| Truy vấn trên store thật | Projection, phạm vi dữ liệu và chi phí đọc phù hợp |

Standalone MockMvc chưa xác minh toàn bộ cấu hình JSON hoặc security của ứng dụng thật. Khi những cấu hình đó có ảnh hưởng đến hợp đồng, cần có test với application context phù hợp.

## 14. Những lỗi thiết kế dễ gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Trả entity trực tiếp cho mọi endpoint | Schema phụ thuộc model lưu trữ | Định nghĩa representation theo nhu cầu |
| DTO chứa lại toàn bộ entity | Graph public vẫn khó kiểm soát | Dùng kiểu phần tử/nested DTO tường minh |
| Sao chép mọi property theo tên | Field nội bộ mới có thể đi theo mapper | Chọn rõ tập trường public |
| Chỉ ẩn field ở frontend | Giá trị vẫn nằm trong response HTTP | Kiểm soát trước serialization |
| Dùng `enum.name()` làm mã public mặc định | API gắn với tên enum nội bộ | Ánh xạ mã public có chủ đích |
| Gọi repository trong mỗi vòng mapping | Có thể phát sinh nhiều thao tác đọc | Điều phối/batch/projection ở tầng đọc |
| Lọc bớt bản ghi sau khi phân trang | Content và tổng không còn cùng nghĩa | Áp dụng điều kiện đúng trong query |
| Dùng cùng DTO cho tạo, sửa và đọc | Trộn các quyền và dữ liệu khác nhau | Tách hợp đồng theo mục đích |
| Dùng `Map<String, Object>` cho mọi response | Khó kiểm soát kiểu và schema | Dùng kiểu rõ ràng khi shape đã biết |
| Đổi annotation mà không kiểm tra HTTP | Schema runtime có thể lệch tài liệu | Kiểm thử JSON thực tế |

Mapper thủ công không phải lựa chọn bắt buộc trong mọi dự án. Tiêu chí là tập trường và quy tắc chuyển đổi phải review được, không phải số lượng dòng code.

Tương tự, DTO không thay thế thiết kế domain. Một domain model tốt vẫn có trách nhiệm bảo vệ bất biến nghiệp vụ; response DTO tập trung vào cách cung cấp thông tin cho bên ngoài.

## 15. Bài thực hành

Chọn một endpoint đọc dữ liệu có repository hoặc read port:

1. Liệt kê tất cả dữ liệu nguồn và mục đích của từng field.
2. Xác định tập trường mà client thực sự cần, gồm cả nested object.
3. Đặt tên, kiểu JSON, quy tắc null và ý nghĩa của mỗi field.
4. Tạo response DTO và mapper không làm thay đổi nguồn.
5. Ánh xạ một enum nội bộ sang mã public có chủ đích.
6. Chọn quy ước cho ID, tiền tệ và thời gian.
7. Đặt phạm vi dữ liệu ở tầng truy vấn theo ngữ cảnh người gọi.
8. Nếu có phân trang, dùng `Page.map` và envelope phù hợp.
9. Cân nhắc projection theo khả năng của module store để tránh đọc dư.
10. Viết kiểm thử HTTP xác nhận cả field cần có và field không được công khai.
11. Thêm thử một field nội bộ vào nguồn và xem hợp đồng public có giữ nguyên không.
12. Mô tả cách chuyển tiếp nếu API cũ đã công khai một schema khác.

Kết quả mong muốn là: **client phụ thuộc một representation được thiết kế rõ; repository và projection phục vụ việc đọc; mapper chuyển dữ liệu đã được phép đọc thành DTO; thay đổi nội bộ không tự biến thành thay đổi hợp đồng API.**
