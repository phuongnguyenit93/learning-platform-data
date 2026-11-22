# Thiết kế Model độc lập với giao diện và giao thức truyền tải

Trong MVC, Model đại diện cho dữ liệu và quy tắc nghiệp vụ mà ứng dụng cần bảo vệ. Một Model được thiết kế tốt có thể phục vụ nhiều cách tương tác: trang HTML, API JSON, ứng dụng di động, tác vụ chạy nền hoặc thông điệp từ một hệ thống khác. Khi giao diện thay đổi hoặc HTTP được thay bằng một giao thức khác, các quy tắc nghiệp vụ cốt lõi vẫn hoạt động như cũ.

Bài học này tập trung vào cách xác định ranh giới của Model, tách nó khỏi chi tiết trình bày và truyền tải, rồi kết nối các phần thông qua những hợp đồng dữ liệu rõ ràng. Ví dụ sử dụng Java để minh họa; các nguyên tắc có thể áp dụng với những ngôn ngữ và framework khác.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao Model không nên phụ thuộc vào HTML, JSON, HTTP hoặc framework giao diện.
- Phân biệt Domain Model, mô hình ca sử dụng, DTO, View Model và mô hình lưu trữ.
- Thiết kế dữ liệu đầu vào và đầu ra phù hợp với từng ranh giới.
- Đặt quy tắc nghiệp vụ ở nơi có thể bảo vệ chúng nhất quán.
- Tổ chức luồng từ Controller đến Model và quay lại mà không để Model biết chi tiết của request hoặc response.
- Kiểm thử quy tắc nghiệp vụ độc lập với web server và cơ sở dữ liệu.

## 2. “Độc lập” có nghĩa là gì?

Hãy hình dung một ứng dụng đặt hàng. Người dùng có thể tạo đơn qua biểu mẫu trên website, ứng dụng di động hoặc một API dành cho đối tác. Dù đầu vào đến từ đâu, một số quy tắc vẫn phải luôn đúng:

- Đơn hàng phải có ít nhất một dòng hàng trước khi được xác nhận.
- Số lượng của mỗi dòng hàng phải lớn hơn 0.
- Tổng tiền được tính từ giá và số lượng hợp lệ.
- Đơn đã xác nhận không được tùy ý thêm dòng hàng.
- Giá dùng cho đơn hàng phải là giá mà hệ thống tin cậy tại thời điểm tạo đơn.

Đây là quy tắc của nghiệp vụ đặt hàng. Chúng không thuộc riêng website, JSON hay HTTP. Vì vậy, chúng cần được biểu diễn trong Model.

Một Model độc lập có những đặc điểm sau:

1. **Biểu đạt ngôn ngữ nghiệp vụ.** Tên lớp, thuộc tính và hành vi phản ánh khái niệm như Order, OrderLine, Money hoặc confirm, thay vì HttpRequest, JsonField hay FormSubmit.
2. **Bảo vệ trạng thái hợp lệ.** Đối tượng không cho phép các thao tác làm vi phạm bất biến nghiệp vụ.
3. **Không biết cách dữ liệu được truyền đến.** Model không đọc request, cookie, session, header hoặc tham số URL.
4. **Không quyết định cách dữ liệu được trình bày.** Model không tạo HTML, thông báo giao diện, cấu trúc JSON hay mã trạng thái HTTP.
5. **Có thể được gọi từ nhiều điểm vào.** Controller web, command-line interface, consumer của message queue hoặc tác vụ định kỳ đều có thể sử dụng cùng một ca sử dụng.

Độc lập không có nghĩa là Model không được dùng thư viện Java chuẩn hoặc không được kết nối với bất kỳ thành phần nào. Điều quan trọng là các quy tắc nghiệp vụ không bị ràng buộc vào chi tiết của một phương thức giao tiếp hay một framework cụ thể.

### Model trong MVC và Domain Model

Từ “Model” trong MVC thường được dùng theo nghĩa rộng: phần đại diện cho trạng thái và hành vi của ứng dụng. Trong một ứng dụng lớn, phần này có thể bao gồm Domain Model, các ca sử dụng, cổng truy cập dữ liệu và các mô hình đọc dữ liệu.

Domain Model là phần mô tả khái niệm và quy tắc cốt lõi của miền nghiệp vụ. Ca sử dụng (application use case) điều phối một hành động cụ thể, chẳng hạn tạo đơn hàng hoặc hủy đơn hàng. Hai phần này phối hợp với nhau nhưng có trách nhiệm khác nhau:

- Domain Model quyết định một thao tác có hợp lệ theo quy tắc nghiệp vụ hay không.
- Ca sử dụng quyết định cần gọi những thành phần nào, theo thứ tự nào, để hoàn thành một mục tiêu của người dùng.
- Controller tiếp nhận tương tác và chuyển dữ liệu từ giao thức bên ngoài thành lời gọi ca sử dụng.

Không nên xem Model chỉ là một tập hợp các lớp có getter và setter. Nếu mọi quy tắc đều nằm trong Controller hoặc service thao tác dữ liệu đơn thuần, các đối tượng nghiệp vụ sẽ khó tự bảo vệ trạng thái của chúng.

## 3. Phân chia các loại mô hình và trách nhiệm

Một hệ thống thường có nhiều dạng dữ liệu cùng mô tả một nghiệp vụ. Chúng có thể chứa một số trường giống nhau, nhưng phục vụ những mục đích khác nhau.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Domain Model | Biểu diễn khái niệm, trạng thái và bất biến nghiệp vụ | Order, OrderLine, Money |
| Application Model / Use Case | Điều phối một mục tiêu nghiệp vụ qua các thành phần | PlaceOrder, CancelOrder |
| Request DTO / Form Model | Nhận dữ liệu theo hợp đồng của giao diện hoặc API | PlaceOrderRequest |
| Response DTO | Trả dữ liệu theo hợp đồng của API | PlaceOrderResponse |
| View Model | Chuẩn bị dữ liệu thuận tiện cho một màn hình | OrderDetailViewModel |
| Persistence Model | Phản ánh cách dữ liệu được lưu trong cơ sở dữ liệu | OrderEntity, các cột và quan hệ ORM |

### Domain Model

Domain Model chứa các quy tắc có ý nghĩa bất kể ứng dụng được truy cập qua giao diện nào. Ví dụ, phương thức Order.confirm() có thể kiểm tra đơn hàng có dòng hàng hay chưa và chỉ cho phép chuyển trạng thái từ DRAFT sang CONFIRMED.

Domain Model nên cung cấp các hành vi có ý nghĩa thay vì để bên ngoài tự sửa từng trường. Điều này giúp mọi nơi sử dụng đối tượng đều đi qua cùng một bộ quy tắc.

### Application Model và ca sử dụng

Ca sử dụng phối hợp công việc ở cấp ứng dụng. Khi đặt hàng, nó có thể:

1. Nhận yêu cầu đặt hàng đã được chuẩn hóa.
2. Tra cứu giá sản phẩm từ nguồn dữ liệu đáng tin cậy.
3. Tạo Domain Model.
4. Yêu cầu Domain Model xác nhận đơn.
5. Lưu đơn qua một giao diện repository.
6. Trả về mã đơn hàng cho lớp gọi.

Ca sử dụng không nên biết request đến từ biểu mẫu HTML hay JSON. Nó nhận một đối tượng lệnh có cấu trúc ổn định và thực hiện công việc.

### DTO và View Model

DTO là hợp đồng dữ liệu ở ranh giới. Request DTO phản ánh dữ liệu mà client được phép gửi; Response DTO phản ánh dữ liệu mà API được phép trả. View Model phản ánh nhu cầu của một màn hình, có thể kết hợp hoặc định dạng dữ liệu từ nhiều đối tượng.

Một DTO có thể trùng một phần với Domain Model, nhưng không vì thế mà hai loại nên bị gộp làm một. Chúng có vòng đời và lý do thay đổi khác nhau. API có thể đổi tên trường để tương thích ngược trong khi khái niệm nghiệp vụ vẫn giữ nguyên.

### Persistence Model

Mô hình lưu trữ phản ánh cấu trúc bảng, khóa, chỉ mục và cách ORM ánh xạ dữ liệu. Nó có thể có trường kỹ thuật như created_at, row_version hoặc khóa ngoại. Các chi tiết này không nhất thiết là khái niệm của miền nghiệp vụ.

Với ứng dụng CRUD nhỏ, dùng cùng một lớp cho Domain Model và Persistence Model đôi khi là lựa chọn thực dụng. Tuy nhiên, nếu lớp đó bắt đầu chứa nhiều annotation ORM, quy tắc serialization hoặc trường dành riêng cho giao diện, việc tách mô hình sẽ giúp giảm phụ thuộc và tránh rò rỉ dữ liệu.

## 4. Luồng tương tác qua các ranh giới

