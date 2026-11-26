# Biểu diễn lỗi và kết quả nghiệp vụ có ý nghĩa rõ ràng

Một ca sử dụng thường không chỉ có một kết quả thành công. Khi đặt hàng, hệ thống có thể tạo đơn, từ chối vì sản phẩm hết hàng, hoặc không cho phép đặt vì khách hàng đã vượt hạn mức tín dụng. Những trường hợp này mang ý nghĩa nghiệp vụ khác nhau và cần được biểu diễn đủ rõ để tầng ứng dụng quyết định bước tiếp theo, giao diện trình bày thông báo phù hợp, còn người phát triển có thể kiểm thử từng tình huống.

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, tập trung vào cách tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Tầng nghiệp vụ**, ta xem cách mô hình hóa kết quả và lỗi nghiệp vụ sao cho quy tắc của bài toán không bị trộn với HTTP, cơ sở dữ liệu hoặc thông báo dành riêng cho giao diện.

## Kết quả nghiệp vụ không chỉ là thành công hoặc thất bại

Hãy xét một ca sử dụng đặt hàng. Một số kết quả có thể xảy ra:

| Tình huống | Ý nghĩa nghiệp vụ | Hướng xử lý có thể có |
|---|---|---|
| Đơn hàng hợp lệ và được chấp nhận | Ca sử dụng hoàn tất | Lưu đơn và trả mã đơn hàng |
| Một sản phẩm không đủ tồn kho | Yêu cầu chưa thể được đáp ứng | Hiển thị sản phẩm và số lượng còn thiếu; người dùng có thể điều chỉnh giỏ hàng |
| Khách hàng vượt hạn mức tín dụng | Chính sách tín dụng từ chối đơn | Thông báo lý do hoặc hướng dẫn liên hệ bộ phận phụ trách |
| Đơn hàng đã ở trạng thái không cho phép đặt lại | Hành động không hợp lệ với trạng thái hiện tại | Đề nghị tải lại trạng thái hoặc chọn hành động khác |
| Cơ sở dữ liệu tạm thời không khả dụng | Hệ thống không thể hoàn tất thao tác kỹ thuật | Ghi log, thử lại theo chính sách và trả lỗi hệ thống phù hợp |

Ba trường hợp đầu tiên là các kết quả nghiệp vụ mà hệ thống có thể dự đoán trong hoạt động bình thường. Cơ sở dữ liệu không khả dụng là lỗi kỹ thuật: nó không nói rằng yêu cầu đặt hàng vi phạm chính sách của cửa hàng. Nếu gom tất cả vào một giá trị `false`, `null` hoặc một thông báo chung như “Có lỗi xảy ra”, tầng gọi sẽ không biết nên xử lý thế nào.

Một kết quả có ý nghĩa thường trả lời được ba câu hỏi: hành động có được chấp nhận không, nếu không thì vì lý do nghiệp vụ nào, và có dữ liệu nào an toàn, hữu ích để người gọi tiếp tục xử lý không.

## Phân biệt từ chối nghiệp vụ với lỗi kỹ thuật

**Từ chối nghiệp vụ** là kết quả có thể dự đoán theo quy tắc hoặc trạng thái của bài toán. Ví dụ: không đủ tồn kho, khách hàng không đủ điều kiện hưởng ưu đãi, hoặc đơn hàng đã giao nên không thể đổi địa chỉ. Người gọi thường có thể đưa ra một hành động tiếp theo dựa trên kết quả đó.

**Lỗi kỹ thuật** cho biết một thao tác cần thiết không thể hoàn tất vì môi trường hoặc hạ tầng. Ví dụ: mất kết nối cơ sở dữ liệu, timeout khi gọi dịch vụ thanh toán, lỗi giải mã dữ liệu hoặc cấu hình sai. Những lỗi này thường cần được ghi nhận, giám sát, thử lại có giới hạn hoặc chuyển thành phản hồi lỗi hệ thống.

**Lỗi lập trình hoặc vi phạm bất biến nội bộ** là trường hợp mã được gọi sai cách hoặc trạng thái nội bộ không thể xảy ra theo thiết kế. Ví dụ, một hàm yêu cầu đơn hàng đã có khách hàng nhưng lại nhận `null`. Không nên âm thầm chuyển lỗi như vậy thành “đặt hàng không thành công” vì điều đó che khuất lỗi cần được sửa.

