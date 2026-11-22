# Ánh xạ kết quả nghiệp vụ thành dữ liệu trình bày

Trong kiến trúc Model–View–Controller (MVC), tầng nghiệp vụ xử lý use case và trả về kết quả có ý nghĩa đối với ứng dụng. Controller nhận kết quả đó rồi chuẩn bị dữ liệu để View render hoặc để API trả về cho client. Công việc chuyển đổi này được gọi là ánh xạ dữ liệu trình bày (presentation mapping).

Kết quả nghiệp vụ và dữ liệu trình bày phục vụ hai mục đích khác nhau. Model có thể biểu diễn đơn hàng bằng các đối tượng miền, quy tắc trạng thái, tiền tệ và quan hệ với khách hàng. View chỉ cần tên khách hàng, mã đơn, danh sách dòng hàng, tổng tiền đã định dạng hoặc một nhãn trạng thái phù hợp với màn hình. API có thể cần một cấu trúc JSON ổn định, trong khi trang HTML cần một ViewModel thuận tiện cho template.

Nếu đưa trực tiếp entity hoặc đối tượng nội bộ của miền nghiệp vụ vào View, giao diện sẽ phụ thuộc vào cấu trúc lưu trữ và có nguy cơ làm lộ trường không được phép. Nếu để View tự tính lại quy tắc nghiệp vụ, nhiều màn hình có thể đưa ra kết quả khác nhau. Ánh xạ rõ ràng giúp giữ ranh giới: nghiệp vụ quyết định điều gì đã xảy ra; tầng trình bày quyết định cách diễn đạt kết quả đó.

## 1. Vì sao cần ánh xạ kết quả?

Giả sử use case xem chi tiết đơn hàng trả về một Order cùng các dòng hàng và thông tin thanh toán. Một trang chi tiết có thể cần:

- Mã đơn hàng và thời điểm tạo.
- Tên người nhận và địa chỉ giao hàng.
- Tên sản phẩm, số lượng và đơn giá từng dòng.
- Tổng tiền, phí vận chuyển và số tiền phải thanh toán.
- Trạng thái đơn hàng và những hành động mà người dùng hiện tại có thể thực hiện.

Trong khi đó, danh sách đơn hàng chỉ cần mã đơn, ngày tạo, tổng tiền và trạng thái. Một API dành cho ứng dụng di động có thể cần thêm mã tiền tệ và các trường phục vụ điều hướng.

Một đối tượng nghiệp vụ không nên phải thay đổi cấu trúc chỉ để đáp ứng từng màn hình. Thay vào đó, mỗi giao diện nhận một projection hoặc DTO phù hợp với nhu cầu của nó.

~~~mermaid
flowchart TD
    U[HTTP Request] --> C[Controller]
    C --> A[Application Service / Use case]
    A --> D[Domain Model và Repository]
    D --> A
    A --> R[Kết quả use case]
    R --> M[Presentation Mapper]
    M --> V1[ViewModel cho trang HTML]
    M --> V2[Response DTO cho JSON API]
    V1 --> H[View Template]
    V2 --> J[HTTP JSON Response]
~~~

Luồng này tách biệt ba trách nhiệm:

1. Application service điều phối use case và trả kết quả có ý nghĩa nghiệp vụ.
2. Presentation mapper chọn và chuyển dữ liệu phù hợp với hợp đồng hiển thị.
3. View hoặc serializer trình bày dữ liệu thành HTML, JSON hay một định dạng phản hồi khác.

Với ứng dụng nhỏ, Controller có thể thực hiện mapping đơn giản ngay trong handler. Khi mapping nhiều trường, nhiều màn hình hoặc nhiều quy tắc biểu diễn, nên tách thành mapper hoặc assembler để dễ kiểm thử và tái sử dụng.

## 2. Phân biệt Domain Model, kết quả use case và ViewModel

Các kiểu dữ liệu sau thường có hình dạng gần giống nhau nhưng có ý nghĩa khác nhau:

| Kiểu dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Domain Model / Entity | Bảo vệ trạng thái và quy tắc nghiệp vụ | Order, OrderLine, Money |
| Application result | Mô tả kết quả của một use case | OrderDetailsResult, PlaceOrderResult |
| ViewModel | Cung cấp dữ liệu cho một màn hình hoặc template | OrderDetailViewModel |
| Response DTO | Công bố hợp đồng dữ liệu cho client API | OrderDetailResponse |
| Persistence projection | Chỉ tải những cột cần thiết từ kho dữ liệu | OrderListRow |