Một luồng MVC điển hình có thể được mô tả như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as Giao diện / Client
    participant Controller as Controller
    participant UseCase as Ca sử dụng
    participant Model as Domain Model
    participant Repo as Repository
    participant DB as Cơ sở dữ liệu

    User->>Client: Gửi yêu cầu đặt hàng
    Client->>Controller: HTTP request / form
    Controller->>Controller: Kiểm tra cấu trúc và ánh xạ DTO
    Controller->>UseCase: PlaceOrderCommand
    UseCase->>Repo: Tra cứu dữ liệu cần thiết
    Repo->>DB: Đọc dữ liệu
    DB-->>Repo: Kết quả
    Repo-->>UseCase: Dữ liệu nghiệp vụ
    UseCase->>Model: Tạo và xác nhận Order
    Model-->>UseCase: Trạng thái hợp lệ hoặc lỗi nghiệp vụ
    UseCase->>Repo: Lưu Order
    Repo->>DB: Ghi dữ liệu
    DB-->>Repo: Kết quả lưu
    Repo-->>UseCase: Hoàn tất
    UseCase-->>Controller: Kết quả ca sử dụng
    Controller->>Controller: Ánh xạ sang Response DTO / View Model
    Controller-->>Client: HTTP response / view
~~~

Điểm quan trọng nằm ở hai lần chuyển đổi:

- Ở đầu vào, Controller chuyển dữ liệu của giao thức thành một lệnh mà ca sử dụng hiểu được.
- Ở đầu ra, Controller hoặc lớp trình bày chuyển kết quả của ca sử dụng thành dữ liệu phù hợp với giao diện.

Model không cần biết hai lần chuyển đổi đó diễn ra như thế nào.

Trong một ứng dụng đơn giản, Controller có thể trực tiếp thực hiện việc ánh xạ. Khi số lượng quy tắc chuyển đổi tăng lên, có thể tách mapper hoặc presenter riêng. Hãy thêm lớp khi nó giải quyết một trách nhiệm thực tế, tránh tạo thêm tầng chỉ để chuyển tiếp lời gọi.

## 5. Ví dụ: Model của nghiệp vụ đặt hàng

Giả sử ứng dụng cho phép khách hàng đặt các sản phẩm. Client gửi mã sản phẩm và số lượng. Giá sản phẩm được lấy từ danh mục do hệ thống quản lý; client không được tự quyết định giá hoặc tổng tiền.

### 5.1. Tạo kiểu giá trị cho tiền

Dùng một kiểu Money giúp tránh thao tác số tiền như số thập phân tùy ý. Kiểu này giữ số tiền cùng loại tiền tệ và kiểm tra các phép toán hợp lệ.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency
        );
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other is required");

        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
~~~

Money không biết giá trị được đọc từ JSON, nhập trong biểu mẫu hay lấy từ cơ sở dữ liệu. Nó chỉ bảo vệ quy tắc của phép toán tiền tệ.

Ví dụ này chưa quy định chính sách làm tròn vì chính sách có thể phụ thuộc vào loại nghiệp vụ, thuế và loại tiền. Hệ thống thực tế cần xác định rõ số chữ số thập phân và thời điểm làm tròn, rồi thực hiện nhất quán ở miền nghiệp vụ tương ứng.

### 5.2. Biểu diễn một dòng hàng

~~~java
import java.util.Objects;

public record OrderLine(String sku, int quantity, Money unitPrice) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        Objects.requireNonNull(unitPrice, "unitPrice is required");
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
~~~

OrderLine đảm bảo một dòng hàng không thể được tạo với mã sản phẩm rỗng hoặc số lượng không hợp lệ. Khi tính thành tiền, nó dùng phép nhân đã được định nghĩa trong Money.

### 5.3. Bảo vệ trạng thái của đơn hàng

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class Order {
    private final UUID id;
    private final UUID customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.customerId =
            Objects.requireNonNull(customerId, "customerId is required");
    }

    public void addLine(OrderLine line) {
        ensureDraft();
        lines.add(Objects.requireNonNull(line, "line is required"));
    }

    public Money total() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order has no total"
            );
        }

        return lines.stream()
            .map(OrderLine::subtotal)
            .reduce(Money::add)
            .orElseThrow();
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An order must contain at least one line"
            );
        }

        total(); // Kiểm tra các dòng hàng có cùng loại tiền tệ.
        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be changed"
            );
        }
    }

    public UUID id() {
        return id;
    }

    public UUID customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
~~~