Ranh giới giữa ngoại lệ và kết quả tường minh tùy ngữ cảnh. Một quy tắc từ chối thường gặp trong hoạt động bình thường nên được cân nhắc biểu diễn thành kết quả nghiệp vụ. Một lỗi bất ngờ hoặc điều kiện khiến chương trình không thể tiếp tục thường phù hợp với exception. Không nên chọn cách biểu diễn chỉ dựa trên việc một tình huống có tên “error” hay “exception”.

## Dùng kiểu dữ liệu để biểu diễn kết quả rõ ràng

Trong Java, một cách đơn giản là dùng `enum` cho mã từ chối và một kiểu kết quả chứa trạng thái cùng dữ liệu liên quan:

```java
public enum PlaceOrderErrorCode {
    PRODUCT_UNAVAILABLE,
    CREDIT_LIMIT_EXCEEDED,
    ORDER_STATE_NOT_ALLOWED
}
```

```java
public record PlaceOrderError(
        PlaceOrderErrorCode code,
        Map<String, String> details) {

    public PlaceOrderError {
        Objects.requireNonNull(code, "code");
        details = Map.copyOf(details);
    }
}
```

```java
public sealed interface PlaceOrderResult
        permits PlaceOrderResult.Accepted, PlaceOrderResult.Rejected {

    record Accepted(UUID orderId, Money total)
            implements PlaceOrderResult {}

    record Rejected(PlaceOrderError error)
            implements PlaceOrderResult {}
}
```

`Accepted` biểu diễn kết quả thành công với dữ liệu mà bước tiếp theo cần dùng. `Rejected` biểu diễn một lý do nghiệp vụ có cấu trúc. `sealed interface` giới hạn các dạng kết quả được phép, giúp người đọc biết một ca sử dụng có những nhánh chính nào. `record` phù hợp với dữ liệu kết quả bất biến và có sẵn constructor, accessor, `equals` cùng `hashCode`.

`details` có thể chứa các giá trị như mã sản phẩm, số lượng được yêu cầu hoặc số lượng có thể đáp ứng. Chỉ đưa vào đây dữ liệu cần thiết cho việc xử lý; không đưa thông tin nhạy cảm hoặc thông tin nội bộ của hạ tầng ra kết quả công khai. Với miền nghiệp vụ lớn, các kiểu lỗi riêng như `ProductUnavailable` hoặc `CreditLimitExceeded` có thể an toàn kiểu dữ liệu hơn một map. Chọn mức chi tiết phù hợp với số loại kết quả và nhu cầu của người gọi.

## Tạo kết quả từ quy tắc nghiệp vụ

Giả sử chính sách đặt hàng kiểm tra tồn kho và hạn mức tín dụng trước khi xác nhận đơn. Có thể mô hình hóa quyết định như sau:

```java
public sealed interface PlaceOrderDecision
        permits PlaceOrderDecision.Ready, PlaceOrderDecision.Rejected {

    record Ready(Order order) implements PlaceOrderDecision {}
    record Rejected(PlaceOrderError error) implements PlaceOrderDecision {}
}
```

```java
public class OrderPolicy {
    public PlaceOrderDecision evaluate(
            Customer customer,
            Cart cart,
            Inventory inventory) {

        if (!customer.canPlaceOrder()) {
            return new PlaceOrderDecision.Rejected(
                new PlaceOrderError(
                    PlaceOrderErrorCode.CREDIT_LIMIT_EXCEEDED,
                    Map.of("customerId", customer.id().toString())
                )
            );
        }

        for (CartLine line : cart.lines()) {
            int available = inventory.availableQuantity(line.productId());
            if (available < line.quantity()) {
                return new PlaceOrderDecision.Rejected(
                    new PlaceOrderError(
                        PlaceOrderErrorCode.PRODUCT_UNAVAILABLE,
                        Map.of(
                            "productId", line.productId().toString(),
                            "requested", Integer.toString(line.quantity()),
                            "available", Integer.toString(available)
                        )
                    )
                );
            }
        }

        Order order = Order.create(customer, cart.lines());
        return new PlaceOrderDecision.Ready(order);
    }
}
```

