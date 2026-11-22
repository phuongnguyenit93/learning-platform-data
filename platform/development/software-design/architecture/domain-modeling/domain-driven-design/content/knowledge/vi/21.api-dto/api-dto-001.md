# DTO của giao tiếp khác với Entity và Value Object của miền

Trong Domain-Driven Design (DDD), **Data Transfer Object (DTO)** là đối tượng dùng để truyền dữ liệu qua một ranh giới giao tiếp, chẳng hạn giữa client và API, giữa Presentation và Application, hoặc giữa hai tiến trình. DTO mô tả dữ liệu mà bên gửi và bên nhận cần trao đổi. Nó không đại diện cho toàn bộ mô hình nghiệp vụ và không nên trở thành nơi chứa các quy tắc cốt lõi của miền.

**Entity** và **Value Object** thuộc Domain Model. Entity có định danh và vòng đời; Value Object được xác định bởi giá trị và thường bất biến. Chúng thể hiện ý nghĩa, hành vi và bất biến nghiệp vụ trong một Bounded Context. DTO có thể mang dữ liệu lấy từ Entity hoặc Value Object, nhưng không vì thế mà trở thành chính đối tượng miền.

Ví dụ, API đặt hàng có thể nhận `PlaceOrderRequest` gồm địa chỉ giao và danh sách mã sản phẩm/số lượng. Application chuyển request thành command, tải dữ liệu cần thiết, tạo Order Aggregate và gọi hành vi miền. API trả `PlaceOrderResponse` chứa mã đơn và trạng thái. Client không cần nhận toàn bộ Aggregate Order, OrderLine, Customer hay các đối tượng nội bộ.

## 1. DTO là gì?

DTO là một cấu trúc dữ liệu được thiết kế để truyền thông tin qua một ranh giới. Nó thường chứa các trường đơn giản hoặc các DTO lồng nhau, có thể được serialize thành JSON, XML, Protocol Buffers hoặc một định dạng khác.

Một DTO thường có các đặc điểm:

- **Phục vụ giao tiếp:** cấu trúc được chọn theo nhu cầu của bên gửi và bên nhận.
- **Tập trung vào dữ liệu:** chủ yếu chứa trường dữ liệu, không sở hữu quy tắc nghiệp vụ cốt lõi.
- **Có thể được serialize:** thường phù hợp với định dạng truyền tin hoặc giao thức.
- **Có phạm vi rõ:** ví dụ request tạo đơn, response chi tiết đơn, hoặc dữ liệu phân trang.
- **Có thể thay đổi độc lập với Domain Model:** hợp đồng API có vòng đời và yêu cầu tương thích riêng.

DTO có thể dùng Java record, class mutable hoặc kiểu dữ liệu do framework sinh ra. Lựa chọn phụ thuộc framework và cách sử dụng; điều quan trọng là không để DTO điều khiển trực tiếp trạng thái nội bộ của Aggregate.

### 1.1. Các loại DTO thường gặp

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Request DTO | Nhận dữ liệu đầu vào từ client. | `PlaceOrderRequest`, `ChangeAddressRequest`. |
| Response DTO | Trả dữ liệu ra client. | `OrderSummaryResponse`, `OrderDetailsResponse`. |
| Command | Yêu cầu Application thực hiện một use case. | `PlaceOrderCommand`, `CancelOrderCommand`. |
| Query | Yêu cầu Application đọc dữ liệu. | `SearchOrdersQuery`, `OrderFilter`. |
| Integration DTO / Message Contract | Trao đổi dữ liệu giữa hệ thống hoặc Bounded Context. | `OrderConfirmedV1`. |

Các loại này có thể có trường giống nhau nhưng phục vụ các hợp đồng khác nhau. Không nhất thiết dùng chung một class cho tất cả chỉ vì chúng chứa cùng một mã đơn hàng.

## 2. DTO khác Entity như thế nào?

Entity là khái niệm miền có định danh ổn định qua thời gian. Hai Entity có cùng thuộc tính vẫn có thể là hai đối tượng khác nhau nếu định danh khác nhau. Entity thường có hành vi và chịu trách nhiệm bảo vệ quy tắc liên quan đến vòng đời.

DTO chủ yếu truyền dữ liệu. Nó không cần có định danh miền hay vòng đời nghiệp vụ; một request DTO có thể chỉ tồn tại trong thời gian xử lý một HTTP request.