Đơn hàng tự bảo vệ các quy tắc quan trọng: chỉ đơn nháp mới được thay đổi, đơn phải có ít nhất một dòng trước khi xác nhận, và các dòng hàng phải cộng được với nhau. Danh sách dòng hàng được trả về dưới dạng bản sao không thể sửa trực tiếp, tránh để lớp gọi bỏ qua addLine().

Đây là một ví dụ nhỏ để minh họa ranh giới. Hệ thống thực tế có thể cần thêm trạng thái thanh toán, tồn kho, hủy đơn, hoàn tiền, địa chỉ giao hàng và quy tắc chuyển trạng thái tương ứng.

### 5.4. Ca sử dụng điều phối việc đặt hàng

Đầu vào của ca sử dụng là một lệnh độc lập với HTTP:

~~~java
import java.util.List;
import java.util.UUID;

public record PlaceOrderCommand(
    UUID customerId,
    List<ItemRequest> items
) {
    public record ItemRequest(String sku, int quantity) {}
}
~~~

Các phụ thuộc bên ngoài được biểu diễn qua interface. Ví dụ này dùng ProductCatalog để lấy giá đáng tin cậy và OrderRepository để lưu đơn hàng:

~~~java
public interface ProductCatalog {
    ProductPrice findPrice(String sku);
}

public record ProductPrice(String sku, Money price) {}

public interface OrderRepository {
    void save(Order order);
}
~~~

Ca sử dụng phối hợp các thành phần:

~~~java
import java.util.UUID;

public final class PlaceOrder {
    private final ProductCatalog catalog;
    private final OrderRepository orders;

    public PlaceOrder(ProductCatalog catalog, OrderRepository orders) {
        this.catalog = catalog;
        this.orders = orders;
    }

    public UUID handle(PlaceOrderCommand command) {
        if (command == null || command.items() == null
                || command.items().isEmpty()) {
            throw new IllegalArgumentException(
                "At least one item is required"
            );
        }

        Order order = new Order(
            UUID.randomUUID(),
            command.customerId()
        );

        for (PlaceOrderCommand.ItemRequest item : command.items()) {
            ProductPrice product = catalog.findPrice(item.sku());

            order.addLine(new OrderLine(
                product.sku(),
                item.quantity(),
                product.price()
            ));
        }

        order.confirm();
        orders.save(order);

        return order.id();
    }
}
~~~

Ca sử dụng không nhận HttpServletRequest, không trả ResponseEntity và không cần biết dữ liệu đến từ JSON hay form. Nó chỉ làm việc với lệnh nghiệp vụ, Model và các interface mà nó cần.

Trong ứng dụng thực tế, cần xử lý rõ các trường hợp sản phẩm không tồn tại, sản phẩm ngừng bán, giá thay đổi, khách hàng không có quyền đặt hàng và lỗi lưu dữ liệu. Giao dịch lưu đơn, giữ tồn kho và thanh toán cũng cần được thiết kế theo chính sách nhất quán của hệ thống. Đoạn mã trên tập trung vào ranh giới Model nên chưa triển khai toàn bộ các chính sách đó.

### 5.5. Controller chuyển đổi hợp đồng HTTP

Một request DTO có thể chứa các ràng buộc về cấu trúc đầu vào:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record PlaceOrderRequest(
    @NotEmpty List<@Valid LineRequest> items
) {
    public record LineRequest(
        @NotBlank String sku,
        @Positive int quantity
    ) {}
}
~~~

Controller nhận request, lấy danh tính khách hàng từ ngữ cảnh xác thực và chuyển thành lệnh:

~~~java
import java.util.UUID;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrder placeOrder;

    public OrderController(PlaceOrder placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> create(
            @AuthenticationPrincipal AppPrincipal principal,
            @Valid @RequestBody PlaceOrderRequest request) {

        PlaceOrderCommand command = new PlaceOrderCommand(
            principal.customerId(),
            request.items().stream()
                .map(item -> new PlaceOrderCommand.ItemRequest(
                    item.sku(),
                    item.quantity()
                ))
                .toList()
        );

        UUID orderId = placeOrder.handle(command);

        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(new PlaceOrderResponse(orderId));
    }
}
~~~

Response DTO chỉ công bố dữ liệu mà API cần:

~~~java
import java.util.UUID;

public record PlaceOrderResponse(UUID orderId) {}
~~~

Đây là mã minh họa theo phong cách Spring MVC; các kiểu RestController, ResponseEntity và annotation HTTP thuộc lớp giao tiếp. Chúng không xuất hiện trong Order, OrderLine hoặc Money.

