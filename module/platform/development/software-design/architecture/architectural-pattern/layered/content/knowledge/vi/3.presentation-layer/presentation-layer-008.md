# Thay đổi kênh giao tiếp mà vẫn tái sử dụng cùng ca sử dụng

Một hệ thống có thể cung cấp cùng một hành động nghiệp vụ qua nhiều kênh: người dùng đặt hàng trên REST API, nhân viên thực hiện thao tác từ công cụ dòng lệnh, hoặc một hệ thống khác gửi yêu cầu qua message broker. Nếu mỗi kênh tự triển khai lại quy trình đặt hàng, các quy tắc và trình tự xử lý sẽ nhanh chóng khác nhau. Kiến trúc phân tầng giải quyết vấn đề này bằng cách để mỗi kênh có một adapter ở tầng trình bày, còn các adapter cùng gọi một hợp đồng ca sử dụng ở tầng ứng dụng.

Trong phạm vi module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này tập trung vào cách giữ tầng trình bày gắn với giao thức của từng kênh, đồng thời tái sử dụng phần điều phối và quy tắc nghiệp vụ ở các tầng bên trong. Mục tiêu không phải ép mọi kênh dùng chung một request hay một response, mà là bảo đảm chúng cùng yêu cầu hệ thống thực hiện một hành động nghiệp vụ có cùng ý nghĩa.

## 1. Kênh giao tiếp và ca sử dụng là hai vấn đề khác nhau

**Kênh giao tiếp** mô tả cách một tác nhân trao đổi với hệ thống. Ví dụ:

- REST API nhận HTTP request và trả HTTP response.
- Giao diện web gửi biểu mẫu và hiển thị kết quả.
- CLI đọc tham số hoặc dữ liệu từ stdin, sau đó in kết quả và trả mã thoát.
- Message consumer nhận thông điệp từ Kafka, RabbitMQ hoặc một broker khác.
- Tác vụ theo lịch gọi hệ thống để xử lý một nhóm công việc vào thời điểm định trước.

**Ca sử dụng (use case)** mô tả mục tiêu mà hệ thống cần hoàn thành, chẳng hạn đặt hàng, hủy đơn, đăng ký thành viên hoặc hoàn tiền. Ca sử dụng không nên phụ thuộc vào việc yêu cầu đến từ HTTP, terminal hay message broker. Nếu cùng một yêu cầu nghiệp vụ có thể được khởi tạo từ nhiều kênh, các kênh đó có thể gọi cùng một hợp đồng ứng dụng.

Ví dụ, thao tác đặt hàng qua REST và thao tác đặt hàng từ CLI đều cần kiểm tra dữ liệu sản phẩm, tạo đơn theo quy tắc nghiệp vụ và lưu đơn. Những bước này thuộc phần ứng dụng và nghiệp vụ. Khác biệt nằm ở cách nhận dữ liệu, xác thực người gọi, trình bày lỗi và trả kết quả.

Tách hai vấn đề này giúp thay đổi kênh giao tiếp ít ảnh hưởng đến quy trình nghiệp vụ. Khi bổ sung CLI cho một hệ thống vốn chỉ có REST API, ta có thể tạo adapter CLI và ánh xạ tham số thành lệnh của ca sử dụng hiện có. Khi chuyển từ REST sang một giao thức khác, phần nghiệp vụ vẫn giữ nguyên nếu ý nghĩa ca sử dụng không đổi.

## 2. Tổ chức tầng trình bày thành các adapter

Tầng trình bày nằm ở biên hệ thống. Mỗi adapter chịu trách nhiệm chuyển đổi giữa giao thức bên ngoài và hợp đồng mà tầng ứng dụng cung cấp.

| Adapter/kênh | Việc adapter thực hiện | Dữ liệu chuyển vào ứng dụng | Cách trả kết quả |
|---|---|---|---|
| REST controller | Đọc path, query, header và JSON body; kiểm tra cấu trúc request; ánh xạ lỗi sang HTTP. | Command hoặc input model của ca sử dụng. | HTTP status, header và JSON response. |
| CLI adapter | Đọc tham số, biến môi trường hoặc stdin; kiểm tra cú pháp và hiển thị trợ giúp. | Cùng command nếu hành động có cùng ý nghĩa. | Văn bản, JSON trên stdout/stderr và exit code. |
| Message consumer | Giải mã message, kiểm tra envelope và metadata, xử lý ack/retry theo cấu hình broker. | Command được tạo từ nội dung message. | Ack, retry hoặc chuyển message lỗi sang dead-letter queue theo chính sách vận hành. |
| Web adapter | Nhận dữ liệu biểu mẫu, quản lý trạng thái tương tác và điều hướng giao diện. | Command của ca sử dụng. | View model, trang HTML hoặc dữ liệu cho giao diện. |