Đây là ví dụ minh họa cho cách trả về quyết định nghiệp vụ; trong hệ thống thực tế, việc kiểm tra và giữ chỗ tồn kho cần được thiết kế cùng cơ chế giao dịch hoặc khóa phù hợp để tránh hai yêu cầu đồng thời cùng sử dụng một lượng hàng. Một lần đọc số lượng tồn kho đơn thuần không bảo đảm hàng vẫn còn khi đơn được lưu.

Điểm quan trọng trong ví dụ là phương thức không trả `null` khi từ chối và không buộc tầng nghiệp vụ biết mã HTTP. Người gọi nhận một giá trị có cấu trúc, có thể phân biệt rõ `Ready` và `Rejected`. Nếu cần nhiều loại dữ liệu kết quả hơn, có thể mở rộng sealed hierarchy bằng những subtype có tên diễn đạt đúng ý nghĩa.

## Tầng ứng dụng điều phối kết quả

Tầng nghiệp vụ quyết định theo quy tắc của bài toán; tầng ứng dụng điều phối việc tải dữ liệu, gọi quyết định, lưu kết quả và phát sinh tác động tiếp theo. Ví dụ:

```java
@Service
class PlaceOrderService {
    private final CustomerRepository customers;
    private final CartRepository carts;
    private final InventoryRepository inventory;
    private final OrderPolicy orderPolicy;
    private final OrderRepository orders;

    PlaceOrderService(
            CustomerRepository customers,
            CartRepository carts,
            InventoryRepository inventory,
            OrderPolicy orderPolicy,
            OrderRepository orders) {
        this.customers = customers;
        this.carts = carts;
        this.inventory = inventory;
        this.orderPolicy = orderPolicy;
        this.orders = orders;
    }

    @Transactional
    public PlaceOrderResult place(PlaceOrderCommand command) {
        Customer customer = customers.getById(command.customerId());
        Cart cart = carts.getById(command.cartId());
        Inventory snapshot = inventory.loadFor(cart.productIds());

        PlaceOrderDecision decision = orderPolicy.evaluate(customer, cart, snapshot);
        if (decision instanceof PlaceOrderDecision.Ready ready) {
            Order order = ready.order();
            orders.save(order);
            return new PlaceOrderResult.Accepted(order.id(), order.total());
        }
        PlaceOrderError error = ((PlaceOrderDecision.Rejected) decision).error();
        return new PlaceOrderResult.Rejected(error);
    }
}
```

Ở đây có hai kiểu kết quả vì chúng phục vụ hai ranh giới khác nhau. `PlaceOrderDecision` là quyết định nội bộ của nghiệp vụ: nhánh thành công mang aggregate `Order` đã được tạo và kiểm tra. `PlaceOrderResult` là kết quả của ca sử dụng: nó chỉ mang dữ liệu mà tầng gọi cần, như mã đơn hàng, tổng tiền hoặc lỗi có cấu trúc. Application service lưu aggregate trong nhánh `Ready`, sau đó chuyển thành kết quả ứng dụng. Nhánh từ chối không thực hiện thao tác lưu.

Giao dịch cần được cân nhắc theo toàn bộ ca sử dụng. Nếu việc kiểm tra tồn kho và trừ hoặc giữ chỗ hàng phải nguyên tử, các thao tác liên quan cần được phối hợp bằng cơ chế phù hợp ở application/infrastructure. Việc chỉ gắn `@Transactional` không tự giải quyết mọi vấn đề đồng thời, nhất là khi tồn kho nằm ở dịch vụ hoặc hệ thống khác.

## Ánh xạ kết quả sang giao diện ở biên hệ thống

Domain không nên trả `ResponseEntity`, `HttpStatus`, `ProblemDetail` hoặc thông điệp được viết riêng cho một màn hình. Đây là chi tiết của giao diện. Controller hoặc adapter HTTP có thể chuyển kết quả ứng dụng thành hợp đồng API:

```java
@PostMapping("/orders")
ResponseEntity<?> place(@Valid @RequestBody PlaceOrderRequest request) {
    PlaceOrderResult result = placeOrder.place(
        new PlaceOrderCommand(request.customerId(), request.cartId())
    );

    if (result instanceof PlaceOrderResult.Accepted accepted) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new PlaceOrderResponse(accepted.orderId(), accepted.total()));
    }

    PlaceOrderError error = ((PlaceOrderResult.Rejected) result).error();
    return switch (error.code()) {
        case PRODUCT_UNAVAILABLE -> ResponseEntity.status(HttpStatus.CONFLICT)
            .body(ApiError.from("PRODUCT_UNAVAILABLE", error.details()));
        case CREDIT_LIMIT_EXCEEDED -> ResponseEntity.unprocessableEntity()
            .body(ApiError.from("CREDIT_LIMIT_EXCEEDED", error.details()));
        case ORDER_STATE_NOT_ALLOWED -> ResponseEntity.status(HttpStatus.CONFLICT)
            .body(ApiError.from("ORDER_STATE_NOT_ALLOWED", error.details()));
    };
}
```

Các mã HTTP ở đây chỉ là lựa chọn cho hợp đồng API minh họa. Một hệ thống có thể dùng `409 Conflict`, `422 Unprocessable Content` hoặc cách ánh xạ khác tùy ngữ nghĩa endpoint và quy ước API. Điều cần giữ là domain chỉ biểu diễn ý nghĩa nghiệp vụ; adapter quyết định cách truyền tải ý nghĩa đó.

Thông điệp hiển thị cho người dùng có thể được tạo ở giao diện dựa trên mã ổn định như `PRODUCT_UNAVAILABLE`, rồi dịch sang ngôn ngữ phù hợp. Không nên dùng trực tiếp `exception.getMessage()` hoặc chuỗi thông báo tùy tiện làm mã máy đọc được. Thông điệp có thể thay đổi theo ngôn ngữ hoặc cách trình bày; mã lỗi cần ổn định hơn để client và hệ thống giám sát có thể xử lý.

## Khi nào nên dùng kết quả tường minh, khi nào dùng exception?

| Tình huống | Cách biểu diễn thường phù hợp | Lý do |
|---|---|---|
| Hết hàng khi đặt đơn | Kết quả từ chối nghiệp vụ | Là khả năng bình thường mà người gọi có thể xử lý |
| Không đủ điều kiện hưởng ưu đãi | Kết quả nghiệp vụ hoặc giá trị không áp dụng | Không nhất thiết là lỗi hệ thống; có thể tiếp tục với giá thông thường nếu chính sách cho phép |
| Đơn hàng không thể hủy vì đã giao | Kết quả từ chối hoặc lỗi miền có kiểu rõ ràng | Cần diễn đạt trạng thái và lý do theo hợp đồng ca sử dụng |
| Cơ sở dữ liệu mất kết nối | Exception kỹ thuật | Ca sử dụng không thể hoàn tất thao tác cần thiết |
| Lỗi lập trình như truyền `null` vào tham số bắt buộc | Exception hoặc fail-fast | Đây là lỗi của mã gọi, không phải kết quả nghiệp vụ dành cho người dùng |
| Tài nguyên không tồn tại | Kết quả vắng mặt hoặc lỗi miền tùy ngữ nghĩa | Phụ thuộc việc “không có” là kết quả bình thường hay vi phạm tiền điều kiện |

Kết quả tường minh phù hợp khi người gọi cần xem xét các nhánh hợp lệ của quy trình. Exception phù hợp khi luồng hiện tại không thể tiếp tục theo cách thông thường hoặc khi một lỗi bất ngờ cần được xử lý ở ranh giới thích hợp. Cả checked exception và unchecked exception đều có thể dùng trong Java; quyết định nên dựa trên hợp đồng và cách xử lý, không dựa vào quy tắc cứng rằng mọi lỗi nghiệp vụ phải là checked exception.

Không nên bắt mọi exception rồi trả về một `Rejected` chung. Làm vậy sẽ che giấu sự cố cơ sở dữ liệu, lỗi lập trình và các tình trạng cần cảnh báo vận hành. Tương tự, không nên dùng exception cho mọi nhánh điều kiện bình thường nếu việc đó khiến luồng nghiệp vụ khó đọc và khó kiểm thử.