| Tiêu chí | DTO | Entity |
| --- | --- | --- |
| Mục đích | Truyền dữ liệu qua ranh giới. | Mô hình hóa một khái niệm có định danh trong miền. |
| Định danh | Có thể có ID kỹ thuật hoặc business ID để truyền, nhưng không bắt buộc. | Có định danh để phân biệt đối tượng qua thời gian. |
| Hành vi | Thường tập trung vào dữ liệu và chuyển đổi. | Có hành vi nghiệp vụ và quản lý trạng thái. |
| Bất biến | Chủ yếu kiểm tra cấu trúc đầu vào/đầu ra. | Bảo vệ bất biến nghiệp vụ. |
| Vòng đời | Thường gắn với request, response hoặc message. | Thuộc vòng đời nghiệp vụ. |
| Thay đổi | Theo version và nhu cầu hợp đồng giao tiếp. | Theo quy tắc và ngôn ngữ của Bounded Context. |
| Phụ thuộc | Có thể phụ thuộc định dạng API hoặc serialization. | Nên độc lập với giao thức và chi tiết vận chuyển. |

Ví dụ, `OrderResponse` có thể chứa `orderId`, `status` và `totalAmount`. Nó không cần có phương thức `cancel()`. Hành vi hủy thuộc Order Aggregate; API gọi use case hủy, Application tải Order và gọi `order.cancel(reason)`.

### 2.1. Không trả Entity trực tiếp từ API

Trả trực tiếp Entity hoặc Aggregate qua API có thể gây ra:

- **Rò rỉ mô hình nội bộ:** client phụ thuộc vào cấu trúc và cách đặt tên trong Domain.
- **Lộ dữ liệu không nên công khai:** Entity có thể chứa ghi chú nội bộ, thông tin nhạy cảm hoặc trường phục vụ xử lý.
- **Vòng tham chiếu khi serialize:** quan hệ hai chiều giữa Entity có thể tạo object graph vòng lặp.
- **Mass assignment:** client gửi thêm trường có thể ảnh hưởng trạng thái mà API không chủ định cho phép.
- **Khó version API:** thay đổi Domain có thể vô tình làm thay đổi JSON công khai.
- **Tải dữ liệu quá mức:** Aggregate có thể chứa nhiều đối tượng không cần thiết cho response.

DTO cho phép API công bố đúng dữ liệu cần thiết và giữ mô hình miền độc lập với hợp đồng bên ngoài.

## 3. DTO khác Value Object như thế nào?

Value Object là đối tượng miền được xác định bởi giá trị của nó thay vì định danh riêng. Hai Value Object có cùng giá trị và cùng ngữ nghĩa thường được xem là bằng nhau. Value Object thường bất biến và có thể chứa hành vi, phép tính hoặc quy tắc xác thực thuộc miền.

DTO cũng có thể bất biến và có các trường giống Value Object, nhưng mục đích khác nhau:

| Tiêu chí | DTO | Value Object |
| --- | --- | --- |
| Mục đích | Truyền dữ liệu qua ranh giới. | Mô hình hóa một giá trị có ý nghĩa nghiệp vụ. |
| Ngữ nghĩa | Theo hợp đồng giao tiếp. | Theo ngôn ngữ miền. |
| Hành vi | Thường ít hoặc không có hành vi miền. | Có thể có phép tính và quy tắc miền. |
| Bằng nhau | Theo yêu cầu của cấu trúc dữ liệu hoặc ngôn ngữ. | Thường dựa trên toàn bộ giá trị cấu thành. |
| Thay đổi | Theo version API/message. | Theo chính sách và ý nghĩa của Bounded Context. |

Ví dụ, `Money` là Value Object có thể kiểm tra đơn vị tiền tệ, cộng hai khoản tiền cùng loại hoặc nhân với số lượng. `MoneyResponse` chỉ là DTO biểu diễn số tiền và mã tiền tệ cho API.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

// Value Object thuộc Domain
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}

~~~

~~~java
// DTO thuộc ranh giới API, được đặt trong file riêng
public record MoneyResponse(
        String amount,
        String currency
) {}
~~~

DTO có thể dùng String cho amount để kiểm soát định dạng thập phân trong JSON. Domain dùng BigDecimal và Currency để biểu diễn giá trị và quy tắc tiền tệ. Mapper chịu trách nhiệm chuyển đổi giữa hai mô hình.

Hai kiểu trong ví dụ thuộc hai mô hình khác nhau và thường được đặt ở package hoặc file riêng.

## 4. DTO thuộc ranh giới giao tiếp

Một DTO nên được thiết kế từ góc nhìn của bên sử dụng hợp đồng. Cùng một Aggregate có thể được biểu diễn bằng nhiều DTO tùy use case:

- Danh sách đơn chỉ cần mã, ngày tạo, trạng thái và tổng tiền.
- Màn hình chi tiết cần địa chỉ, dòng hàng và thông tin giao.
- Request hủy chỉ cần mã đơn và lý do.
- Request tạo đơn cần danh sách sản phẩm và số lượng.

Không có lý do để một DTO khổng lồ chứa mọi trường có thể có của Order chỉ để dùng lại ở nhiều endpoint.

### 4.1. Thiết kế Request DTO theo hành động API

Ví dụ request tạo đơn:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