Một adapter thường làm bốn việc:

1. Nhận dữ liệu theo định dạng của kênh.
2. Kiểm tra tính hợp lệ ở mức giao thức và cấu trúc.
3. Chuyển dữ liệu sang command/input model của ca sử dụng rồi gọi hợp đồng ứng dụng.
4. Chuyển kết quả hoặc lỗi của ứng dụng thành phản hồi phù hợp với kênh.

Adapter có thể chứa một ít logic chuyển đổi, nhưng không nên trở thành nơi thực hiện toàn bộ quy trình nghiệp vụ. Nếu REST controller và CLI cùng tự tải sản phẩm, tự tính giá và tự tạo đơn, hai luồng sẽ dần trở thành hai bản triển khai khác nhau của cùng ca sử dụng.

## 3. Định nghĩa một hợp đồng ứng dụng độc lập với giao thức

Giả sử hệ thống có ca sử dụng đặt hàng. Ta định nghĩa một hợp đồng mô tả đầu vào và kết quả theo ngôn ngữ của ứng dụng:

~~~java
public record PlaceOrderItem(
    UUID productId,
    int quantity
) {}

public record PlaceOrderCommand(
    UUID customerId,
    List<PlaceOrderItem> items,
    String idempotencyKey
) {
    public PlaceOrderCommand {
        items = List.copyOf(items);
    }
}

public record PlaceOrderResult(
    UUID orderId,
    String status
) {}

public interface PlaceOrderUseCase {
    PlaceOrderResult handle(PlaceOrderCommand command);
}
~~~

PlaceOrderCommand thể hiện thông tin cần thiết để thực hiện ca sử dụng. PlaceOrderResult thể hiện kết quả mà ứng dụng muốn cung cấp. Các kiểu này không chứa HttpServletRequest, ResponseEntity, Kafka ConsumerRecord hay đối tượng giao diện web. Vì vậy, tầng ứng dụng không cần biết ai đã gửi yêu cầu hoặc dữ liệu ban đầu được mã hóa theo giao thức nào.

Trường idempotencyKey chỉ cần có nếu nghiệp vụ hoặc hợp đồng vận hành yêu cầu nhận diện các lần gửi lặp. Với một ca sử dụng không có nhu cầu đó, có thể bỏ trường này. Khi có khóa, ứng dụng cần định nghĩa rõ phạm vi và thời hạn của khóa, cách phát hiện lần gửi trùng và kết quả trả lại. Việc broker có thể gửi lại message không tự động có nghĩa mọi command đều phải có cùng một cơ chế idempotency.

Dịch vụ ứng dụng triển khai hợp đồng và điều phối các bước:

~~~java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductCatalog products;
    private final OrderRepository orders;

    PlaceOrderService(ProductCatalog products, OrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Override
    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        List<OrderLine> lines = command.items().stream()
            .map(item -> {
                Product product = products.findById(item.productId())
                    .orElseThrow(ProductNotFoundException::new);

                return OrderLine.of(
                    product.id(), item.quantity(), product.price());
            })
            .toList();

        Order order = Order.place(
            CustomerId.of(command.customerId()), lines);

        orders.save(order);

        return new PlaceOrderResult(
            order.id().value(), order.status().name());
    }
}
~~~

Đây là ví dụ rút gọn để thể hiện ranh giới. ProductCatalog và OrderRepository là các hợp đồng mà dịch vụ ứng dụng cần; adapter hạ tầng cung cấp cách triển khai cụ thể. Domain Order chịu trách nhiệm bảo vệ các bất biến như đơn phải có dòng hàng hợp lệ. Dịch vụ ứng dụng điều phối việc lấy sản phẩm, tạo đơn và lưu kết quả trong một giao dịch.

Điểm cốt lõi là mỗi adapter gọi PlaceOrderUseCase. Nếu sau này thay JPA bằng một cơ chế lưu trữ khác, adapter trình bày không cần thay đổi vì hợp đồng ứng dụng vẫn giữ nguyên. Nếu bổ sung một kênh mới, kênh đó chỉ cần chuyển dữ liệu đầu vào của mình thành PlaceOrderCommand phù hợp.

## 4. Hai kênh khác nhau cùng gọi một ca sử dụng

### Kênh REST

REST controller xử lý HTTP và ánh xạ request thành command. DTO của HTTP có thể phản ánh cấu trúc API, kể cả tên trường hoặc quy tắc tương thích ngược của API:

~~~java
public record PlaceOrderRequest(
    @NotNull UUID customerId,
    @NotEmpty List<@Valid PlaceOrderLineRequest> items,
    String idempotencyKey
) {}

public record PlaceOrderLineRequest(
    @NotNull UUID productId,
    @Positive int quantity
) {}

public record PlaceOrderResponse(UUID orderId, String status) {}
~~~

Controller gọi cùng hợp đồng ứng dụng:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<PlaceOrderResponse> create(
            @Valid @RequestBody PlaceOrderRequest request) {
        PlaceOrderCommand command = new PlaceOrderCommand(
            request.customerId(),
            request.items().stream()
                .map(item -> new PlaceOrderItem(
                    item.productId(), item.quantity()))
                .toList(),
            request.idempotencyKey()
        );

        PlaceOrderResult result = placeOrder.handle(command);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new PlaceOrderResponse(
                result.orderId(), result.status()));
    }
}
~~~

Các annotation như @NotNull, @NotEmpty và @Positive giúp kiểm tra cấu trúc, kiểu và điều kiện đầu vào ở biên HTTP. Controller không quyết định đơn có được phép đặt hay không; những điều kiện nghiệp vụ phải được kiểm tra trong tầng ứng dụng hoặc domain để mọi kênh đều được bảo vệ.

### Kênh dòng lệnh

CLI có cách nhận dữ liệu và phản hồi khác. Adapter có thể đọc tham số, chuyển chúng thành command rồi in kết quả:

~~~java
@Component
class PlaceOrderCli implements CommandLineRunner {
    private final PlaceOrderUseCase placeOrder;
    private final CliOrderParser parser;

    PlaceOrderCli(PlaceOrderUseCase placeOrder, CliOrderParser parser) {
        this.placeOrder = placeOrder;
        this.parser = parser;
    }

    @Override
    public void run(String... args) {
        if (!parser.isPlaceOrderCommand(args)) {
            return;
        }

        PlaceOrderCommand command = parser.toCommand(args);
        PlaceOrderResult result = placeOrder.handle(command);

        System.out.println("Created order: " + result.orderId());
    }
}
~~~

CliOrderParser chịu trách nhiệm hiểu cú pháp dòng lệnh và chuyển dữ liệu sang command. CLI không cần biết đơn được lưu bằng JPA, cũng không cần tự triển khai việc kiểm tra sản phẩm hoặc tạo đơn. Trong ứng dụng thực tế, adapter CLI còn có thể chuyển lỗi cú pháp thành thông báo trợ giúp và mã thoát phù hợp.

### Kênh message

Một message consumer cũng có thể gọi cùng ca sử dụng khi nội dung message thể hiện đúng hành động đặt hàng:

~~~java
@Component
class PlaceOrderListener {
    private final PlaceOrderUseCase placeOrder;

    PlaceOrderListener(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @KafkaListener(topics = "orders-to-place")
    public void receive(OrderRequestedMessage message) {
        PlaceOrderCommand command = new PlaceOrderCommand(
            message.customerId(),
            message.items().stream()
                .map(item -> new PlaceOrderItem(
                    item.productId(), item.quantity()))
                .toList(),
            message.messageId()
        );

        placeOrder.handle(command);
    }
}
~~~

Message listener giải mã message và ánh xạ nội dung thành command. Cơ chế ack, retry và dead-letter thường do adapter cùng cấu hình container/broker đảm nhiệm. Nếu xử lý thất bại, listener có thể để lỗi truyền ra để cơ chế retry hoạt động theo cấu hình. Với message có khả năng được giao nhiều lần, hệ thống cần quyết định cách bảo vệ thao tác khỏi việc tạo đơn trùng; khóa message có thể được dùng làm idempotency key nếu hợp đồng nghiệp vụ xác định như vậy.

Các ví dụ trên cùng gọi PlaceOrderUseCase. Chúng không cần dùng chung DTO đầu vào hoặc định dạng kết quả bên ngoài. HTTP có thể trả JSON và status 201; CLI có thể in mã đơn; message consumer có thể xác nhận đã xử lý. Điều được tái sử dụng là ca sử dụng và quy tắc bên trong, còn cách trao đổi với từng kênh vẫn thuộc adapter tương ứng.

## 5. Luồng phụ thuộc và luồng xử lý

Có thể hình dung cấu trúc như sau:

~~~mermaid
flowchart LR
    HTTP[REST controller]
    CLI[CLI adapter]
    MSG[Message consumer]