Domain Model có thể chứa phương thức hành vi như tính tổng, xác nhận thanh toán hoặc kiểm tra trạng thái có thể hủy. ViewModel thường là dữ liệu đã được chọn và tổ chức để template dễ hiển thị. Response DTO là hợp đồng công khai; thay đổi nó có thể ảnh hưởng client đã tích hợp.

Application result có thể được dùng làm đầu ra ổn định của use case, không nhất thiết là entity. Nó có thể chứa ID, giá trị nghiệp vụ, mã kết quả hoặc thông tin cần cho tầng trình bày. Tầng ứng dụng không nên phải biết template HTML nào đang sử dụng kết quả đó.

Không bắt buộc mọi ứng dụng phải có đủ năm loại đối tượng. Với một trang đơn giản, Controller có thể ánh xạ trực tiếp từ application result sang ViewModel. Điều quan trọng là không để persistence entity trở thành hợp đồng trình bày mặc định cho mọi màn hình và API.

## 3. Nguyên tắc thiết kế dữ liệu trình bày

### 3.1. Chỉ đưa ra trường mà giao diện cần

Một ViewModel nên chứa những trường cần cho màn hình đó. Nếu trang danh sách chỉ cần tên khách hàng, không cần đưa toàn bộ Customer entity cùng địa chỉ, số điện thoại, ghi chú nội bộ và dữ liệu tài khoản vào template.

### 3.2. Giữ quy tắc nghiệp vụ trong Model hoặc use case

Mapper có thể chuyển trạng thái ORDER_SHIPPED thành nhãn hiển thị “Đang giao hàng”. Mapper không nên tự quyết định đơn hàng có được hủy hay không bằng cách lặp lại quy tắc trạng thái. Quyết định nghiệp vụ cần đến từ use case hoặc policy có thẩm quyền.

### 3.3. Không để View tự truy vấn dữ liệu

Template nên nhận dữ liệu đã được Controller hoặc application layer chuẩn bị. Nếu View gọi repository hoặc lazy-load quan hệ entity, luồng truy cập dữ liệu trở nên khó dự đoán và dễ phát sinh N+1 query.

### 3.4. Định dạng đúng tầng

ViewModel có thể chứa giá trị có kiểu như BigDecimal, LocalDate hoặc Instant để template định dạng theo locale. Với API, response DTO nên giữ biểu diễn máy đọc ổn định, chẳng hạn số thập phân và mã tiền tệ hoặc chuỗi ngày ISO. Không dùng chuỗi đã định dạng cho người dùng làm dữ liệu để tính toán.

### 3.5. Không làm lộ cấu trúc nội bộ

Entity có thể chứa password hash, ghi chú nội bộ, cờ kiểm duyệt, thông tin chủ sở hữu hoặc trường kỹ thuật. Chỉ ánh xạ những dữ liệu được phép công bố. Không dựa vào việc template “không hiển thị” một trường để xem đó là biện pháp bảo vệ; nếu trường đã được serialize vào JSON thì client vẫn nhận được.

## 4. Ví dụ miền nghiệp vụ: đơn hàng

Các đoạn mã sau minh họa các kiểu riêng biệt; mỗi kiểu public được đặt trong file Java tương ứng và những import thông thường được lược bớt ở một số đoạn.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record Money(BigDecimal amount, String currency) {
}

public record OrderLine(
        String productName,
        int quantity,
        Money unitPrice
) {
    public OrderLine {
        if (quantity < 1) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
    }

    public Money lineTotal() {
        return new Money(
                unitPrice.amount().multiply(BigDecimal.valueOf(quantity)),
                unitPrice.currency()
        );
    }
}

public enum OrderStatus {
    PLACED,
    PAID,
    SHIPPED,
    CANCELLED
}