public record PlaceOrderRequest(
        @NotNull @Valid AddressRequest deliveryAddress,
        @NotEmpty @Size(max = 50) List<@Valid OrderLineRequest> lines
) {
    public record AddressRequest(
            @NotBlank @Size(max = 120) String street,
            @NotBlank @Size(max = 80) String city,
            @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
    ) {}

    public record OrderLineRequest(
            @NotBlank String productId,
            @Positive int quantity
    ) {}
}
~~~

Các annotation trên minh họa validation cấu trúc tại ranh giới HTTP. Tùy framework và phiên bản Jakarta Validation, cách đặt annotation lên phần tử collection có thể cần điều chỉnh. Request chỉ chứa thông tin client được phép gửi; giá, trạng thái, chiết khấu và người tạo được hệ thống xác định theo chính sách.

### 4.2. Thiết kế Response DTO theo nhu cầu người dùng

~~~java
import java.time.Instant;
import java.util.List;

public final class OrderDtos {
    private OrderDtos() {}

    public record MoneyResponse(String amount, String currency) {}

    public record AddressResponse(
            String street,
            String city,
            String countryCode
    ) {}

    public record OrderLineResponse(
            String productId,
            String productName,
            int quantity,
            MoneyResponse unitPrice,
            MoneyResponse subtotal
    ) {}

    public record OrderDetailsResponse(
            String orderId,
            String status,
            Instant createdAt,
            MoneyResponse total,
            AddressResponse deliveryAddress,
            List<OrderLineResponse> lines
    ) {}
}
~~~

Response chỉ công bố dữ liệu cần cho màn hình chi tiết. Một endpoint danh sách có thể dùng `OrderSummaryResponse` nhỏ hơn để giảm payload và tránh tải các quan hệ không cần thiết.

### 4.3. Request và Response không nhất thiết đối xứng

Request tạo đơn không nên nhận `status`, `totalAmount` hoặc `discount` nếu các giá trị đó do hệ thống quyết định. Response có thể trả các giá trị này để client hiển thị.

Đầu vào và đầu ra phản ánh hai hướng khác nhau:

- Request cho biết client được phép yêu cầu điều gì.
- Response cho biết hệ thống xác nhận hoặc trả về điều gì.

Dùng chung một DTO cho cả hai chiều dễ tạo ra trường không phù hợp, mở rộng quyền ghi không chủ định và làm hợp đồng khó tiến hóa.

## 5. Luồng chuyển đổi từ DTO sang Domain Model

Một luồng thường gặp trong DDD:

1. Presentation nhận Request DTO và kiểm tra cấu trúc đầu vào.
2. Presentation hoặc Application chuyển DTO thành Command có ý nghĩa use case.
3. Application tải Aggregate hoặc dữ liệu cần thiết.
4. Domain tạo hoặc thay đổi Entity/Value Object thông qua hành vi nghiệp vụ.
5. Application lưu Aggregate.
6. Application hoặc mapper tạo Response DTO từ kết quả miền.
7. Presentation serialize Response DTO thành JSON hoặc định dạng giao tiếp.

~~~mermaid
flowchart LR
    C[Client] --> R[Request DTO]
    R --> V[Structural Validation]
    V --> M[Mapping to Command]
    M --> A[Application Use Case]
    A --> D[Domain Entity / Value Object / Aggregate]
    D --> A
    A --> S[Repository Save]
    A --> O[Response Mapping]
    O --> T[Response DTO]
    T --> C
~~~

DTO không nên được truyền sâu vào Domain chỉ vì nó đã chứa đủ trường. Hãy chuyển đổi sang kiểu miền ở ranh giới phù hợp để Domain không phụ thuộc vào API.

## 6. Ví dụ: API đặt hàng và Domain Model

Giả sử client gửi yêu cầu tạo đơn gồm địa chỉ giao hàng và danh sách sản phẩm/số lượng. Giá được lấy từ Catalog; tổng tiền do hệ thống tính. Order là Aggregate Root và OrderLine thuộc vòng đời của Order.

### 6.1. Request DTO

~~~java
public record PlaceOrderRequest(
        AddressRequest deliveryAddress,
        List<OrderLineRequest> lines
) {
    public record AddressRequest(
            String street,
            String city,
            String countryCode
    ) {}

    public record OrderLineRequest(
            String productId,
            int quantity
    ) {}
}
~~~

Request không có trường giá, trạng thái hoặc tổng tiền. Client không thể quyết định các giá trị do miền hoặc hệ thống sở hữu.

### 6.2. Command của Application

~~~java
public record PlaceOrderCommand(
        AddressInput deliveryAddress,
        List<OrderLineInput> lines
) {
    public record AddressInput(
            String street,
            String city,
            String countryCode
    ) {}

    public record OrderLineInput(
            String productId,
            int quantity
    ) {}
}
~~~