Một điểm bảo mật quan trọng là customerId được lấy từ principal đã xác thực. Nếu client tự gửi customerId trong body, người dùng có thể thử đặt hàng thay cho khách hàng khác. Tương tự, giá và tổng tiền được tra cứu hoặc tính ở phía server, không tin giá trị do client gửi lên.

## 6. Thiết kế hợp đồng dữ liệu ở ranh giới

Hợp đồng dữ liệu là thỏa thuận giữa hai phần của hệ thống về cấu trúc và ý nghĩa dữ liệu được trao đổi. Mỗi ranh giới nên có hợp đồng phục vụ đúng mục đích của nó.

### 6.1. Request DTO mô tả ý định của client

Request nên chứa thông tin client được phép cung cấp để yêu cầu một hành động. Trong ví dụ đặt hàng, sku và quantity là đủ để mô tả các mặt hàng muốn mua.

Không nên cho client gửi trực tiếp những trường như:

- unitPrice hoặc totalAmount nếu giá do hệ thống quản lý.
- status nếu trạng thái phải được quyết định bởi quy trình nghiệp vụ.
- isAdmin, role hoặc các cờ quyền hạn.
- createdAt, approvedBy hoặc các trường kiểm soát nội bộ.

Chỉ nhận các trường cần thiết giúp giảm nguy cơ mass assignment, tức client gửi thêm trường để cố sửa trạng thái mà họ không được phép điều khiển.

### 6.2. Phân biệt kiểm tra cấu trúc và kiểm tra nghiệp vụ

Có nhiều loại kiểm tra, nên đặt chúng tại nơi phù hợp:

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Cấu trúc đầu vào | Trường bắt buộc, chuỗi không rỗng, kiểu dữ liệu đúng | Request DTO / Controller |
| Quy tắc của đối tượng | Số lượng phải dương, đơn đã xác nhận không được sửa | Domain Model |
| Quy tắc của ca sử dụng | Sản phẩm còn được bán, khách hàng được phép đặt | Application Use Case và các chính sách nghiệp vụ |
| Ràng buộc lưu trữ | Khóa duy nhất, khóa ngoại, giao dịch | Persistence adapter và cơ sở dữ liệu |

Không nên dựa hoàn toàn vào validation của biểu mẫu. Một ca sử dụng có thể được gọi từ API khác hoặc tác vụ nền, nên quy tắc nghiệp vụ phải được bảo vệ ở phía Model hoặc ca sử dụng ngay cả khi Controller đã kiểm tra dữ liệu.

### 6.3. Response DTO và View Model phục vụ người nhận

Response API nên có cấu trúc ổn định và chỉ chứa trường cần công bố. View Model có thể chứa dữ liệu đã định dạng cho một màn hình, chẳng hạn tên hiển thị, nhãn trạng thái, chuỗi tiền tệ hoặc các thao tác mà người dùng được phép thực hiện.

Không nên trả thẳng Domain Model hoặc đối tượng ORM ra ngoài. Làm như vậy khiến thay đổi nội bộ có thể vô tình làm thay đổi API, làm lộ trường nhạy cảm hoặc tạo vòng tham chiếu khi serialization.

### 6.4. Ánh xạ rõ ràng tại ranh giới

Mapper chuyển đổi một kiểu dữ liệu sang kiểu khác. Việc ánh xạ rõ ràng có một số lợi ích:

- Dễ thấy dữ liệu nào được phép đi vào nghiệp vụ.
- Dễ kiểm soát trường nào được công bố ra bên ngoài.
- Có thể thay đổi tên hoặc cấu trúc API mà không đổi Domain Model.
- Có thể kiểm thử chuyển đổi mà không cần chạy toàn bộ ứng dụng.

Không nhất thiết phải tạo mapper cho mọi lớp. Nếu phép ánh xạ chỉ có một vài dòng và nằm rõ ràng trong Controller, giữ nó tại đó có thể đơn giản hơn. Khi mapping được dùng ở nhiều nơi hoặc có logic đáng kể, hãy tách nó thành thành phần riêng.

## 7. Xử lý lỗi mà không đưa HTTP vào Model

Model cần biểu đạt được điều gì sai theo ngôn ngữ nghiệp vụ. Ví dụ:

- Đơn hàng rỗng không thể được xác nhận.
- Đơn đã xác nhận không thể thêm dòng hàng.
- Hai khoản tiền khác loại tiền tệ không thể cộng trực tiếp.
- Sản phẩm không còn được phép đặt.