public record Order(
        long id,
        String customerName,
        Instant createdAt,
        List<OrderLine> lines,
        Money shippingFee,
        OrderStatus status
) {
    public Order {
        lines = List.copyOf(lines);
    }

    public Money total() {
        BigDecimal linesTotal = lines.stream()
                .map(line -> line.lineTotal().amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        boolean currencyMatches = lines.stream()
                .allMatch(line -> line.unitPrice().currency()
                        .equals(shippingFee.currency()));
        if (!currencyMatches) {
            throw new IllegalStateException(
                    "Không thể cộng các khoản tiền khác loại tiền tệ"
            );
        }

        return new Money(
                linesTotal.add(shippingFee.amount()),
                shippingFee.currency()
        );
    }
}
~~~

Đây là ví dụ minh họa cấu trúc dữ liệu. Trong ứng dụng thực tế, Money cần bảo vệ quy tắc về mã tiền tệ, độ chính xác và phép cộng giữa các loại tiền. Order có thể là domain aggregate có hành vi thay đổi trạng thái. Nếu dùng JPA, entity lưu trữ thường là class có định danh và vòng đời riêng; record ở đây chỉ giúp minh họa dữ liệu và phép tính.

Application service có thể trả về kết quả use case:

~~~java
public record OrderDetailsResult(
        long orderId,
        String customerName,
        Instant createdAt,
        List<OrderLineResult> lines,
        Money shippingFee,
        OrderStatus status,
        Money total,
        boolean cancellationAllowed
) {
}

public record OrderLineResult(
        String productName,
        int quantity,
        Money unitPrice,
        Money lineTotal
) {
}
~~~

Service chịu trách nhiệm tải dữ liệu và điều phối policy nghiệp vụ. Tổng tiền được tính bởi Model, nơi có thể bảo vệ quy tắc cộng tiền cùng loại tiền tệ; không để mỗi View tự cộng theo một công thức khác nhau.

~~~java
@Service
public class OrderQueryService {
    private final OrderRepository orders;
    private final OrderCancellationPolicy cancellationPolicy;

    public OrderQueryService(
            OrderRepository orders,
            OrderCancellationPolicy cancellationPolicy
    ) {
        this.orders = orders;
        this.cancellationPolicy = cancellationPolicy;
    }

    public OrderDetailsResult getDetails(long orderId, long actorId) {
        Order order = orders.findForCustomer(orderId, actorId)
                .orElseThrow(OrderNotFoundException::new);

        return new OrderDetailsResult(
                order.id(),
                order.customerName(),
                order.createdAt(),
                order.lines().stream()
                        .map(line -> new OrderLineResult(
                                line.productName(),
                                line.quantity(),
                                line.unitPrice(),
                                line.lineTotal()
                        ))
                        .toList(),
                order.shippingFee(),
                order.status(),
                order.total(),
                cancellationPolicy.canCancel(order, actorId)
        );
    }
}
~~~

Trong ví dụ, repository đã giới hạn đơn hàng theo actorId và policy quyết định người dùng có thể hủy hay không. Đây là điểm quan trọng: mapper không thể thay thế kiểm tra quyền truy cập hoặc quy tắc nghiệp vụ. Use case phải chỉ trả dữ liệu mà người gọi được phép xem.

## 5. Ánh xạ sang ViewModel cho HTML

Trang HTML thường cần dữ liệu có tên trường gần với ngôn ngữ trình bày. Ví dụ, template cần chuỗi trạng thái tiếng Việt, thông tin tổng tiền và một cờ cho biết có nên hiển thị nút hủy.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderDetailViewModel(
        String orderNumber,
        String customerName,
        Instant createdAt,
        List<OrderLineViewModel> lines,
        BigDecimal totalAmount,
        String currency,
        String statusLabel,
        boolean cancellationAvailable
) {
}

public record OrderLineViewModel(
        String productName,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal lineTotal
) {
}
~~~

Mapper chuyển application result thành ViewModel:

~~~java
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class OrderViewModelMapper {
    public OrderDetailViewModel toDetail(OrderDetailsResult result) {
        List<OrderLineViewModel> lines = result.lines().stream()
                .map(line -> new OrderLineViewModel(
                        line.productName(),
                        line.quantity(),
                        line.unitPrice().amount(),
                        line.lineTotal().amount()
                ))
                .toList();

        return new OrderDetailViewModel(
                "ORD-" + result.orderId(),
                result.customerName(),
                result.createdAt(),
                lines,
                result.total().amount(),
                result.total().currency(),
                statusLabel(result.status()),
                result.cancellationAllowed()
        );
    }

    private String statusLabel(OrderStatus status) {
        return switch (status) {
            case PLACED -> "Đã đặt";
            case PAID -> "Đã thanh toán";
            case SHIPPED -> "Đang giao hàng";
            case CANCELLED -> "Đã hủy";
        };
    }
}
~~~

Ví dụ trên minh họa mapping cho mục đích trình bày. Cờ cancellationAvailable chỉ nên được tính từ kết quả policy/use case có thẩm quyền nếu điều kiện hủy phụ thuộc nhiều hơn trạng thái đơn. Việc ẩn nút trên View không thay thế kiểm tra quyền và trạng thái khi người dùng gửi command hủy đơn.

Hàm statusLabel trong ví dụ trả nhãn tiếng Việt cố định để minh họa. Với ứng dụng đa ngôn ngữ, nên dùng MessageSource hoặc cơ chế localization của View để lấy nhãn theo Locale của request. Không lưu nhãn đã dịch vào domain model; trạng thái nghiệp vụ vẫn là mã ổn định như PLACED hoặc SHIPPED.

~~~java
import java.util.Locale;
import org.springframework.context.MessageSource;

public class LocalizedOrderLabelMapper {
    private final MessageSource messages;

    public LocalizedOrderLabelMapper(MessageSource messages) {
        this.messages = messages;
    }

    public String statusLabel(OrderStatus status, Locale locale) {
        String key = "order.status."
                + status.name().toLowerCase(Locale.ROOT);
        return messages.getMessage(key, null, locale);
    }
}
~~~

Các message key tương ứng được khai báo trong resource bundle theo từng ngôn ngữ, chẳng hạn order.status.placed. Locale đến từ ngữ cảnh request đã được Spring MVC xác định.

Controller chỉ điều phối việc đọc kết quả và chọn View:

~~~java
@Controller
public class OrderPageController {
    private final OrderQueryService orders;
    private final OrderViewModelMapper mapper;

    public OrderPageController(
            OrderQueryService orders,
            OrderViewModelMapper mapper
    ) {
        this.orders = orders;
        this.mapper = mapper;
    }

    @GetMapping("/orders/{id}")
    public String detail(
            @PathVariable long id,
            @AuthenticationPrincipal CurrentUser user,
            Model model
    ) {
        OrderDetailsResult result = orders.getDetails(id, user.id());
        model.addAttribute("order", mapper.toDetail(result));
        return "orders/detail";
    }
}
~~~

Template chỉ đọc ViewModel. Fragment nhận thuộc tính order từ model và dùng nó làm object context:

~~~html
<section th:object="${order}">
  <h1>Đơn hàng <span th:text="*{orderNumber}"></span></h1>
  <p>Khách hàng: <span th:text="*{customerName}"></span></p>
  <p>Trạng thái: <span th:text="*{statusLabel}"></span></p>
  <p>
    Tổng tiền:
    <span th:text="*{totalAmount}"></span>
    <span th:text="*{currency}"></span>
  </p>
<button th:if="*{cancellationAvailable}">Yêu cầu hủy</button>
</section>
~~~

Template không cần biết repository, entity relationship hay cách tính tổng tiền. Nó nhận dữ liệu đã được tổ chức cho đúng mục đích hiển thị.

## 6. Ánh xạ sang Response DTO cho JSON API

Response DTO là hợp đồng mà client API tiêu thụ. Nó cần ổn định, có kiểu rõ ràng và không phụ thuộc vào tên template hoặc cấu trúc persistence.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderDetailResponse(
        String orderNumber,
        String customerName,
        Instant createdAt,
        List<OrderLineResponse> lines,
        BigDecimal totalAmount,
        String currency,
        String status
) {
}

public record OrderLineResponse(
        String productName,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal lineTotal
) {
}
~~~

API mapper có thể khác với HTML mapper:

~~~java
import org.springframework.stereotype.Component;

@Component
public class OrderResponseMapper {
    public OrderDetailResponse toResponse(OrderDetailsResult result) {
        var lines = result.lines().stream()
                .map(line -> new OrderLineResponse(
                        line.productName(),
                        line.quantity(),
                        line.unitPrice().amount(),
                        line.lineTotal().amount()
                ))
                .toList();

        return new OrderDetailResponse(
                "ORD-" + result.orderId(),
                result.customerName(),
                result.createdAt(),
                lines,
                result.total().amount(),
                result.total().currency(),
                statusCode(result.status())
        );
    }

    private String statusCode(OrderStatus status) {
        return switch (status) {
            case PLACED -> "PLACED";
            case PAID -> "PAID";
            case SHIPPED -> "SHIPPED";
            case CANCELLED -> "CANCELLED";
        };
    }
}
~~~

Controller API trả response DTO:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderApiController {
    private final OrderQueryService orders;
    private final OrderResponseMapper mapper;

    public OrderApiController(
            OrderQueryService orders,
            OrderResponseMapper mapper
    ) {
        this.orders = orders;
        this.mapper = mapper;
    }

    @GetMapping("/{id}")
    public OrderDetailResponse detail(
            @PathVariable long id,
            @AuthenticationPrincipal CurrentUser user
    ) {
        return mapper.toResponse(orders.getDetails(id, user.id()));
    }
}
~~~

API giữ timestamp ở dạng Instant để serializer tạo biểu diễn JSON theo cấu hình đã công bố. Client có thể tự định dạng thời gian theo locale và múi giờ của thiết bị. Nếu hợp đồng API cần định dạng khác, hãy định nghĩa rõ serializer và versioning; không tự ý đổi chuỗi ngày theo locale của người dùng.

## 7. ViewModel và Response DTO có nên dùng chung?

Có thể dùng chung khi hai giao diện thực sự có cùng hợp đồng dữ liệu và cùng vòng đời thay đổi. Tuy nhiên, HTML ViewModel và API response thường phát triển theo nhu cầu khác nhau.

| Khía cạnh | ViewModel HTML | Response DTO API |
|---|---|---|
| Người tiêu thụ | Template phía máy chủ | Client bên ngoài hoặc ứng dụng khác |
| Tên trường | Thuận tiện cho màn hình | Ổn định theo hợp đồng API |
| Dữ liệu hiển thị | Có thể có nhãn, cờ giao diện, nhóm nội dung | Nên là dữ liệu có ý nghĩa và dễ xử lý bằng máy |
| Locale | Có thể gắn với locale của request | Thường dùng biểu diễn trung lập, ổn định |
| Tương thích ngược | Thường thay đổi cùng template | Cần quản lý version và tương thích client |
| Bảo mật | Chỉ dữ liệu cần render | Chỉ dữ liệu được phép công bố ra API |

Không nên đưa cờ giao diện như isExpanded, selectedTab hoặc showHelp vào response API nếu đó chỉ là trạng thái cục bộ của một màn hình. Ngược lại, API có thể cần ID, mã trạng thái và liên kết tài nguyên mà template không cần hiển thị.

Khi hai loại dữ liệu giống hệt nhau, có thể dùng chung một DTO trung lập. Khi chúng bắt đầu có mục đích hoặc vòng đời khác nhau, tách chúng để tránh một thay đổi ở giao diện HTML vô tình phá vỡ hợp đồng API.

## 8. Mapping thủ công, Mapper và thư viện ánh xạ

### 8.1. Mapping thủ công

Mapping thủ công dùng constructor hoặc factory để gán từng trường. Cách này rõ ràng, dễ đọc và phù hợp khi DTO có ít trường hoặc có quy tắc chuyển đổi đặc biệt.

Ưu điểm:

- Nhìn thấy chính xác trường nào được đưa ra ngoài.
- Dễ đặt logic trình bày nhỏ như nhãn hoặc định dạng mã.
- Dễ phát hiện trường nhạy cảm bị đưa nhầm vào response.

Hạn chế là mã lặp lại khi có nhiều DTO với cấu trúc tương tự. Không nên vì tránh lặp mà tạo một mapper tổng quát khó hiểu hoặc tự động ánh xạ mọi trường.

### 8.2. Mapper/Assembler chuyên biệt

Một mapper có tên theo mục đích như OrderDetailMapper hoặc CustomerSummaryAssembler giúp gom logic chuyển đổi và tạo điểm kiểm thử riêng. Mapper thường không truy cập repository và không thực hiện quy tắc nghiệp vụ. Nó nhận dữ liệu đã tải và trả về cấu trúc trình bày.

Nếu mapper cần gọi nhiều repository để tìm dữ liệu thiếu, hãy xem lại ranh giới use case hoặc query service. Việc tải dữ liệu nên được thực hiện ở application/query layer để tránh mapping gây truy vấn ẩn.

### 8.3. MapStruct

Với nhiều DTO có ánh xạ thuộc tính trực tiếp, MapStruct có thể sinh mã mapping lúc biên dịch. Những trường cần quy tắc đặc biệt vẫn nên được khai báo rõ:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CustomerMapper {
    @Mapping(target = "displayName", source = "fullName")
    @Mapping(target = "customerCode", source = "id")
    CustomerSummaryResponse toSummary(Customer customer);
}
~~~

MapStruct giúp giảm mã lặp và phát hiện một số lỗi mapping khi biên dịch. Tuy nhiên, thư viện không tự quyết định dữ liệu nào được phép công bố, không thay thế kiểm tra quyền và không nên tự động ánh xạ toàn bộ entity ra API. Cần khai báo ignore hoặc mapping tường minh cho các trường nhạy cảm và kiểm tra mã được sinh.

Các mã trạng thái trả ra API là một phần của hợp đồng công khai. Khi thay đổi tên hoặc ý nghĩa mã, cần xem xét tương thích ngược và versioning; không để việc đổi tên enum nội bộ tự động làm thay đổi response.

## 9. Mapping collection, quan hệ lồng nhau và tránh N+1

Một kết quả use case có thể chứa danh sách hoặc quan hệ lồng nhau. Mapper cần biến mỗi phần tử thành DTO phù hợp, đồng thời chú ý dữ liệu đã được tải hay chưa.

Ví dụ, Order có nhiều OrderLine và mỗi dòng liên quan đến Product. Nếu mapper gọi product.getName() trên lazy association cho từng dòng, ORM có thể phát sinh một truy vấn bổ sung cho mỗi sản phẩm. Đây là vấn đề N+1 query.

Giải pháp thường nằm ở query layer:

- Dùng fetch join hoặc entity graph khi cần tải một tập quan hệ cụ thể.
- Dùng DTO projection từ truy vấn để chỉ lấy cột cần thiết.
- Gom dữ liệu liên quan trong một truy vấn hoặc một số truy vấn có kiểm soát.
- Tránh để mapper gọi repository trong vòng lặp.
- Đặt giới hạn cho collection và phân trang với danh sách lớn.

Mapper nên làm việc trên dữ liệu đã được chuẩn bị. Nó không nên vô tình kích hoạt nhiều truy vấn hoặc giữ một persistence session mở chỉ để template truy cập lazy field.

## 10. Projection cho danh sách và phân trang

Trang danh sách thường cần ít dữ liệu hơn trang chi tiết. Không nên tải toàn bộ aggregate cho hàng trăm mục chỉ để hiển thị vài cột.

Có thể định nghĩa projection cho một dòng danh sách:

~~~java
public record OrderListRow(
        long id,
        Instant createdAt,
        String customerName,
        BigDecimal totalAmount,
        String currency,
        OrderStatus status
) {
}
~~~

Query service trả về trang kết quả:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class OrderListQueryService {
    private final OrderReadRepository repository;

    public OrderListQueryService(OrderReadRepository repository) {
        this.repository = repository;
    }

    public Page<OrderListRow> search(long actorId, Pageable pageable) {
        return repository.findRowsForActor(actorId, pageable);
    }
}
~~~

Controller có thể ánh xạ Page thành ViewModel chứa nội dung và thông tin phân trang:

~~~java
public record PageViewModel<T>(
        List<T> items,
        int page,
        int pageSize,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious
) {
}
~~~

Không nên đưa toàn bộ đối tượng Page nội bộ của Spring thành hợp đồng API dài hạn nếu client cần một cấu trúc ổn định. Hãy ánh xạ thành response DTO có trường phân trang được công bố rõ. Đồng thời giới hạn page size ở máy chủ để tránh client yêu cầu tải một lượng dữ liệu quá lớn.

## 11. Giá trị null, Optional và dữ liệu thiếu

Mapping cần định nghĩa rõ cách xử lý giá trị không có:

- Null có nghĩa là không biết, không có hoặc chưa được thiết lập?
- Trường có bị bỏ qua trong JSON hay xuất hiện với giá trị null?
- Với cập nhật một phần, trường thiếu có nghĩa là giữ nguyên hay xóa giá trị?
- View nên hiển thị chuỗi rỗng, dấu gạch ngang hay thông báo “Chưa có”?

Không nên chuyển mọi null thành chuỗi rỗng trong mapper dùng chung. Ý nghĩa phụ thuộc trường và giao diện. Ví dụ, số điện thoại chưa có có thể hiển thị “Chưa cập nhật”, trong khi ngày giao hàng chưa xác định có thể hiển thị “Đang chờ xác nhận”.

Optional thường hữu ích ở biên truy vấn để thể hiện có hoặc không có kết quả. DTO thường dùng kiểu trường nullable hoặc một cấu trúc kết quả rõ ràng theo hợp đồng. Tránh dùng Optional làm kiểu field trong mọi DTO nếu serializer và client không có quy ước hỗ trợ.

Với JSON API, cần thống nhất giữa ba cách biểu diễn: trường bị bỏ qua, trường có giá trị null và trường có giá trị. Đối với PATCH, ba trạng thái này có thể mang ý nghĩa khác nhau và phải được mô tả trong hợp đồng.

## 12. Mapping lỗi nghiệp vụ thành phản hồi trình bày

Kết quả use case không phải lúc nào cũng thành công. Tầng trình bày cần chuyển lỗi thành thông tin phù hợp với người dùng hoặc client.

Ví dụ:

| Lỗi nghiệp vụ/kỹ thuật | Biểu diễn phù hợp |
|---|---|
| Không tìm thấy đơn hàng hoặc không thuộc phạm vi truy cập | Trang 404 hoặc API 404 theo chính sách |
| Không đủ tồn kho | Thông báo không thể đặt số lượng yêu cầu |
| Đơn hàng đã giao nên không thể hủy | Thông báo xung đột trạng thái, thường là 409 cho API |
| Đầu vào sai định dạng | Lỗi trường hoặc API 400 |
| Lỗi hệ thống ngoài dự kiến | Trang lỗi chung hoặc API 500 an toàn |

Không đưa stack trace, câu SQL, tên class nội bộ hoặc thông tin nhạy cảm vào ViewModel hay response. Có thể dùng mã lỗi ổn định để client xử lý và thông điệp đã được bản địa hóa cho người dùng.

Với Spring MVC, Controller có thể bắt lỗi ở phạm vi handler khi cần trải nghiệm cụ thể; các lỗi dùng chung nên được ánh xạ qua @ControllerAdvice và @ExceptionHandler. Mapper dữ liệu thành công không nên biến exception thành một response thành công giả.

## 13. Quyền truy cập và dữ liệu nhạy cảm

Mapping là một điểm quan trọng để kiểm soát dữ liệu nào được đưa ra ngoài, nhưng không phải nơi duy nhất để thực thi bảo mật.

- Query/use case phải giới hạn tài nguyên theo người dùng hoặc tenant trước khi trả kết quả.
- Response DTO chỉ chứa trường client được phép biết.
- Không serialize trực tiếp entity có trường nội bộ hoặc quan hệ không kiểm soát.
- Không dựa vào việc template không hiển thị trường để xem là dữ liệu đã được bảo vệ.
- Không đưa thông tin bí mật vào log mapping hoặc lỗi serialize.
- Với danh sách nhiều tenant, filter phạm vi dữ liệu phải được áp dụng trong truy vấn hoặc tầng nghiệp vụ có thẩm quyền.

Ví dụ, mapper có thể bỏ qua internalNote, nhưng nếu query service tải toàn bộ ghi chú nhạy cảm cho mọi người dùng rồi chỉ dựa vào mapper để lọc, dữ liệu vẫn đã đi qua những thành phần không cần thiết. Tốt hơn là giới hạn dữ liệu ngay từ query/use case và tiếp tục dùng DTO allowlist ở biên trình bày.

## 14. Kiểm thử mapping

Mapper thường là thành phần thuần dữ liệu nên có thể kiểm thử bằng unit test mà không cần khởi chạy Spring hoặc cơ sở dữ liệu.

Các tình huống cần kiểm tra:

1. **Ánh xạ trường cơ bản:** ID, tên, ngày, trạng thái và số tiền được chuyển đúng.
2. **Collection:** danh sách dòng hàng giữ đúng số phần tử và thứ tự theo hợp đồng.
3. **Giá trị thiếu:** null được xử lý đúng cho từng trường và View.
4. **Enum:** mỗi trạng thái nghiệp vụ có mã hoặc nhãn trình bày tương ứng.
5. **Tiền và ngày:** mapper giữ giá trị có kiểu; định dạng theo locale được kiểm tra ở lớp trình bày.
6. **Bảo mật:** trường nội bộ như password hash, internal note hoặc owner metadata không xuất hiện trong DTO.
7. **Quyền truy cập:** query/use case không trả tài nguyên ngoài phạm vi người gọi.
8. **Phân trang:** tổng số phần tử, số trang và các cờ điều hướng nhất quán.
9. **Hiệu năng truy vấn:** mapping không kích hoạt N+1 hoặc truy cập repository ẩn.
10. **Tương thích API:** response giữ cấu trúc đã công bố khi thay đổi nội bộ của entity.

Có thể dùng MockMvc để kiểm thử endpoint trả đúng JSON hoặc View name, nhưng unit test mapper vẫn cần thiết để cô lập logic chuyển đổi. Với MapStruct, nên kiểm thử cả mapping được sinh và các trường đã ignore.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Trả entity trực tiếp ra API | Lộ trường nội bộ và ràng buộc client vào persistence | Dùng response DTO allowlist |
| Đưa quy tắc nghiệp vụ vào mapper | Các use case có thể áp dụng quy tắc khác nhau | Để Model/service quyết định, mapper chỉ biểu diễn |
| Template truy cập repository hoặc lazy relation | N+1 query và phụ thuộc persistence | Chuẩn bị projection trước khi render |
| Dùng một DTO cho mọi View và API | Trường giao diện và hợp đồng công khai bị trộn | Tách theo mục đích khi nhu cầu khác nhau |
| Mapper truy vấn dữ liệu trong vòng lặp | Truy vấn ẩn, hiệu năng khó dự đoán | Tải dữ liệu ở query layer |
| Serialize toàn bộ Page hoặc entity framework | Hợp đồng API phụ thuộc thư viện | Tạo response DTO rõ ràng |
| Chuyển mọi null thành chuỗi rỗng | Mất ngữ nghĩa dữ liệu thiếu | Định nghĩa cách hiển thị theo từng trường |
| Tin mapper là biện pháp phân quyền duy nhất | Dữ liệu nhạy cảm vẫn được tải hoặc xử lý | Kiểm tra quyền ở query/use case và lọc DTO |
| Tự tính tổng tiền ở mỗi View | Các màn hình hiển thị kết quả khác nhau | Tính theo quy tắc nghiệp vụ một lần |

## 16. Checklist thiết kế presentation mapping

Trước khi hoàn thành một Controller hoặc endpoint, hãy xác nhận:

- Kết quả use case có biểu diễn rõ ý nghĩa nghiệp vụ không?
- ViewModel hoặc response DTO có được thiết kế theo đúng người tiêu thụ không?
- Có trường nào không cần thiết hoặc nhạy cảm đang được đưa ra không?
- Quy tắc nghiệp vụ có nằm trong Model/application service thay vì mapper không?
- Mapper có chỉ chuyển đổi dữ liệu đã được tải, không truy vấn repository ẩn không?
- Collection và quan hệ lồng nhau có tránh N+1 query không?
- Giá trị null, enum, ngày giờ, tiền tệ và locale có hợp đồng rõ không?
- Danh sách lớn có dùng projection và phân trang không?
- Lỗi nghiệp vụ có được ánh xạ thành phản hồi an toàn, dễ hiểu không?
- Unit test có bao phủ mapping, giá trị biên và trường nhạy cảm không?

Ánh xạ kết quả nghiệp vụ thành dữ liệu trình bày giúp MVC giữ ranh giới rõ giữa cách ứng dụng hoạt động và cách người dùng hoặc client nhìn thấy kết quả. Application service và Model quyết định kết quả đúng theo quy tắc nghiệp vụ; ViewModel và response DTO diễn đạt kết quả theo từng hợp đồng. Khi mapping có chủ đích, giao diện có thể thay đổi mà không buộc phải thay cấu trúc miền nghiệp vụ hoặc làm lộ dữ liệu nội bộ.