    PORT[PlaceOrderUseCase]
    APP[PlaceOrderService]
    DOMAIN[Order domain model]
    REPO[OrderRepository port]
    DB[Persistence adapter and database]

    HTTP --> PORT
    CLI --> PORT
    MSG --> PORT
    PORT -.implemented by.-> APP
    APP --> DOMAIN
    APP --> REPO
    REPO -.implemented by.-> DB
~~~

Khi chạy, request đi từ một adapter trình bày đến dịch vụ ứng dụng, rồi đến domain và các cổng hạ tầng cần thiết. Các adapter trình bày phụ thuộc vào hợp đồng ứng dụng. Hướng phụ thuộc mã nguồn có thể được tổ chức sao cho adapter hạ tầng triển khai interface do phần bên trong định nghĩa; do đó, chi tiết JPA hoặc broker không trở thành yêu cầu của tầng trình bày.

Các tầng này là ranh giới logic. REST controller, CLI adapter và dịch vụ ứng dụng có thể nằm trong cùng một ứng dụng Spring Boot. Nếu cần, một adapter cũng có thể được đóng gói hoặc triển khai riêng, miễn là nó gọi được hợp đồng ứng dụng qua một ranh giới đã xác định. Việc có nhiều kênh giao tiếp không đồng nghĩa phải triển khai nhiều tầng hoặc nhiều máy chủ.

## 6. Giữ khác biệt của từng kênh ở đúng nơi

Tái sử dụng cùng ca sử dụng không có nghĩa mọi kênh phải xử lý mọi thứ giống nhau. Một số khác biệt cần được giữ tại biên:

- **Định dạng và cú pháp:** HTTP kiểm tra JSON, CLI phân tích tham số, consumer giải mã message. Mỗi adapter chuyển dữ liệu sang kiểu đầu vào của ứng dụng.
- **Thông báo lỗi:** REST ánh xạ lỗi thành HTTP status và response body; CLI hiển thị thông báo cùng exit code; consumer áp dụng retry hoặc dead-letter theo chính sách xử lý message.
- **Xác thực danh tính:** mỗi kênh có thể dùng cơ chế riêng như token, tài khoản hệ điều hành hoặc thông tin định danh trong message. Việc xác định người gọi thuộc biên bảo mật. Quyền thực hiện hành động cần được kiểm tra trong ngữ cảnh ca sử dụng hoặc chính sách nghiệp vụ, vì một kênh khác có thể gọi cùng hành động.
- **Ngữ cảnh yêu cầu:** locale, correlation ID, thông tin truy vết và metadata giao thức có thể được trích xuất tại adapter. Chỉ truyền vào ứng dụng những dữ liệu thực sự ảnh hưởng đến ca sử dụng hoặc kiểm toán.
- **Tính lặp lại và thứ tự:** HTTP client có thể gửi lại request, message broker có thể giao message nhiều lần, còn CLI có thể được người vận hành chạy lại. Cơ chế chống thực hiện trùng cần phù hợp với ngữ nghĩa của thao tác và được đặt tại nơi có thể bảo đảm tính nhất quán.

Cũng cần phân biệt hai loại kiểm tra. Kiểm tra request có trường customerId, danh sách items không rỗng và quantity có đúng kiểu, đúng định dạng là kiểm tra hợp đồng giao tiếp. Kiểm tra khách hàng có quyền đặt hàng, sản phẩm còn được phép bán và đơn không vi phạm bất biến là kiểm tra ứng dụng/nghiệp vụ. Một kiểm tra ở controller có thể giúp phản hồi lỗi sớm, nhưng không thay thế được quy tắc cần đúng cho mọi kênh.

Lỗi cũng cần được phân loại rõ. Lỗi cú pháp của HTTP request có thể trở thành 400; lỗi không tìm thấy tài nguyên có thể thành 404; vi phạm trạng thái nghiệp vụ có thể được ánh xạ thành 409 tùy hợp đồng API. CLI có thể dùng mã thoát khác nhau cho lỗi tham số và lỗi nghiệp vụ. Với message, lỗi tạm thời có thể được retry, còn lỗi dữ liệu không thể xử lý có thể chuyển sang dead-letter. Chính sách ánh xạ thuộc adapter; nguyên nhân và ý nghĩa nghiệp vụ của lỗi nên được biểu diễn ổn định ở tầng ứng dụng/domain.

## 7. Khi nào không nên ép hai kênh dùng cùng ca sử dụng?

Chỉ nên chia sẻ một ca sử dụng khi hai kênh yêu cầu cùng một hành động nghiệp vụ. Cùng tên gọi ở giao diện bên ngoài chưa đủ để kết luận chúng giống nhau.

Ví dụ, nút “Đặt hàng” trên website và lệnh “place-order” trên CLI có thể cùng tạo một đơn với các quy tắc giống nhau. Nhưng một message “OrderPaid” thông báo đơn đã được thanh toán có thể đại diện cho một hành động khác: ghi nhận thanh toán và chuyển trạng thái đơn. Không nên gọi PlaceOrderUseCase chỉ vì cả hai đều nhắc đến đơn hàng.

Nếu một kênh cần thêm bước nghiệp vụ riêng, hãy xác định đó là một ca sử dụng riêng hay chỉ là một bước điều phối bổ sung. Ví dụ, thao tác của nhân viên có thể cần kiểm tra quyền phê duyệt hoặc ghi nhận lý do thay đổi. Nếu điều kiện này là một quy tắc của hành động quản trị, nó cần được thể hiện trong hợp đồng ứng dụng hoặc chính sách nghiệp vụ, không nên chỉ ẩn trong controller nội bộ.

Tránh hai cực đoan:

- **Nhân bản quy trình theo từng kênh:** làm cho cùng một hành động có nhiều bản triển khai, dẫn đến sai khác về quy tắc, giao dịch và cách xử lý lỗi.
- **Một ca sử dụng tổng quát cho mọi việc:** tạo command với nhiều cờ như isFromWeb, isFromCli hoặc isInternal, rồi rải nhánh theo kênh trong dịch vụ ứng dụng. Điều này khiến tầng ứng dụng biết quá nhiều về giao thức và làm ca sử dụng khó hiểu.

Nếu hai kênh có cùng mục tiêu nhưng yêu cầu đầu vào khác nhau, adapter có thể chuyển đổi dữ liệu khác nhau thành cùng command. Nếu mục tiêu hoặc quy tắc khác nhau, hãy tạo hợp đồng ca sử dụng riêng và chia sẻ những thành phần nghiệp vụ thực sự chung.

## 8. Kiểm thử khả năng tái sử dụng và thay đổi kênh

Có thể kiểm tra ranh giới này bằng nhiều loại kiểm thử:

| Phạm vi kiểm thử | Điều cần xác minh |
|---|---|
| Unit test của application/domain | Cùng command tạo ra kết quả và quy tắc nghiệp vụ giống nhau, không phụ thuộc HTTP hoặc CLI. |
| Test REST adapter | JSON được ánh xạ đúng sang command; kết quả và lỗi được chuyển thành HTTP response theo hợp đồng API. |
| Test CLI adapter | Tham số được phân tích đúng; adapter gọi ca sử dụng và hiển thị kết quả/mã thoát phù hợp. |
| Test message adapter | Message được ánh xạ đúng; lỗi được truyền hoặc xử lý theo chính sách retry/ack đã cấu hình. |
| Integration test | Hợp đồng ứng dụng và adapter hạ tầng phối hợp đúng với cơ sở dữ liệu hoặc broker thực tế. |

Một bài kiểm thử hữu ích là gọi cùng PlaceOrderUseCase bằng hai bộ dữ liệu được chuyển đổi từ hai adapter khác nhau, rồi xác minh cùng một quy tắc nghiệp vụ được áp dụng. Không cần kiểm tra rằng hai kênh có response giống nhau; chúng có thể có định dạng khác nhau theo hợp đồng riêng.

Một dấu hiệu thiết kế chưa tốt là khi thêm kênh CLI phải sao chép toàn bộ logic từ REST controller, hoặc khi thay đổi JSON API làm dịch vụ ứng dụng phải đổi theo dù ý nghĩa ca sử dụng không đổi. Một dấu hiệu khác là domain cần import kiểu HTTP hoặc message broker. Những dấu hiệu đó cho thấy ranh giới giữa trình bày và phần bên trong chưa được giữ rõ.

Khi triển khai, hãy bắt đầu bằng việc xác định hành động nghiệp vụ và hợp đồng ứng dụng. Sau đó, tạo adapter cho từng kênh để chuyển dữ liệu vào hợp đồng và chuyển kết quả ra giao thức tương ứng. Giữ quy tắc nghiệp vụ ở domain, giữ trình tự và phối hợp ở application, còn việc nhận request, phân tích dữ liệu và định dạng phản hồi ở tầng trình bày. Cách tổ chức này cho phép hệ thống bổ sung hoặc thay đổi kênh giao tiếp mà vẫn duy trì cùng một ca sử dụng, miễn là mục tiêu nghiệp vụ của hành động không thay đổi.