Các lỗi này có thể được biểu diễn bằng exception nghiệp vụ, kiểu kết quả hoặc một cơ chế lỗi nhất quán. Điều quan trọng là chúng không chứa mã HTTP hoặc phụ thuộc vào lớp web.

Controller hoặc lớp chuyển đổi lỗi ở ranh giới sẽ ánh xạ lỗi sang phản hồi thích hợp. Ví dụ minh họa:

| Tình huống | Phản hồi HTTP thường dùng |
|---|---|
| Request sai cấu trúc hoặc thiếu trường bắt buộc | 400 Bad Request |
| Dữ liệu đúng cấu trúc nhưng vi phạm quy tắc nghiệp vụ | 422 Unprocessable Content hoặc 400 Bad Request, theo quy ước API |
| Tài nguyên không tồn tại | 404 Not Found |
| Trạng thái hiện tại xung đột với thao tác | 409 Conflict |
| Lỗi ngoài dự kiến | 500 Internal Server Error |

Một hệ thống cần thống nhất cách phân loại lỗi trong toàn API. Không nên để Domain Model tự quyết định rằng một lỗi phải trở thành 409 hay 422, vì cùng một nghiệp vụ có thể được gọi qua giao diện không dùng HTTP.

Thông báo kỹ thuật cũng cần được xử lý cẩn thận. Client chỉ nên nhận thông tin đủ để hiểu và sửa yêu cầu; stack trace, câu lệnh SQL, token, khóa bí mật và chi tiết nội bộ không được đưa vào response công khai.

## 8. Bảo mật tại ranh giới Model

Thiết kế Model độc lập vẫn phải tính đến bảo mật. Controller là một ranh giới tiếp nhận dữ liệu không đáng tin cậy; dữ liệu cần được kiểm tra và danh tính phải được xác thực trước khi thực hiện thao tác.

Một số nguyên tắc thực hành:

1. **Không tin dữ liệu do client tự khai báo.** Giá, tổng tiền, trạng thái thanh toán và vai trò phải được xác định hoặc kiểm tra từ nguồn đáng tin cậy.
2. **Dùng allowlist cho đầu vào.** Chỉ ánh xạ các trường được phép từ request DTO sang command.
3. **Lấy danh tính từ ngữ cảnh xác thực.** Không cho phép người dùng tùy ý thay customerId hoặc ownerId trong request.
4. **Kiểm tra quyền ở đúng cấp.** Controller có thể chặn truy cập ở mức endpoint; ca sử dụng vẫn cần bảo đảm người gọi được phép thực hiện hành động trên tài nguyên cụ thể.
5. **Không trả đối tượng nội bộ trực tiếp.** Response DTO giúp giới hạn dữ liệu công khai.
6. **Không đưa bí mật vào Model hoặc DTO.** Mật khẩu, token và thông tin xác thực cần có chính sách xử lý riêng, không được ghi log hoặc trả ra ngoài tùy tiện.

Xác thực cho biết người gọi là ai; phân quyền quyết định họ có được thực hiện hành động hay không. Việc kiểm tra quyền không nên chỉ dựa vào một nút bị ẩn trên giao diện.

## 9. Giữ Model độc lập với cơ sở dữ liệu

Một cách phổ biến để giảm phụ thuộc là để ca sử dụng làm việc với interface repository, còn lớp triển khai repository chịu trách nhiệm truy cập cơ sở dữ liệu.

~~~java
import java.util.UUID;

public interface OrderRepository {
    void save(Order order);
    Order findById(UUID id);
}
~~~

Lớp triển khai có thể dùng JPA, JDBC hoặc một dịch vụ lưu trữ khác. Nếu cấu trúc ORM khác Domain Model, adapter sẽ chuyển đổi giữa Order và OrderEntity.

Cách tổ chức này giúp:

- Domain Model không cần biết tên bảng, cột hoặc annotation ORM.
- Có thể thay đổi cách lưu trữ mà ít ảnh hưởng đến quy tắc nghiệp vụ.
- Ca sử dụng có thể được kiểm thử bằng repository giả.
- Có thể đặt chính sách giao dịch ở tầng ứng dụng phù hợp.

Không phải dự án nào cũng cần tách hoàn toàn hai mô hình. Với ứng dụng CRUD đơn giản, dùng chung entity và domain object có thể giảm mã chuyển đổi. Hãy xem xét tách chúng khi quy tắc nghiệp vụ phức tạp, API có vòng đời riêng, dữ liệu lưu trữ thay đổi thường xuyên hoặc các annotation bắt đầu làm lớp nghiệp vụ phụ thuộc sâu vào framework.