Command biểu diễn yêu cầu của use case. Nó có thể giống Request DTO ở một số trường, nhưng không bị ràng buộc bởi tên field, annotation hay version của HTTP API. Nếu ứng dụng chỉ có một adapter và hợp đồng đơn giản, có thể dùng chung một kiểu ở ranh giới Presentation/Application khi trade-off được chấp nhận; không nên mặc định rằng DTO và Command luôn phải là hai class riêng.

### 6.3. Mapping từ Request sang Command

~~~java
public final class PlaceOrderRequestMapper {
    public PlaceOrderCommand toCommand(PlaceOrderRequest request) {
        return new PlaceOrderCommand(
                new PlaceOrderCommand.AddressInput(
                        request.deliveryAddress().street(),
                        request.deliveryAddress().city(),
                        request.deliveryAddress().countryCode()
                ),
                request.lines().stream()
                        .map(line -> new PlaceOrderCommand.OrderLineInput(
                                line.productId(),
                                line.quantity()
                        ))
                        .toList()
        );
    }
}
~~~

Mapper chỉ chuyển đổi dữ liệu và không tự quyết định giá hoặc kiểm tra chính sách nghiệp vụ. Nếu request có cấu trúc không hợp lệ, validation ở ranh giới có thể từ chối trước khi tạo Command.

### 6.4. Application tải dữ liệu và điều phối

~~~java
import java.util.List;

public final class PlaceOrderService {
    private final OrderRepository orders;
    private final ProductCatalog products;
    private final OrderIdGenerator ids;

    public PlaceOrderService(
            OrderRepository orders,
            ProductCatalog products,
            OrderIdGenerator ids
    ) {
        this.orders = orders;
        this.products = products;
        this.ids = ids;
    }

    public Order place(PlaceOrderCommand command) {
        List<OrderLine> lines = command.lines().stream()
                .map(input -> {
                    ProductSnapshot product = products.get(input.productId());
                    return new OrderLine(
                            new ProductId(input.productId()),
                            product.name(),
                            product.price(),
                            new Quantity(input.quantity())
                    );
                })
                .toList();

        Order order = Order.place(
                ids.next(),
                new Address(
                        command.deliveryAddress().street(),
                        command.deliveryAddress().city(),
                        command.deliveryAddress().countryCode()
                ),
                lines
        );

        orders.save(order);
        return order;
    }
}
~~~

Các kiểu Order, ProductCatalog, ProductSnapshot, OrderLine, ProductId, Quantity, Address và OrderIdGenerator được giả định đã được định nghĩa. Ví dụ minh họa rằng giá được lấy từ nguồn dữ liệu do hệ thống tin cậy; Domain nhận các kiểu miền và bảo vệ các bất biến như số lượng dương, dòng hàng hợp lệ và quy tắc tạo đơn.

Trong một hệ thống thật, cần xác định cách xử lý sản phẩm không tồn tại, giá thay đổi đồng thời, tồn kho, thuế, chiết khấu và transaction. Không nên để mapper tự tải Catalog hoặc gọi dịch vụ ngoài vì như vậy nó đã trở thành một phần của use case.

### 6.5. Response mapping

Sau khi use case thành công, Application hoặc một presenter/mapper tạo response:

~~~java
public record PlaceOrderResponse(
        String orderId,
        String status,
        String totalAmount,
        String currency
) {}

public final class OrderResponseMapper {
    public PlaceOrderResponse toResponse(Order order) {
        Money total = order.total();
        return new PlaceOrderResponse(
                order.id().value(),
                order.status().name(),
                total.amount().toPlainString(),
                total.currency().getCurrencyCode()
        );
    }
}
~~~

Mapper chuyển dữ liệu từ mô hình miền sang hợp đồng API. Nó không nên gọi `order.confirm()`, sửa trạng thái hoặc quyết định chính sách. Việc tính `order.total()` ở đây là lời gọi truy vấn miền; nếu response cần dữ liệu đã có trong kết quả use case, có thể trả một read model phù hợp để tránh tải lại.

## 7. Validation: cấu trúc đầu vào và quy tắc nghiệp vụ

Validation thường có nhiều mức. Cần phân biệt kiểm tra dữ liệu có thể đọc được với kiểm tra một hành động có hợp lệ theo nghiệp vụ hay không.

### 7.1. Structural validation ở ranh giới

Presentation có thể kiểm tra:

- Trường bắt buộc có được gửi không.
- Chuỗi có vượt độ dài cho phép không.
- Số lượng có đúng kiểu và lớn hơn không.
- JSON có đúng cấu trúc không.
- Định dạng email, ngày hoặc mã quốc gia có hợp lệ về cú pháp không.
- Collection có vượt giới hạn payload không.

Các kiểm tra này giúp từ chối request sai định dạng sớm và trả lỗi phù hợp với giao thức.

### 7.2. Semantic validation trong Domain

Domain chịu trách nhiệm kiểm tra ý nghĩa nghiệp vụ:

- Sản phẩm có được phép bán trong ngữ cảnh này không.
- Đơn đã xác nhận có thể thêm dòng hàng không.
- Khách hàng có đủ điều kiện hưởng chính sách không.
- Số lượng có vượt giới hạn nghiệp vụ không.
- Khoản chiết khấu có vượt tổng tiền không.
- Đơn có thể hủy ở trạng thái hiện tại không.

Các quy tắc này cần được bảo vệ tại Entity, Value Object, Aggregate hoặc Domain Service phù hợp, để mọi adapter đều tuân theo cùng một mô hình.

### 7.3. Không nhầm validation của DTO với bảo vệ bất biến

Một request có thể vượt qua annotation validation nhưng vẫn không hợp lệ theo miền. Ví dụ, `quantity = 2` là số nguyên dương nhưng sản phẩm có thể chỉ còn một đơn vị. Ngược lại, dữ liệu có thể hợp lệ về nghiệp vụ nhưng không hợp lệ theo hợp đồng API nếu client thiếu trường bắt buộc.

Hai mức validation phục vụ hai ranh giới khác nhau và không thay thế nhau.

## 8. Bảo mật và quyền kiểm soát dữ liệu

DTO là một phần của bề mặt giao tiếp công khai hoặc nội bộ. Thiết kế DTO cần giới hạn dữ liệu được nhận và được trả.

### 8.1. Tránh Mass Assignment

Không bind trực tiếp request JSON vào Entity có nhiều setter công khai. Nếu client gửi thêm trường `status`, `discount`, `approvedBy` hoặc `isAdmin`, framework có thể gán vào đối tượng nếu mapping cho phép.

Hãy định nghĩa Request DTO chỉ chứa các trường client được phép gửi, sau đó chuyển thành Command và để Application/Domain quyết định phần còn lại.

### 8.2. Chỉ trả dữ liệu được phép công khai

Response DTO nên dùng allowlist: chỉ đưa các trường mà client cần và được phép xem. Không serialize toàn bộ Entity rồi cố loại bỏ một vài trường nhạy cảm.

Ví dụ, Order có thể chứa ghi chú nội bộ, dữ liệu đánh giá rủi ro hoặc thông tin vận hành không nên xuất hiện trong response khách hàng. `OrderDetailsResponse` chỉ chứa địa chỉ giao, dòng hàng và trạng thái được phép công bố.

### 8.3. Không tin dữ liệu định danh hoặc quyền từ client

Nếu người dùng gửi `customerId`, Application cần kiểm tra actor có quyền thao tác với khách hàng đó hay không. Không xem một ID trong DTO là bằng chứng về quyền sở hữu. Tương tự, không nhận vai trò, trạng thái phê duyệt hoặc giá cuối cùng từ client nếu đó là dữ liệu do hệ thống quyết định.

### 8.4. Cẩn trọng với dữ liệu nhạy cảm

Không đưa mật khẩu, access token, thông tin thanh toán đầy đủ hoặc dữ liệu cá nhân không cần thiết vào DTO và log. Response chỉ nên trả dữ liệu theo nguyên tắc tối thiểu cần thiết.

## 9. Versioning và khả năng tương thích của DTO

DTO công khai là một hợp đồng. Khi client và server được triển khai độc lập, thay đổi cấu trúc có thể ảnh hưởng bên sử dụng.

### 9.1. Thay đổi thường tương thích

Trong một số định dạng như JSON, thêm một trường response tùy chọn thường có thể tương thích với client bỏ qua trường chưa biết. Tuy nhiên, vẫn cần xem xét client có strict schema validation hay không.

Các thay đổi có rủi ro cao hơn:

- Xóa hoặc đổi tên trường.
- Đổi kiểu dữ liệu.
- Thay đổi ý nghĩa của trường mà không đổi tên.
- Biến trường tùy chọn thành bắt buộc.
- Thay đổi đơn vị hoặc quy tắc làm tròn.
- Thêm giá trị enum mà client cũ không xử lý được.

### 9.2. Thiết kế trường có khả năng tiến hóa

Một số thực hành:

- Dùng tên trường có ngữ nghĩa rõ.
- Ghi rõ đơn vị và múi giờ cho ngày/giờ hoặc số đo khi cần.
- Có quy tắc cho trường optional và giá trị null.
- Không dùng số thực nhị phân cho tiền.
- Có chiến lược xử lý giá trị enum chưa biết.
- Tách DTO theo use case để thay đổi một endpoint không làm ảnh hưởng toàn bộ API.
- Duy trì contract test hoặc schema test cho API quan trọng.

### 9.3. Version API khi cần

Có thể quản lý version qua URL như `/v1/orders`, header hoặc schema registry tùy kiến trúc. Không phải mọi thay đổi đều cần version mới; ưu tiên thay đổi tương thích và có lộ trình deprecation. Khi thay đổi không tương thích, cần thông báo, hỗ trợ giai đoạn chuyển tiếp và có kiểm thử consumer.

## 10. DTO không phải Integration Event