## Thiết kế mã lỗi và dữ liệu chi tiết

Một mã lỗi tốt có tên ổn định, diễn đạt đúng ý nghĩa nghiệp vụ và không phụ thuộc vào cách hiển thị. Ví dụ `PRODUCT_UNAVAILABLE` mô tả một điều kiện có thể hiểu được; `ERROR_17` hoặc `SomethingWentWrong` không cho biết người gọi nên làm gì.

Khi thiết kế chi tiết đi kèm, hãy cân nhắc:

- Chỉ cung cấp dữ liệu cần thiết để người gọi hiểu hoặc khắc phục vấn đề.
- Dùng mã định danh và giá trị có cấu trúc thay vì ghép tất cả thành một chuỗi tự do.
- Không tiết lộ dữ liệu cá nhân, hạn mức nội bộ, thông tin bảo mật hoặc chi tiết hạ tầng.
- Không buộc domain biết ngôn ngữ hiển thị. Việc dịch và định dạng thuộc lớp giao diện.
- Ghi log kỹ thuật ở nơi phù hợp, nhưng tránh ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log.

Không nhất thiết phải tạo một hệ thống mã lỗi lớn ngay từ đầu. Với một miền nhỏ, enum và một record lỗi có thể đủ. Khi nhiều ứng dụng hoặc đối tác tích hợp cần hợp đồng ổn định, hãy quản lý mã lỗi và ý nghĩa của chúng như một phần của API/domain contract có kiểm soát phiên bản.

## Kiểm thử các nhánh kết quả

Kiểm thử nên xác nhận cả ý nghĩa kết quả lẫn tác động phụ:

| Trường hợp | Điều cần xác minh |
|---|---|
| Đủ điều kiện và còn hàng | Trả kết quả chấp nhận với mã đơn và tổng tiền đúng |
| Không đủ tồn kho | Trả `PRODUCT_UNAVAILABLE` với dữ liệu cần thiết; không lưu đơn |
| Vượt hạn mức tín dụng | Trả `CREDIT_LIMIT_EXCEEDED`; không tạo đơn |
| Trạng thái không cho phép | Trả lý do đúng và giữ nguyên trạng thái hiện tại |
| Repository gặp lỗi kết nối | Exception kỹ thuật được truyền tới ranh giới xử lý; không biến thành từ chối nghiệp vụ |
| Mã lỗi được chuyển sang HTTP | Adapter trả đúng status và cấu trúc API theo hợp đồng |

Unit test cho policy hoặc domain có thể chạy không cần Spring hay cơ sở dữ liệu. Test application service xác minh việc lưu chỉ xảy ra ở nhánh được chấp nhận và lỗi kỹ thuật không bị nuốt. Test controller xác nhận kết quả domain được ánh xạ sang HTTP và DTO đúng. Với các thao tác tồn kho có cạnh tranh, cần integration test hoặc kiểm thử đồng thời phù hợp để xác nhận cơ chế giữ chỗ và giao dịch.

## Giữ mô hình kết quả vừa đủ

Biểu diễn rõ ràng giúp tầng gọi xử lý đúng từng tình huống, người dùng nhận được hướng dẫn hữu ích và hệ thống tránh trộn lỗi nghiệp vụ với sự cố kỹ thuật. Tuy vậy, mỗi subtype, enum và mã lỗi cũng là một phần hợp đồng cần duy trì. Đừng tạo một hierarchy phức tạp cho mọi hàm nhỏ; bắt đầu từ những nhánh thực sự ảnh hưởng đến quyết định của người gọi.

Trong kiến trúc phân tầng, domain hoặc business layer diễn đạt quy tắc và kết quả theo ngôn ngữ của bài toán. Application layer điều phối và quyết định cách tiếp tục; adapter giao diện chuyển kết quả thành HTTP, màn hình hoặc thông điệp tích hợp; infrastructure xử lý lỗi kỹ thuật từ cơ sở dữ liệu và dịch vụ ngoài. Khi mỗi tầng giữ đúng ý nghĩa của mình, mã nguồn dễ kiểm thử, dễ thay đổi và không để chi tiết truyền tải quyết định cách hiểu nghiệp vụ.