## 10. Kiểm thử Model và các ranh giới

Khi Model độc lập với giao diện và giao thức, có thể kiểm tra quy tắc nghiệp vụ mà không cần khởi động web server hoặc cơ sở dữ liệu.

### 10.1. Unit test cho Domain Model

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.Currency;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderTest {
    private final Currency vnd = Currency.getInstance("VND");

    @Test
    void cannotConfirmAnEmptyOrder() {
        Order order = new Order(UUID.randomUUID(), UUID.randomUUID());

        assertThrows(IllegalStateException.class, order::confirm);
    }

    @Test
    void calculatesTotalFromItsLines() {
        Order order = new Order(UUID.randomUUID(), UUID.randomUUID());

        order.addLine(new OrderLine(
            "BOOK-01",
            2,
            new Money(new BigDecimal("50000"), vnd)
        ));

        assertEquals(
            new BigDecimal("100000"),
            order.total().amount()
        );
    }

    @Test
    void cannotChangeAnOrderAfterConfirmation() {
        Order order = new Order(UUID.randomUUID(), UUID.randomUUID());
        order.addLine(new OrderLine(
            "BOOK-01",
            1,
            new Money(new BigDecimal("50000"), vnd)
        ));
        order.confirm();

        assertThrows(
            IllegalStateException.class,
            () -> order.addLine(new OrderLine(
                "BOOK-02",
                1,
                new Money(new BigDecimal("30000"), vnd)
            ))
        );
    }
}
~~~

Các bài kiểm thử này tập trung vào hành vi và bất biến của Model. Chúng không cần biết đơn hàng được tạo từ form, API hay tác vụ nền.

### 10.2. Kiểm thử ca sử dụng bằng dependency giả

Có thể thay ProductCatalog và OrderRepository bằng các implementation giả trong bộ kiểm thử. Nhờ đó, kiểm tra được ca sử dụng:

- Tra cứu đúng sản phẩm.
- Dùng giá lấy từ catalog thay vì giá do client cung cấp.
- Tạo đơn với đúng khách hàng.
- Không lưu đơn khi quy tắc nghiệp vụ thất bại.
- Trả về mã đơn sau khi lưu thành công.

Với các thao tác có giao dịch hoặc tương tác hệ thống ngoài, cần bổ sung kiểm thử tích hợp để xác nhận hành vi thực tế của adapter và ranh giới giao dịch.

### 10.3. Kiểm thử Controller và hợp đồng

Kiểm thử Controller tập trung vào trách nhiệm giao tiếp:

- Request sai cấu trúc được từ chối.
- Trường không được phép không thể ghi đè dữ liệu nghiệp vụ.
- Danh tính được lấy từ principal.
- Request được ánh xạ thành command đúng.
- Kết quả ca sử dụng được ánh xạ thành response hoặc view đúng.
- Lỗi nghiệp vụ được chuyển thành phản hồi nhất quán.

Như vậy, mỗi lớp có nhóm kiểm thử phù hợp với trách nhiệm của nó. Một thay đổi trong JSON không nên buộc phải viết lại unit test cho Money hoặc Order.

## 11. Những cách thiết kế dễ gây phụ thuộc

### Đưa HTTP vào Domain Model

Ví dụ không phù hợp:

~~~java
public class Order {
    public ResponseEntity<?> confirm(HttpServletRequest request) {
        // Kiểm tra request, cập nhật đơn và tạo HTTP response.
        return ResponseEntity.ok().build();
    }
}
~~~

Lớp Order giờ phụ thuộc vào Servlet API và Spring MVC. Không thể dùng nó thuận tiện trong một tác vụ nền hoặc một giao diện khác. Hãy để Model cung cấp hành vi nghiệp vụ, rồi để Controller chuyển kết quả thành HTTP response.

### Để Controller chứa toàn bộ quy tắc nghiệp vụ

Nếu Controller tự tính giá, kiểm tra trạng thái và cập nhật nhiều bảng, quy tắc sẽ bị lặp lại khi có thêm endpoint hoặc điểm vào mới. Chuyển các quy tắc về Domain Model và ca sử dụng giúp chúng được áp dụng nhất quán.

### Trả thẳng entity hoặc Domain Model ra API