DTO của HTTP API và Integration Event đều là hợp đồng truyền dữ liệu nhưng phục vụ mục tiêu khác:

| Tiêu chí | API DTO | Integration Event |
| --- | --- | --- |
| Mục đích | Request/response cho một thao tác hoặc truy vấn. | Thông báo một sự việc đã xảy ra. |
| Ngữ nghĩa | Theo endpoint và use case. | Theo sự kiện nghiệp vụ. |
| Thời điểm | Thường gắn với một request/response. | Có thể được tiêu thụ bất đồng bộ sau đó. |
| Tương tác | Client yêu cầu hoặc nhận dữ liệu. | Producer công bố, consumer xử lý. |
| Version | Theo hợp đồng API. | Theo hợp đồng message/event. |

Không nên dùng trực tiếp Request DTO làm message event chỉ vì các trường giống nhau. Một command như `PlaceOrderRequest` là yêu cầu; `OrderPlaced` là sự thật đã xảy ra. Event nên có định danh, thời điểm nghiệp vụ và payload phù hợp với consumer.

## 11. DTO và Persistence Entity cũng khác nhau

Persistence Entity là cấu trúc phục vụ ORM hoặc cơ sở dữ liệu. Nó có thể phản ánh bảng, khóa ngoại, cột và quan hệ lưu trữ. DTO phản ánh hợp đồng giao tiếp. Domain Entity phản ánh khái niệm và hành vi nghiệp vụ.

Ba mô hình có thể có một số trường giống nhau nhưng không nên mặc định dùng chung:

~~~mermaid
flowchart TD
    A[HTTP Request JSON] --> B[Request DTO]
    B --> C[Application Command]
    C --> D[Domain Aggregate]
    D --> E[Repository]
    E --> F[Persistence Entity / Database]
    D --> G[Response Mapper]
    G --> H[Response DTO]
    H --> I[HTTP Response JSON]
~~~

Việc tách mô hình cho phép:

- API thay đổi mà không phải thay đổi Domain.
- Cơ sở dữ liệu thay đổi mà không làm client thay đổi.
- Domain giữ kiểu và hành vi theo ngôn ngữ miền.
- Mỗi ranh giới có thể được kiểm thử riêng.

Không cần tạo ba class riêng cho mọi trường hợp đơn giản nếu chúng thực sự có cùng ngữ nghĩa và vòng đời. Tuy nhiên, việc dùng chung phải là quyết định có chủ đích, không phải mặc định vì tiện mapping.

## 12. Mapping DTO và Domain Model

Mapping là chuyển đổi dữ liệu giữa các mô hình. Có thể thực hiện thủ công, dùng thư viện mapping hoặc đặt trong assembler/mapper chuyên biệt.

### 12.1. Mapping thủ công

Mapping thủ công phù hợp khi số trường ít và chuyển đổi có quy tắc rõ:

~~~java
public OrderId toDomainId(String value) {
    return new OrderId(value);
}
~~~

Ưu điểm là dễ đọc, kiểm soát được phép chuyển đổi và không cần thêm dependency. Khi mapping phức tạp, có thể tách thành mapper để Application Service không bị lẫn chi tiết chuyển đổi.

### 12.2. Dùng thư viện mapping

MapStruct hoặc công cụ tương tự có thể giảm code lặp khi mapping nhiều DTO và persistence model. Tuy nhiên:

- Cần kiểm tra mapping có bỏ sót trường quan trọng không.
- Không để mapper tự quyết định quy tắc nghiệp vụ.
- Không dùng mapping tự động để cập nhật toàn bộ Aggregate từ request.
- Các chuyển đổi có ý nghĩa miền như Money, Quantity hoặc trạng thái cần được thể hiện rõ.

### 12.3. Mapping không phải nơi thực hiện use case

Mapper không nên tải Product từ Repository, gọi Payment Gateway, kiểm tra quyền hoặc xác nhận đơn. Những việc đó cần Application điều phối. Mapper chuyển đổi dữ liệu; nó không quyết định nghiệp vụ.

## 13. DTO trong API đọc và ghi

API đọc và ghi có thể cần cấu trúc khác nhau.

### 13.1. Write DTO

Write DTO thể hiện dữ liệu cần để yêu cầu một hành động. Ví dụ:

~~~json
{
  "deliveryAddress": {
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "lines": [
    {
      "productId": "SKU-01",
      "quantity": 2
    }
  ]
}
~~~

Client không gửi trạng thái hoặc tổng tiền nếu các giá trị đó do hệ thống quyết định.

### 13.2. Read DTO

Read DTO có thể tổng hợp dữ liệu từ nhiều nguồn để phục vụ màn hình:

~~~json
{
  "orderId": "ORD-1042",
  "status": "CONFIRMED",
  "customerName": "Nguyen An",
  "total": {
    "amount": "1250000",
    "currency": "VND"
  },
  "lineCount": 2
}
~~~

Đây là projection dành cho truy vấn. Nó không cần là một Entity hoặc Aggregate và không nhất thiết phải được lưu theo cùng cấu trúc của Domain Model.

### 13.3. Không ép Read DTO thành mô hình ghi

Một màn hình có thể cần tên khách, tổng tiền, số lượng dòng và trạng thái. Request cập nhật đơn chỉ cần địa chỉ hoặc một thay đổi cụ thể. Dùng cùng DTO cho cả đọc và ghi có thể tạo ra nhiều trường optional, các quy tắc không rõ và nguy cơ ghi đè dữ liệu.

## 14. Xử lý lỗi validation và API response

Khi Request DTO không hợp lệ về cấu trúc, API có thể trả lỗi 400 với danh sách trường và mã lỗi. Khi yêu cầu hợp lệ về cấu trúc nhưng bị từ chối bởi quy tắc miền, API cần chuyển kết quả miền sang một response lỗi phù hợp.

Ví dụ cấu trúc lỗi:

~~~java
public record ApiError(
        String code,
        String message,
        List<FieldViolation> violations
) {
    public record FieldViolation(
            String field,
            String reason
    ) {}
}
~~~

Không nên trả stack trace, tên class nội bộ hoặc SQL error cho client. Message công khai nên đủ để người dùng hiểu cách sửa; chi tiết kỹ thuật được ghi log ở phía server theo chính sách bảo mật.

Phân biệt:

- Lỗi parse hoặc validation DTO: request không đáp ứng hợp đồng.
- Lỗi nghiệp vụ: hành động không được phép theo Domain.
- Lỗi xác thực/phân quyền: actor không được phép thực hiện.
- Lỗi kỹ thuật: database, network hoặc hệ thống ngoài gặp sự cố.

Các loại lỗi có thể được ánh xạ sang HTTP status khác nhau theo hợp đồng API; cần thống nhất để client xử lý ổn định.

## 15. Kiểm thử DTO và mapping

DTO và mapping có thể được kiểm thử riêng với Domain:

- Request DTO nhận đúng JSON và xử lý trường bắt buộc.
- Validation từ chối dữ liệu sai định dạng hoặc vượt giới hạn.
- Mapper chuyển đúng các trường và kiểu dữ liệu.
- Response DTO không chứa trường nội bộ hoặc nhạy cảm.
- API contract giữ tương thích với client đã công bố.
- Domain vẫn bảo vệ bất biến khi được gọi qua bất kỳ adapter nào.

Ví dụ kiểm thử mapper:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PlaceOrderRequestMapperTest {
    @Test
    void mapsRequestLinesToCommandLines() {
        PlaceOrderRequest request = new PlaceOrderRequest(
                new PlaceOrderRequest.AddressRequest(
                        "12 Nguyen Hue", "Ho Chi Minh City", "VN"
                ),
                List.of(new PlaceOrderRequest.OrderLineRequest("SKU-01", 2))
        );

        PlaceOrderCommand command =
                new PlaceOrderRequestMapper().toCommand(request);

        assertEquals("SKU-01", command.lines().getFirst().productId());
        assertEquals(2, command.lines().getFirst().quantity());
    }
}
~~~

Ví dụ dùng `List.getFirst()` yêu cầu Java 21 trở lên; với phiên bản thấp hơn dùng `get(0)`. Kiểm thử mapper không thay thế kiểm thử Domain như xác nhận đơn rỗng bị từ chối hoặc số lượng không hợp lệ không thể tạo Value Object.

## 16. Những sai lầm thường gặp

### 16.1. Dùng Entity làm Request/Response DTO

Điều này gắn chặt API với mô hình miền, có nguy cơ lộ dữ liệu và cho phép client sửa các trường không nên sửa. Hãy dùng DTO theo hợp đồng API.

### 16.2. Dùng một DTO cho mọi endpoint

Một `OrderDto` khổng lồ chứa trường tạo, sửa, chi tiết, danh sách, phê duyệt và thanh toán khiến nhiều trường không liên quan trở thành optional. Tách DTO theo mục tiêu giao tiếp.

### 16.3. Đưa quy tắc nghiệp vụ vào DTO

DTO có thể kiểm tra cấu trúc như không null, độ dài hoặc định dạng. Nhưng nó không nên quyết định một Order có thể hủy hoặc một khách hàng có đủ điều kiện nhận chiết khấu hay không.

### 16.4. Dùng DTO như Entity miền

Một DTO có trường `id`, `status` và `lines` vẫn không tự trở thành Aggregate. Nó không tự bảo vệ bất biến hoặc sở hữu vòng đời nghiệp vụ.

### 16.5. Mapping tự động toàn bộ request vào Aggregate

Việc copy mọi trường từ request vào Entity có thể ghi đè trạng thái do hệ thống quản lý. Hãy chuyển từng hành động được phép thành phương thức miền cụ thể.

### 16.6. Dùng một kiểu cho cả HTTP và message

API request và Integration Event có ngữ nghĩa, vòng đời và chính sách version khác nhau. Tách hợp đồng khi chúng phục vụ các mục đích khác nhau.

### 16.7. Trả dữ liệu thừa

Serialize toàn bộ Aggregate có thể lộ dữ liệu nội bộ và tạo payload lớn. Hãy chọn đúng trường cho từng response.

### 16.8. Không quản lý version hợp đồng

Đổi tên hoặc đổi kiểu field mà không đánh giá consumer có thể phá vỡ client cũ. Hãy dùng thay đổi tương thích, contract test và versioning khi cần.

### 16.9. Nhầm validation với authorization

Một request có customerId hợp lệ về định dạng không có nghĩa actor có quyền truy cập khách hàng đó. Phân quyền phải được kiểm tra theo danh tính và chính sách truy cập.

## 17. Quy trình thiết kế DTO cho một use case

Khi thiết kế một endpoint hoặc adapter, có thể đi theo các bước:

1. **Xác định mục tiêu giao tiếp:** client muốn yêu cầu hành động hay đọc dữ liệu?
2. **Xác định trường được phép gửi/nhận:** chỉ công bố dữ liệu cần thiết.
3. **Thiết kế Request/Response riêng:** không mặc định dùng chung một DTO hai chiều.
4. **Đặt validation cấu trúc ở ranh giới:** kiểm tra kiểu, định dạng, độ dài và trường bắt buộc.
5. **Chuyển sang Command/Query:** dùng kiểu phù hợp với use case, không mang chi tiết HTTP vào Application.
6. **Tải dữ liệu và gọi Domain:** Application điều phối, Aggregate/Value Object/Domain Service bảo vệ quy tắc.
7. **Mapping kết quả sang Response DTO:** chỉ trả dữ liệu được phép công khai.
8. **Kiểm tra bảo mật:** tránh mass assignment, lộ dữ liệu nhạy cảm và tin cậy ID từ client một cách mù quáng.
9. **Xác định versioning:** đánh giá tác động của thay đổi đến client và consumer.
10. **Kiểm thử contract và mapping:** kiểm tra JSON, validation, mapping và hành vi miền độc lập.

~~~mermaid
flowchart TD
    A[Thiết kế use case API] --> B[Request DTO]
    B --> C[Validate cấu trúc và quyền truy cập]
    C --> D[Map thành Command]
    D --> E[Application điều phối]
    E --> F[Domain bảo vệ quy tắc]
    F --> G[Repository lưu Aggregate]
    G --> H[Map kết quả sang Response DTO]
    H --> I[Contract / Serialization Test]
~~~

## 18. Checklist thiết kế DTO

- [ ] DTO được thiết kế theo nhu cầu giao tiếp cụ thể.
- [ ] Request và Response được tách khi chúng có mục đích hoặc quyền dữ liệu khác nhau.
- [ ] Không serialize trực tiếp Aggregate hoặc Entity ra API.
- [ ] DTO không trở thành nơi chứa quy tắc nghiệp vụ cốt lõi.
- [ ] Entity và Value Object vẫn thuộc Domain Model và bảo vệ bất biến.
- [ ] Request chỉ nhận các trường client được phép thay đổi.
- [ ] Response chỉ công bố dữ liệu cần thiết và được phép xem.
- [ ] Structural validation và semantic validation được phân biệt.
- [ ] Application chuyển DTO thành Command/Query phù hợp.
- [ ] Mapper chỉ chuyển đổi dữ liệu, không điều phối use case hoặc gọi hạ tầng.
- [ ] Kiểu tiền, ngày giờ, múi giờ và đơn vị được biểu diễn rõ.
- [ ] Hợp đồng có chiến lược tương thích và versioning phù hợp.
- [ ] Integration Event được tách khi có ngữ nghĩa và vòng đời riêng.
- [ ] Có kiểm thử DTO, validation, mapping, contract và Domain.

## 19. Kết luận

DTO là hợp đồng dữ liệu ở ranh giới giao tiếp; Entity và Value Object là thành phần của mô hình miền. DTO giúp API nhận và trả đúng dữ liệu cần thiết, kiểm soát trường được phép thay đổi, tránh lộ cấu trúc nội bộ và cho phép hợp đồng tiến hóa độc lập với Domain Model.

Trong DDD, Request DTO nên được chuyển thành Command hoặc kiểu đầu vào phù hợp; Application điều phối use case; Domain Entity, Value Object và Aggregate bảo vệ hành vi cùng bất biến; kết quả được ánh xạ thành Response DTO. Không cần tách class một cách máy móc nếu hai mô hình thực sự có cùng ý nghĩa và vòng đời, nhưng cũng không nên dùng chung chỉ vì các trường hiện tại giống nhau. Hãy xác định ranh giới dựa trên ngữ nghĩa, quyền sở hữu và tốc độ thay đổi của từng hợp đồng.