Điều này khiến cấu trúc nội bộ trở thành hợp đồng công khai. Một trường mới trong entity có thể vô tình bị lộ; một quan hệ ORM có thể tạo vòng tham chiếu; thay đổi tên trường có thể phá client. Dùng Response DTO hoặc View Model để kiểm soát dữ liệu đầu ra.

### Dùng một lớp cho mọi mục đích

Một lớp vừa là form, API request, domain object, ORM entity và response thường tích tụ nhiều annotation và quy tắc không liên quan. Khi các bên thay đổi vì những lý do khác nhau, việc sửa một chức năng có thể gây lỗi ở chức năng khác. Hãy tách theo ranh giới có ý nghĩa, không tách máy móc từng trường hợp nhỏ.

### Tạo quá nhiều tầng chuyển tiếp

Độc lập không đồng nghĩa phải có interface, mapper và service cho mọi lớp. Nếu một ứng dụng nhỏ chỉ có một điểm gọi và một phép ánh xạ đơn giản, thêm nhiều tầng có thể làm luồng khó theo dõi. Chỉ tách thành phần khi nó tạo ra một ranh giới, khả năng tái sử dụng hoặc điểm kiểm thử có giá trị.

## 12. Quy trình thiết kế thực tế

Khi bắt đầu một chức năng MVC mới, có thể đi theo trình tự sau:

1. **Mô tả mục tiêu người dùng.** Viết hành động bằng ngôn ngữ nghiệp vụ, ví dụ “khách hàng đặt một đơn hàng”.
2. **Xác định quy tắc phải luôn đúng.** Liệt kê điều kiện hợp lệ, trạng thái và các chuyển đổi được phép.
3. **Tạo Domain Model.** Chọn entity, value object và hành vi đủ để bảo vệ các quy tắc đó.
4. **Xác định ca sử dụng.** Mô tả trình tự phối hợp, dữ liệu cần tra cứu và kết quả cần trả.
5. **Định nghĩa hợp đồng đầu vào.** Tạo request DTO hoặc form model phù hợp với giao diện cụ thể.
6. **Ánh xạ vào command.** Chuyển dữ liệu giao tiếp thành kiểu dữ liệu mà ca sử dụng hiểu.
7. **Định nghĩa hợp đồng đầu ra.** Tạo Response DTO hoặc View Model và chỉ công bố dữ liệu cần thiết.
8. **Đặt chuyển đổi lỗi tại ranh giới.** Giữ lỗi nghiệp vụ trong Model; chuyển chúng thành thông báo và mã phản hồi ở lớp giao tiếp.
9. **Kiểm thử theo trách nhiệm.** Kiểm tra bất biến trong Domain Model, luồng điều phối trong ca sử dụng và hợp đồng ở Controller.
10. **Đánh giá phụ thuộc.** Đảm bảo quy tắc cốt lõi không phải import HTTP, UI, serialization hoặc ORM chỉ để hoạt động.

Trước khi hoàn thành, hãy tự hỏi:

- Nếu thay trang HTML bằng API JSON, có phải sửa Domain Model không?
- Nếu gọi cùng nghiệp vụ từ một tác vụ nền, có thể tái sử dụng ca sử dụng không?
- Client có thể tự gửi giá, trạng thái hoặc danh tính để ghi đè dữ liệu không?
- Có thể kiểm thử các quy tắc cốt lõi mà không chạy web server không?
- Response có vô tình để lộ cấu trúc lưu trữ hoặc trường nội bộ không?
- Có quy tắc nghiệp vụ nào đang bị lặp ở nhiều Controller không?

Nếu câu trả lời cho các câu hỏi này cho thấy Model đang phụ thuộc vào giao diện hoặc giao thức, hãy xem lại ranh giới và chuyển trách nhiệm về đúng lớp.

## 13. Kết luận

Model độc lập với giao diện và giao thức truyền tải giúp ứng dụng giữ được các quy tắc nghiệp vụ ổn định khi cách người dùng tương tác thay đổi. Domain Model bảo vệ trạng thái và hành vi; ca sử dụng điều phối công việc; DTO và View Model mô tả hợp đồng ở ranh giới; Controller chuyển đổi giữa giao thức bên ngoài và các hợp đồng nội bộ.

Thiết kế này tạo điều kiện tái sử dụng nghiệp vụ qua nhiều điểm vào, kiểm thử nhanh hơn và kiểm soát dữ liệu công khai tốt hơn. Mức độ tách lớp nên phù hợp với độ phức tạp thực tế của hệ thống, nhưng ranh giới trách nhiệm cần được làm rõ ngay từ đầu.

