# Tạo quá nhiều lớp và khái niệm không đem lại ý nghĩa nghiệp vụ

Domain-Driven Design (DDD) khuyến khích mô hình hóa nghiệp vụ bằng những khái niệm có ý nghĩa, đặt hành vi và quy tắc ở đúng nơi, đồng thời làm rõ ranh giới giữa các phần của hệ thống. Tuy nhiên, DDD không yêu cầu tạo thật nhiều class, interface, factory, manager, service hoặc abstraction. Một mô hình có nhiều tên gọi nghe có vẻ chuyên nghiệp vẫn có thể khiến người đọc khó hiểu nghiệp vụ hơn.

Một lỗi thiết kế thường gặp là tạo lớp chỉ để chuyển tiếp lời gọi, bọc một kiểu dữ liệu mà không thêm quy tắc, hoặc dựng abstraction cho một khả năng chưa tồn tại và chưa có nhu cầu thực tế. Một use case đơn giản có thể đi qua nhiều tầng mapper, coordinator, processor, handler, manager và facade trước khi đến hành vi thật. Khi đó, người đọc phải lần theo nhiều file để hiểu một quyết định nghiệp vụ nhỏ.

Vấn đề không nằm ở số lượng class tự thân. Một hệ thống phức tạp có thể cần nhiều model, adapter và policy riêng. Vấn đề là mỗi khái niệm được thêm vào có tạo ra ranh giới, ngữ nghĩa, invariant hoặc khả năng thay đổi độc lập đủ rõ để bù lại chi phí nhận thức và bảo trì hay không.

Bài học này giúp nhận diện overengineering trong mô hình DDD, phân biệt abstraction có giá trị với ceremony, lựa chọn số lớp phù hợp và refactor dần một thiết kế nhiều tầng thành mô hình dễ hiểu hơn mà vẫn giữ được ranh giới kiến trúc cần thiết.

Sau bài học, người học có thể:

- giải thích vì sao nhiều class hoặc nhiều layer không tự động tạo ra thiết kế tốt;
- nhận diện pass-through class, wrapper rỗng, interface không có vai trò và abstraction suy đoán;
- phân biệt khái niệm nghiệp vụ với cấu trúc kỹ thuật;
- quyết định khi nào cần Entity, Value Object, Domain Service, Factory, Repository, Policy hoặc Domain Event;
- biết khi nào một lớp application service, mapper hoặc adapter thực sự có ích;
- đánh giá abstraction bằng ngữ nghĩa, invariant, ownership, biến thiên và chi phí thay đổi;
- đơn giản hóa code mà không gom mọi trách nhiệm vào một class khổng lồ;
- dùng ví dụ, test và phản hồi của chuyên gia để xác nhận mô hình;
- xây dựng quy trình loại bỏ indirection không cần thiết và giữ lại boundary có giá trị.

## 1. Nhiều lớp không đồng nghĩa với mô hình tốt

Một kiến trúc có thể có nhiều tầng nhưng vẫn không diễn đạt được nghiệp vụ. Ví dụ một thao tác hủy đơn đi qua:

~~~text
OrderController
      |
      v
CancelOrderRequestMapper
      |
      v
CancelOrderCommandFactory
      |
      v
CancelOrderCommandHandler
      |
      v
OrderCancellationCoordinator
      |
      v
OrderCancellationManager
      |
      v
OrderCancellationProcessor
      |
      v
OrderRepositoryFacade
      |
      v
OrderJpaRepositoryAdapter
      |
      v
Database
~~~

Mỗi lớp có thể chỉ gọi lớp tiếp theo mà không kiểm tra quy tắc, chuyển đổi mô hình, bảo vệ transaction hay tạo một boundary có ý nghĩa. Người đọc phải mở nhiều file mới tìm thấy hành vi thực sự.

Nếu tất cả lớp chỉ chuyển tiếp cùng một tham số và cùng một kết quả, chúng tạo ra indirection mà không tạo ra abstraction hữu ích.

Một thiết kế đơn giản hơn có thể là:

~~~text
HTTP Adapter
    |
    v
CancelOrderHandler
    |
    +----> OrderRepository
    |
    +----> Order.cancel(reason)
    |
    v
Persistence / Outbox Adapter
~~~

Thiết kế thứ hai vẫn có boundary giữa transport, application, domain và infrastructure. Nó chỉ tránh tạo thêm các tầng không có trách nhiệm riêng.

### Phân biệt layer với lớp

Layer là ranh giới trách nhiệm trong kiến trúc, chẳng hạn:

- Presentation/Transport: nhận request và định dạng response.
- Application: điều phối use case và transaction.
- Domain: mô hình, hành vi và quy tắc nghiệp vụ.
- Infrastructure: database, HTTP client, broker và file system.

Một layer có thể gồm nhiều class hoặc chỉ một vài class. Tạo thêm class trong cùng một layer không tự động tạo ra layer mới. Ngược lại, một interface port có thể là boundary kiến trúc có giá trị dù chỉ có một implementation hiện tại.

Đừng dùng số lượng package hoặc class để đo chất lượng DDD. Hãy xem trách nhiệm và ngữ nghĩa mà mỗi thành phần sở hữu.

## 2. Dấu hiệu đang tạo quá nhiều lớp

Một lớp đáng xem xét lại khi nó không có trách nhiệm riêng và chỉ làm tăng số bước cần đọc.

| Dấu hiệu | Ví dụ | Câu hỏi cần đặt |
|---|---|---|
| Pass-through class | Manager chỉ gọi service.process() | Lớp này có quyết định hoặc bảo vệ điều gì? |
| Wrapper rỗng | Amount chỉ chứa BigDecimal và getter | Nó có invariant, đơn vị hoặc semantics riêng không? |
| Interface một implementation | IOrderManager chỉ có DefaultOrderManager | Interface này bảo vệ boundary hay chỉ phản chiếu class? |
| Factory cho constructor đơn giản | OrderFactory chỉ gọi new Order(id) | Việc tạo object có quy tắc hoặc nhiều nguồn dữ liệu không? |
| Service trùng nghĩa | OrderService, OrderManager, OrderProcessor cùng xử lý một use case | Ai sở hữu hành vi và quyết định cuối cùng? |
| DTO nội bộ liên tiếp | Request -> CommandDTO -> InternalDTO -> DomainInput với cùng field | Mỗi chuyển đổi có thay đổi contract hoặc semantics không? |
| Generic base class suy đoán | BaseCrudService<T, ID> cho mọi aggregate | Các loại thực thể có thực sự cùng quy tắc không? |
| Event cho mọi thay đổi field | OrderStatusUpdated sau mỗi setter | Đây có phải fact nghiệp vụ mà consumer cần biết không? |
| Policy chỉ bọc một điều kiện | CanCancelPolicy trả về một biểu thức if duy nhất | Quy tắc có đủ phức tạp hoặc cần tên riêng không? |
| Abstraction chưa có nhu cầu | Plugin system cho một nguồn dữ liệu cố định | Có biến thiên thực tế hoặc quyết định tương lai đủ gần không? |

Một dấu hiệu riêng lẻ chưa đủ để kết luận thiết kế sai. Ví dụ, một interface có một implementation vẫn có thể rất có giá trị nếu nó là port tới hệ thống ngoài. Cần đánh giá mục đích và chi phí của nó trong ngữ cảnh cụ thể.

## 3. Khái niệm kỹ thuật khác với khái niệm nghiệp vụ

DDD hướng đến mô hình phản ánh ngôn ngữ và cách tổ chức hiểu domain. Không phải mọi danh từ trong code đều cần trở thành một khái niệm miền.

Ví dụ, các tên sau thường là chi tiết kỹ thuật:

- RequestMapper
- JpaEntityConverter
- RetryExecutor
- TransactionCoordinator
- JsonPayloadBuilder
- CacheEntry
- HttpResponseWrapper

Chúng có thể là thành phần cần thiết của implementation, nhưng không nên được trình bày như thể chúng là khái niệm nghiệp vụ.

Các tên như Order, Reservation, CreditLimit, Refund, DeliveryWindow hoặc Subscription có thể là khái niệm miền nếu chuyên gia sử dụng chúng với ý nghĩa ổn định và chúng có quy tắc riêng.

### Một khái niệm có giá trị thường có ít nhất một lý do rõ

- Có tên được dùng trong ngôn ngữ nghiệp vụ.
- Có identity hoặc lifecycle cần quản lý.
- Có invariant cần bảo vệ.
- Có nhiều giá trị hoặc hành vi cần được giữ cùng nhau.
- Có policy hoặc quyết định riêng.
- Có owner hoặc boundary rõ.
- Có thể thay đổi độc lập với thành phần khác.
- Giúp loại bỏ một sự phụ thuộc hoặc một quy tắc bị lặp.

Không cần mọi khái niệm phải đáp ứng tất cả điều kiện. Một Value Object có thể rất nhỏ nhưng vẫn có ý nghĩa vì nó biểu diễn một đơn vị đo hoặc currency. Một adapter có thể không phải khái niệm domain nhưng vẫn có lý do tồn tại vì nó cô lập giao thức bên ngoài.

### Đừng đặt tên miền cho một lớp kỹ thuật để làm nó có vẻ quan trọng

Một lớp có tên OrderPolicy nhưng chỉ gọi repository rồi trả về true/false có thể không phải domain policy. Nếu nó không sở hữu quy tắc mà chỉ truy vấn dữ liệu, có thể nó thuộc application query hoặc domain service tùy semantics.

Tên phải mô tả trách nhiệm thật. Không nên tạo các tên như DomainManager hoặc BusinessProcessor chỉ để tránh một class dài.

## 4. Abstraction có giá trị phải giảm độ phức tạp tổng thể

Abstraction không miễn phí. Nó tạo thêm tên, file, interface, mapping và đường điều hướng. Nó đáng dùng khi giảm được một loại phức tạp lớn hơn.

Có thể đánh giá theo năm câu hỏi:

1. **Ngữ nghĩa:** abstraction có tên diễn đạt một khái niệm hoặc capability rõ ràng không?
2. **Trách nhiệm:** nó có sở hữu một quy tắc, invariant hoặc quyết định riêng không?
3. **Boundary:** nó có cô lập một dependency, context hoặc giao thức không?
4. **Biến thiên:** có nhiều implementation, policy hoặc cách thay đổi thực tế cần được tách không?
5. **Chi phí:** lợi ích về hiểu biết, thay đổi và kiểm thử có lớn hơn chi phí indirection không?

Nếu không có câu trả lời rõ cho bất kỳ câu hỏi nào, hãy cân nhắc chưa tạo abstraction. Có thể bắt đầu bằng code trực tiếp, sau đó trích xuất khi một mẫu lặp hoặc một biến thiên thực sự xuất hiện.

### Abstraction tốt không nhất thiết phải lớn

Một Value Object gồm hai field có thể loại bỏ nhiều lỗi đơn vị. Một interface có một method có thể tách application khỏi payment provider. Một policy mười dòng có thể diễn đạt rõ quy tắc tính ngày làm việc.

Ngược lại, một framework generic vài trăm dòng có thể làm một thao tác đơn giản khó hiểu hơn.

## 5. Ví dụ: nhiều tầng cho một thao tác hủy đơn

Giả sử một ứng dụng chỉ cần hủy một Order theo ID và lý do. Thiết kế ban đầu:

~~~java
public final class CancelOrderManager {
    private final CancelOrderProcessor processor;

    public CancelOrderManager(CancelOrderProcessor processor) {
        this.processor = processor;
    }

    public void cancel(CancelOrderCommand command) {
        processor.process(command);
    }
}
~~~

~~~java
public final class CancelOrderProcessor {
    private final CancelOrderService service;

    public CancelOrderProcessor(CancelOrderService service) {
        this.service = service;
    }

    public void process(CancelOrderCommand command) {
        service.execute(command);
    }
}
~~~

~~~java
public final class CancelOrderService {
    private final OrderRepository repository;

    public CancelOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public void execute(CancelOrderCommand command) {
        Order order = repository.get(command.orderId());
        order.setStatus(OrderStatus.CANCELLED);
        repository.save(order);
    }
}
~~~

Manager và Processor không thêm quy tắc hoặc boundary. Service lại thay đổi status bằng setter, nên invariant chưa được bảo vệ tại nơi sở hữu trạng thái.

Có thể đơn giản hóa:

~~~java
public final class CancelOrderHandler {
    private final OrderRepository orders;

    public CancelOrderHandler(OrderRepository orders) {
        this.orders = orders;
    }

    public void handle(CancelOrderCommand command) {
        Order order = orders.get(command.orderId());
        order.cancel(command.reason());
        orders.save(order);
    }
}
~~~

Aggregate bảo vệ hành vi:

~~~java
public final class Order {
    private OrderStatus status;

    public void cancel(CancellationReason reason) {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderCannotBeCancelled();
        }
        if (status == OrderStatus.CANCELLED) {
            throw new OrderAlreadyCancelled();
        }

        status = OrderStatus.CANCELLED;
        recordEvent(new OrderCancelled(id, reason));
    }
}
~~~

Handler điều phối use case; Order bảo vệ invariant; repository lưu aggregate. Mỗi thành phần có một lý do tồn tại.

### Khi nào vẫn cần thêm lớp?

Nếu quy trình hủy đơn cần:
- kiểm tra quyền hủy theo loại khách;
- tính phí hủy theo thời điểm;
- phối hợp reservation và payment;
- ghi audit;
- phát outbox event;
- hỗ trợ nhiều loại yêu cầu hủy;

thì một application service hoặc domain policy riêng có thể hữu ích. Hãy thêm lớp khi có trách nhiệm mới, không phải vì một use case cần một số lượng tầng cố định.

## 6. Wrapper quanh primitive: khi nào có giá trị?

DDD thường dùng Value Object để tránh primitive obsession. Tuy nhiên, bọc mọi String, Integer hoặc BigDecimal thành một class mà không có invariant hay semantics riêng có thể tạo ra rất nhiều kiểu không cần thiết.

### Wrapper không thêm giá trị

~~~java
public record Name(String value) {
    public String getValue() {
        return value;
    }
}
~~~

Nếu Name không kiểm tra độ dài, chuẩn hóa, equality đặc biệt hoặc quy tắc nào khác, và mọi caller vẫn phải xử lý String trực tiếp, wrapper có thể chỉ tăng số lần chuyển đổi.

### Wrapper có ngữ nghĩa

~~~java
public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }
}
~~~

CustomerId ngăn nhầm ID khách hàng với OrderId dù cả hai cùng biểu diễn UUID. Đây là một lợi ích kiểu dữ liệu đáng kể ở boundary có nhiều loại định danh.

~~~java
public record Percentage(BigDecimal value) {
    public Percentage {
        Objects.requireNonNull(value, "value");
        if (value.compareTo(BigDecimal.ZERO) < 0
                || value.compareTo(BigDecimal.valueOf(100)) > 0) {
            throw new IllegalArgumentException(
                    "Percentage must be between 0 and 100"
            );
        }
    }

    public BigDecimal applyTo(BigDecimal amount) {
        return amount.multiply(value)
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
    }
}
~~~

Percentage có miền giá trị và hành vi rõ. Nhưng quy tắc làm tròn trong ví dụ chỉ là một lựa chọn minh họa; nếu từng nghiệp vụ có rounding policy khác nhau, hãy truyền policy hoặc dùng calculator phù hợp thay vì giấu một quy tắc chung trong Percentage.

### Dùng wrapper theo ý nghĩa, không theo từng field

Không cần tạo CustomerFirstName, CustomerLastName, CustomerPhone, CustomerEmail nếu chúng không có semantics hoặc quy tắc riêng. Nhưng EmailAddress có thể đáng là Value Object nếu hệ thống có validation, normalization và policy xác minh. PhoneNumber có thể cần country code và chuẩn hóa. Quyết định dựa trên domain và use case.

## 7. Không phải mọi hành vi đều cần Domain Service

Domain Service phù hợp khi một quy tắc nghiệp vụ:
- có ý nghĩa miền;
- không thuộc tự nhiên về một Entity hoặc Value Object;
- phối hợp nhiều khái niệm miền;
- vẫn có thể được mô tả bằng ngôn ngữ nghiệp vụ.

Ví dụ, chính sách phân bổ tín dụng có thể liên quan Customer, Exposure và CreditLimit. Nếu không có một entity nào sở hữu tự nhiên quyết định này, CreditAllocationPolicy có thể phù hợp.

Ngược lại, không cần Domain Service chỉ để chuyển tiếp:

~~~java
public final class OrderStatusService {
    public OrderStatus statusOf(Order order) {
        return order.status();
    }
}
~~~

Nếu operation chỉ đọc một property, nó không tạo ra quy tắc mới.

### Phân biệt Application Service và Domain Service

| Thành phần | Trách nhiệm |
|---|---|
| Application Service | Điều phối use case, transaction, authorization flow và port |
| Domain Service | Quy tắc nghiệp vụ không thuộc tự nhiên về một Entity/Value Object |
| Entity/Aggregate | Bảo vệ invariant và lifecycle thuộc đối tượng |
| Value Object | Quy tắc và phép toán thuần trên giá trị |
| Infrastructure Adapter | Giao tiếp database, HTTP, broker hoặc file |

Không nên dùng hậu tố Service như một lý do để gom mọi logic vào một class. Hãy xác định loại trách nhiệm trước khi chọn tên.

## 8. Repository: một abstraction có ranh giới, không phải CRUD cho mọi bảng

Trong DDD, Repository thường cung cấp cách truy xuất Aggregate Root theo ngôn ngữ domain. Nó không nhất thiết phải là một interface CRUD generic cho mọi row.

Một interface có ý nghĩa:

~~~java
public interface OrderRepository {
    Optional<Order> find(OrderId id);
    void save(Order order);
}
~~~

Một interface có thể quá tổng quát:

~~~java
public interface GenericRepository<T, ID> {
    T findById(ID id);
    void save(T entity);
    void update(T entity);
    void delete(ID id);
    List<T> findAll();
}
~~~

Generic repository không tự động sai. Nó có thể phù hợp với một framework nội bộ hoặc một số aggregate có cùng contract. Nhưng nếu mọi aggregate bị ép có cùng thao tác, nhóm có thể tạo API không phản ánh lifecycle: Order có thể cancel, Invoice có thể issue, Reservation có thể expire. Không phải aggregate nào cũng có ý nghĩa với delete hoặc update tùy ý.

Hãy tạo repository theo nhu cầu truy xuất và lưu aggregate. Query phức tạp cho màn hình có thể dùng query service hoặc read model thay vì nhồi mọi truy vấn vào repository domain.

## 9. Factory: chỉ cần khi việc tạo object có quyết định

Factory có giá trị khi tạo một object:
- cần kiểm tra nhiều điều kiện;
- phải phối hợp nhiều Value Object;
- cần chọn một subtype;
- cần khôi phục object từ dữ liệu có nhiều dạng;
- che giấu cấu trúc tạo phức tạp;
- cần bảo đảm aggregate bắt đầu ở trạng thái hợp lệ.

Nếu constructor đơn giản và public API đã đủ rõ, một factory chỉ gọi constructor có thể không cần thiết.

~~~java
public final class OrderFactory {
    public Order create(OrderId id, CustomerId customerId) {
        return new Order(id, customerId);
    }
}
~~~

Nếu không có quy tắc hoặc nguồn dữ liệu khác, lớp trên không thêm ý nghĩa.

Một factory có thể hợp lý hơn khi tạo đơn từ quote đã được xác nhận:

~~~java
public final class OrderFactory {
    public Order createFrom(ConfirmedQuote quote, CustomerId customer) {
        if (quote.isExpired()) {
            throw new QuoteExpired();
        }

        List<OrderLine> lines = quote.lines().stream()
                .map(line -> OrderLine.from(line.productId(),
                                            line.quantity(),
                                            line.confirmedPrice()))
                .toList();

        return Order.place(
                OrderId.newId(),
                customer,
                lines,
                quote.currency()
        );
    }
}
~~~

Factory này thể hiện một quy trình tạo có ý nghĩa và chuyển dữ liệu từ một khái niệm miền khác sang Order. Nếu logic phát triển thêm hoặc có nhiều nguồn tạo, trách nhiệm của factory càng rõ.

## 10. Event không phải thông báo cho mọi lần cập nhật

Domain Event biểu diễn một fact nghiệp vụ đã xảy ra. Không nên tạo event chỉ vì một field bị set hoặc một row được cập nhật.

Ví dụ event có ý nghĩa:
- OrderPlaced
- PaymentCaptured
- ReservationExpired
- CreditLimitApproved

Một event quá kỹ thuật:
- OrderRowUpdated
- StatusColumnChanged
- JpaEntitySaved

Nếu consumer cần biết một đơn đã được đặt, OrderPlaced là contract có ý nghĩa. Nếu chỉ cần ghi lại field nào đã thay đổi để audit, đó có thể là audit trail chứ không nhất thiết là Domain Event.

Không nên tạo EventFactory, EventManager, EventProcessor và EventCoordinator riêng nếu chúng chỉ bọc một lệnh publish đơn giản. Nhưng outbox relay, event serializer hoặc dispatcher có thể cần abstraction vì chúng quản lý retry, serialization, ordering hoặc transport.

## 11. Policy, Strategy và Specification không phải mặc định cho mọi điều kiện

Các pattern như Policy, Strategy và Specification hữu ích khi có quy tắc độc lập, nhiều biến thể hoặc khả năng kết hợp.

Ví dụ:
- nhiều chính sách tính phí vận chuyển theo khu vực;
- nhiều cách đánh giá tín dụng theo loại khách;
- điều kiện đủ tiêu chuẩn có thể kết hợp và tái sử dụng;
- chính sách hoàn tiền thay đổi theo kênh và thời điểm.

Không cần tạo interface cho một điều kiện đơn giản chỉ được dùng một lần:

~~~java
if (order.status() == OrderStatus.PLACED) {
    // cho phép yêu cầu hủy
}
~~~

Nếu quy tắc trở nên phức tạp hoặc được dùng ở nhiều nơi, có thể đặt tên:

~~~java
public final class CancellationEligibility {
    public boolean isEligible(Order order, Instant requestedAt) {
        return order.status() == OrderStatus.PLACED
                && !order.isPastCancellationDeadline(requestedAt);
    }
}
~~~

Nếu chỉ có một rule nhỏ, method trong Order có thể còn rõ hơn. Pattern không phải mục tiêu; khả năng diễn đạt rule và bảo vệ nó mới là mục tiêu.

## 12. DTO và Mapper: không cần một lớp cho mỗi lần chuyển tiếp

DTO hữu ích ở boundary:
- HTTP request/response;
- message contract;
- batch import/export;
- projection cho màn hình;
- adapter với hệ thống ngoài.

Mapper hữu ích khi chuyển đổi có semantics, validation hoặc nhiều field. Nhưng không cần tạo một DTO nội bộ mới ở mỗi tầng nếu dữ liệu và ý nghĩa không đổi.

Một luồng có thể đủ rõ:

~~~text
CreateOrderRequest
        |
        v
Application Handler
        |
        v
Order.place(...)
        |
        v
OrderResponse
~~~

Nếu một hệ thống có contract ngoài khác domain model, hãy giữ DTO riêng. Nếu mapper chỉ copy một UUID từ request vào command rồi command lại copy UUID sang một input object khác, hãy kiểm tra xem mỗi bước có bảo vệ boundary thực sự không.

### Không gộp mọi model chỉ để giảm số class

Đơn giản hóa không có nghĩa dùng một class cho request, domain, database và response. Việc gộp có thể tạo coupling còn tốn kém hơn số lớp được tiết kiệm. Hãy tách khi contract, lifecycle, validation hoặc quyền sở hữu khác nhau.

## 13. Generic abstraction và Base Class

Một base class có thể giảm lặp khi nhiều kiểu thực sự chia sẻ hành vi và invariant. Nhưng một generic framework được tạo quá sớm thường buộc các khái niệm khác nhau đi theo cùng một lifecycle.

Ví dụ đáng nghi:

~~~java
public abstract class BaseEntityService<T, ID> {
    public abstract T find(ID id);
    public abstract T create(T value);
    public abstract T update(ID id, T value);
    public abstract void delete(ID id);
}
~~~

Order, Invoice, Payment và Reservation không nhất thiết có cùng quy tắc create/update/delete. Nếu base class chỉ giúp viết ít dòng nhưng khiến mỗi subclass phải override hoặc vô hiệu hóa nhiều method, abstraction đang sai.

Hãy tìm phần lặp thực sự:
- có cùng semantics không?
- có cùng thứ tự và điều kiện không?
- thay đổi một nơi có nên ảnh hưởng tất cả không?
- các class có cùng lý do thay đổi không?

Nếu chỉ lặp cú pháp nhưng khác nghiệp vụ, giữ code riêng có thể dễ hiểu hơn.

## 14. Tạo interface khi có boundary hoặc biến thiên thực tế

Một interface có thể đáng giá khi:
- application layer cần một port tới infrastructure;
- có nhiều implementation với semantics giống nhau;
- cần thay đổi adapter mà không đổi use case;
- module cần công bố contract ổn định;
- test cần thay dependency ngoài một cách có ý nghĩa.

Ví dụ:

~~~java
public interface PaymentGateway {
    PaymentResult authorize(AuthorizationRequest request);
}
~~~

Interface này thể hiện một capability bên ngoài mà application cần. Implementation có thể là provider A, provider B hoặc fake trong test.

Ngược lại, tạo IOrderService cho một OrderService chỉ để tuân theo quy tắc “mọi class phải có interface” không tự tạo ra boundary. Nếu interface không có consumer độc lập, không có khả năng thay thế và không phải contract module, nó có thể chỉ tăng indirection.

Một implementation duy nhất không phải lý do đủ để xóa interface. Cần xem interface có phải port ổn định hay chỉ phản chiếu class.

## 15. Đừng tạo một lớp cho mỗi động từ

Một số codebase tạo class cho mọi hành động:
- CreateOrderService
- UpdateOrderService
- DeleteOrderService
- CancelOrderService
- ConfirmOrderService
- ShipOrderService

Một use case handler riêng cho mỗi command có thể hợp lý trong hệ thống CQRS hoặc khi các use case có transaction, authorization và orchestration khác nhau. Nhưng nếu các lớp chỉ gọi cùng một method hoặc chỉ cập nhật field, số lượng handler có thể không đem lại lợi ích.

Hãy phân biệt:
- use case có mục tiêu và boundary riêng;
- domain operation trên một aggregate;
- technical operation của adapter;
- helper method chỉ phục vụ tổ chức code.

Không cần biến mỗi method thành một class. Cũng không nên gom mọi use case vào một God Service có hàng chục nhánh. Chọn đơn vị tổ chức theo trách nhiệm, thay đổi và khả năng hiểu.

## 16. Một ví dụ: thiết kế quá mức cho tính phí giao hàng

Giả sử nghiệp vụ hiện tại chỉ có một quy tắc: đơn trên một ngưỡng được miễn phí vận chuyển, còn lại trả một mức phí cố định.

Một thiết kế quá mức có thể gồm:

~~~text
ShippingFeeController
   |
ShippingFeeRequestMapper
   |
ShippingFeeCommandFactory
   |
ShippingFeeOrchestrator
   |
ShippingFeeCalculationManager
   |
ShippingFeeStrategyResolver
   |
ShippingFeeStrategyRegistry
   |
DefaultShippingFeeStrategy
   |
ShippingFeeCalculator
   |
ShippingFeeResultAssembler
~~~

Nếu không có nhiều chiến lược, không có cấu hình, không có biến thiên theo vùng và mỗi lớp chỉ chuyển tiếp, thiết kế này che khuất quy tắc đơn giản.

Có thể bắt đầu bằng một policy nhỏ:

~~~java
public final class ShippingFeePolicy {
    private final Money freeShippingThreshold;
    private final Money standardFee;

    public ShippingFeePolicy(
            Money freeShippingThreshold,
            Money standardFee
    ) {
        this.freeShippingThreshold = freeShippingThreshold;
        this.standardFee = standardFee;
    }

    public Money feeFor(Money merchandiseTotal) {
        if (merchandiseTotal.compareTo(freeShippingThreshold) >= 0) {
            return Money.zero(merchandiseTotal.currency());
        }
        return standardFee;
    }
}
~~~

Nếu sau này xuất hiện nhiều rule theo khu vực, trọng lượng, phương thức giao hàng và loại khách hàng, policy có thể được tách thành các chiến lược. Không cần xây registry và plugin system trước khi có nhu cầu đó.

### Khi độ phức tạp thật sự xuất hiện

Một phiên bản mới có thể cần:
- phí theo vùng;
- phí theo trọng lượng;
- miễn phí theo membership;
- surcharge cho giao hàng nhanh;
- giới hạn do carrier;
- thời gian hiệu lực của bảng giá.

Khi đó, một ShippingPricingService hoặc tập policy có thể trở thành abstraction hợp lý. Sự phức tạp đến từ quy tắc thực tế, không phải từ mong muốn làm kiến trúc trông tổng quát.

## 17. Phân biệt đơn giản với đơn giản hóa quá mức

Thiết kế quá nhiều lớp là một cực. Một class khổng lồ chứa mọi thứ là cực còn lại.

~~~text
Over-engineered
  nhiều lớp chuyển tiếp, không rõ ownership
              |
              v
      khó lần theo hành vi

Under-designed
  một class xử lý HTTP, SQL, rule và event
              |
              v
      khó tách trách nhiệm
~~~

Mục tiêu là đủ cấu trúc để mỗi quyết định có owner rõ, nhưng không thêm abstraction không cần thiết.

Một application service có thể điều phối nhiều bước. Domain aggregate có thể có nhiều method. Repository adapter có thể chứa mapping. Đó không phải overengineering nếu các trách nhiệm thực sự tồn tại.

### Một nguyên tắc cân bằng

- Tách khi có lý do thay đổi hoặc semantics khác nhau.
- Giữ cùng nhau khi dữ liệu và hành vi thuộc một invariant.
- Dùng interface tại boundary, không dùng như nghi thức.
- Tạo Value Object khi kiểu mới bảo vệ meaning hoặc invariant.
- Trích xuất policy khi quy tắc có tên và có khả năng được hiểu hoặc thay đổi độc lập.
- Đừng tạo abstraction chỉ để dự đoán mọi biến thể tương lai.

## 18. DDD không phải danh sách pattern phải dùng

Một dự án DDD không cần phải có đủ:
- Entity;
- Value Object;
- Aggregate;
- Domain Service;
- Factory;
- Repository;
- Specification;
- Policy;
- Domain Event;
- Saga;
- Anti-Corruption Layer.

Các pattern là công cụ giải quyết vấn đề. Một use case đơn giản có thể chỉ cần Value Object, Aggregate và Repository. Một context có nhiều workflow bất đồng bộ có thể cần Domain Event, Process Manager hoặc Saga. Một hệ thống tích hợp legacy có thể cần ACL. Không cần thêm pattern để “đủ bộ”.

### Chọn pattern bằng câu hỏi

| Nhu cầu | Pattern có thể phù hợp |
|---|---|
| Identity và lifecycle | Entity |
| Equality theo giá trị, invariant | Value Object |
| Consistency boundary | Aggregate |
| Truy xuất aggregate | Repository |
| Quy tắc không thuộc tự nhiên một entity | Domain Service |
| Tạo object có nhiều điều kiện | Factory |
| Fact cần consumer khác biết | Domain Event |
| Chuyển đổi model qua context boundary | Anti-Corruption Layer |
| Quy trình dài qua nhiều transaction | Saga / Process Manager |
| Nhiều cách thực thi cùng contract | Strategy / Policy |

Nếu không có nhu cầu tương ứng, không cần pattern đó.

## 19. Đánh giá chi phí của indirection

Mỗi abstraction có lợi ích và chi phí. Có thể dùng các dấu hiệu sau trong code review:

### Chi phí điều hướng

- Người đọc phải mở bao nhiêu file để hiểu một quyết định?
- Tên lớp có giúp đoán được trách nhiệm không?
- Có nhiều method chỉ đổi tên rồi chuyển tiếp không?

### Chi phí thay đổi

- Một thay đổi nghiệp vụ cần sửa bao nhiêu lớp?
- Có phải cập nhật interface, implementation, factory, registry và mapper dù behavior không đổi?
- Một lớp có nhiều caller không liên quan không?

### Chi phí nhận thức

- Có bao nhiêu khái niệm mới phải hiểu trước khi đọc use case?
- Các wrapper có phân biệt được semantics hay chỉ đổi tên kiểu?
- Có abstraction generic nào buộc người đọc hiểu framework riêng của dự án?

### Chi phí kiểm thử

- Test có phải mock nhiều tầng nội bộ?
- Fake có phức tạp hơn logic cần test?
- Có thể kiểm tra behavior qua một boundary rõ hơn không?

Không nên đặt một ngưỡng số class cứng. Một workflow tài chính phức tạp có thể cần nhiều policy và adapter. Một CRUD nhỏ có thể chỉ cần vài thành phần. Mục tiêu là làm rõ lợi ích và chi phí của mỗi abstraction.

## 20. Tái cấu trúc khi đã có quá nhiều lớp

Đừng xóa hàng loạt lớp trong một lần. Hãy bắt đầu từ một use case và lần theo luồng thực thi.

### Bước 1: tìm behavior thực sự

Tìm nơi có:
- quyết định nghiệp vụ;
- kiểm tra invariant;
- thay đổi trạng thái;
- tính toán;
- phát event;
- tương tác với hệ thống ngoài.

Nếu lớp chỉ chuyển tiếp, đánh dấu là ứng viên để gộp.

### Bước 2: xác định owner

Hỏi:
- quy tắc thuộc Aggregate nào?
- use case do application layer nào điều phối?
- dữ liệu do context nào sở hữu?
- dependency nào cần port?

### Bước 3: bảo vệ behavior

Viết hoặc cập nhật test ở boundary công khai. Test nên xác nhận kết quả, trạng thái và side effect có ý nghĩa, không phụ thuộc vào số lớp trung gian.

### Bước 4: gộp pass-through layer

Nếu Manager chỉ gọi Processor, và Processor chỉ gọi Service, có thể gộp chúng vào application handler hoặc class có trách nhiệm rõ hơn. Giữ lớp nào đang sở hữu transaction hoặc boundary thực sự.

### Bước 5: đưa rule về domain object

Nếu service bên ngoài đang cập nhật status và kiểm tra điều kiện cho một aggregate, cân nhắc chuyển operation vào aggregate. Không chuyển logic truy vấn hạ tầng vào domain object.

### Bước 6: xóa wrapper không thêm semantics

Nếu một wrapper không có invariant, behavior, identity, unit hoặc boundary, có thể thay bằng kiểu hiện có. Kiểm tra serialization, API và persistence trước khi thay đổi public contract.

### Bước 7: giữ abstraction có lý do

Không xóa port chỉ vì hiện tại có một implementation nếu nó là boundary quan trọng. Không gộp API DTO với domain object nếu contract cần độc lập.

### Bước 8: chạy test và review diff

Sau mỗi bước, chạy test phù hợp. Review xem:
- behavior có giữ nguyên không;
- trách nhiệm có rõ hơn không;
- dependency có đi đúng chiều không;
- số khái niệm cần hiểu có giảm mà không mất semantics không.

## 21. Ví dụ refactor một chuỗi wrapper

Trước:

~~~java
public final class CustomerCreditLimitManager {
    private final CustomerCreditLimitProcessor processor;

    public Money getLimit(CustomerId id) {
        return processor.loadLimit(id);
    }
}
~~~

~~~java
public final class CustomerCreditLimitProcessor {
    private final CustomerCreditLimitService service;

    public Money loadLimit(CustomerId id) {
        return service.findLimit(id);
    }
}
~~~

~~~java
public final class CustomerCreditLimitService {
    private final CustomerRepository customers;

    public Money findLimit(CustomerId id) {
        return customers.find(id)
                .orElseThrow(CustomerNotFound::new)
                .creditLimit();
    }
}
~~~

Sau:

~~~java
public final class GetCustomerCreditLimitHandler {
    private final CustomerRepository customers;

    public Money handle(CustomerId id) {
        return customers.find(id)
                .orElseThrow(CustomerNotFound::new)
                .creditLimit();
    }
}
~~~

Nếu việc lấy credit limit chỉ là query đơn giản, một handler là đủ. Nếu sau này cần kiểm tra nhiều nguồn exposure, tính hạn mức khả dụng và áp dụng policy, có thể tạo một CreditAvailability service có trách nhiệm nghiệp vụ rõ ràng.

## 22. Khi nào không nên đơn giản hóa?

Một số abstraction trông có vẻ dư thừa nhưng lại bảo vệ boundary quan trọng.

Không nên vội gộp khi:
- interface là port giữa application và hệ thống ngoài;
- mapper chuyển đổi semantics giữa hai bounded context;
- DTO bảo vệ contract công khai;
- policy có nhiều biến thể đã tồn tại;
- factory bảo vệ điều kiện tạo aggregate;
- repository giữ contract truy xuất aggregate;
- adapter che giấu giao thức hoặc framework;
- một process manager quản lý workflow dài;
- một module cần công bố API ổn định cho consumer độc lập.

Cũng không nên xóa Value Object chỉ vì nó có ít dòng. CustomerId có thể chỉ chứa một UUID nhưng ngăn truyền nhầm OrderId. Money có thể có hai field nhưng bảo vệ currency và phép toán. Kích thước class không đo được giá trị mô hình.

## 23. Code review: hỏi về lý do tồn tại của từng abstraction

Một review hữu ích có thể hỏi:

1. Lớp này đại diện cho khái niệm hoặc trách nhiệm nào?
2. Ai là consumer của nó?
3. Nó sở hữu quy tắc hoặc invariant nào?
4. Nó cô lập dependency hoặc contract nào?
5. Điều gì sẽ khó hơn nếu gộp nó với caller?
6. Điều gì sẽ khó hơn nếu xóa nó?
7. Nó có khả năng thay đổi độc lập không?
8. Có implementation hoặc policy khác thực sự cần không?
9. Tên có giúp người đọc hiểu nghiệp vụ không?
10. Có test nào chứng minh boundary của nó có ý nghĩa không?

Không phải mọi lớp phải trả lời tất cả câu hỏi. Nhưng nếu không có lý do cụ thể, abstraction nên được xem xét lại.

### Một ví dụ review

Đề xuất thêm IOrderFormatter và DefaultOrderFormatter cho một endpoint duy nhất.

Câu hỏi:
- Có nhiều format khác nhau không?
- Format có phải contract bên ngoài không?
- Có cần thay formatter độc lập không?
- Logic format có đủ phức tạp để kiểm thử riêng không?

Nếu chỉ chuyển ba field sang response DTO, mapper hoặc method trong adapter có thể rõ hơn. Nếu hệ thống xuất cùng Order sang JSON, CSV và tài liệu PDF với các policy khác nhau, formatter abstraction có thể hợp lý.

## 24. Dùng test để ngăn abstraction rỗng quay lại

Test nên kiểm tra behavior và boundary, không kiểm tra số lớp.

Một số test hữu ích:
- domain test xác nhận invariant của Aggregate;
- Value Object test xác nhận validation và equality;
- application test xác nhận orchestration;
- adapter test xác nhận mapping và protocol;
- architecture test xác nhận dependency direction nếu dự án cần.

Không cần viết test chỉ để chứng minh một pass-through method gọi method kế tiếp. Nếu method không có contract độc lập, test đó thường chỉ lặp lại implementation.

Architecture test có thể hữu ích để bảo vệ ranh giới module, ví dụ domain không phụ thuộc package web hoặc persistence. Nhưng không nên viết hàng loạt rule cứng cho từng class nếu cấu trúc còn đang khám phá.

## 25. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Tạo nhiều tầng cho một use case đơn giản | Khó lần theo hành vi | Giữ các boundary thực sự có trách nhiệm |
| Mọi class đều phải có interface | Tăng indirection và số kiểu | Tạo interface khi có port, contract hoặc biến thiên |
| Bọc mọi primitive | Nhiều kiểu nhưng không thêm semantics | Tạo Value Object khi có invariant, unit hoặc meaning |
| Mỗi method thành một service class | Khó thấy ownership | Tổ chức theo use case và trách nhiệm |
| Tạo generic CRUD cho mọi aggregate | Ép lifecycle khác nhau vào cùng API | Repository theo aggregate và nhu cầu thực |
| Factory chỉ gọi constructor | Thêm lớp không có quyết định | Dùng constructor/factory method trực tiếp |
| Domain Service cho mọi logic | Domain model mất hành vi tự nhiên | Đặt rule ở Entity/VO khi phù hợp |
| Strategy cho một điều kiện đơn giản | Khó hiểu hơn một nhánh if | Trích xuất khi có biến thể hoặc policy độc lập |
| Event cho mọi field update | Event mất ý nghĩa nghiệp vụ | Chỉ phát fact có consumer hoặc audit purpose |
| DTO cho mọi tầng nội bộ | Mapping lặp và khó bảo trì | Giữ DTO ở boundary có contract riêng |
| Một God Service để giảm số lớp | Trách nhiệm tập trung và khó thay đổi | Chia theo use case, aggregate và boundary |
| Xóa port vì chỉ có một adapter | Application bị gắn với infrastructure | Giữ port nếu nó là boundary có ý nghĩa |
| Tạo plugin system trước nhu cầu | Tăng configuration và failure mode | Bắt đầu với implementation rõ ràng |
| Dùng số dòng làm thước đo chất lượng | Bỏ qua ngữ nghĩa và coupling | Đánh giá lý do tồn tại và chi phí thay đổi |

## 26. Quy trình quyết định có nên thêm một lớp

Trước khi tạo class, interface hoặc pattern mới:

1. **Mô tả vấn đề:** điều gì đang khó hiểu, lặp lại hoặc thay đổi?
2. **Gọi tên trách nhiệm:** thành phần mới sẽ sở hữu quyết định nào?
3. **Xác định consumer:** ai cần sử dụng contract này?
4. **Xác định boundary:** nó tách domain, application, infrastructure hay bounded context nào?
5. **Xác định invariant:** có quy tắc nào được bảo vệ tốt hơn nhờ abstraction này?
6. **Kiểm tra biến thiên:** có nhiều implementation hoặc policy thực tế không?
7. **So sánh với phương án trực tiếp:** một method hoặc một class hiện tại có đủ rõ không?
8. **Đánh giá chi phí:** mapping, indirection, test và tài liệu tăng bao nhiêu?
9. **Thử bằng ví dụ:** người đọc có hiểu use case nhanh hơn không?
10. **Đo lại sau một thay đổi:** abstraction có giúp thay đổi độc lập hay chỉ làm diff lớn hơn?

Nếu câu trả lời chưa rõ, có thể trì hoãn abstraction. Trì hoãn không có nghĩa bỏ qua thiết kế; đó là giữ mô hình nhỏ cho đến khi có bằng chứng cần cấu trúc thêm.

## 27. Checklist rà soát

- [ ] Mỗi lớp có trách nhiệm và lý do tồn tại rõ.
- [ ] Tên lớp diễn đạt khái niệm hoặc vai trò thật.
- [ ] Không có chuỗi pass-through chỉ đổi tên method.
- [ ] Interface nằm ở boundary có ý nghĩa hoặc có biến thiên thực tế.
- [ ] Value Object bảo vệ meaning, equality, unit hoặc invariant.
- [ ] Không tạo wrapper cho mọi primitive theo máy móc.
- [ ] Entity và Aggregate sở hữu lifecycle/invariant phù hợp.
- [ ] Domain Service chỉ chứa rule không thuộc tự nhiên về Entity/VO.
- [ ] Application Service điều phối use case thay vì chứa mọi business rule.
- [ ] Repository tập trung vào Aggregate Root và nhu cầu truy xuất thực.
- [ ] Factory có logic tạo hoặc reconstitution đủ đáng kể.
- [ ] Policy/Strategy/Specification được dùng khi có quy tắc hoặc biến thể thực.
- [ ] DTO và mapper tồn tại ở boundary cần bảo vệ contract hoặc semantics.
- [ ] Domain Event biểu diễn fact nghiệp vụ, không chỉ thông báo update kỹ thuật.
- [ ] Không tạo generic base class chỉ để giảm vài dòng lặp.
- [ ] Không gom mọi thứ vào God Service để giảm số class.
- [ ] Test tập trung vào behavior và boundary có ý nghĩa.
- [ ] Dependency direction được giữ rõ giữa domain, application và infrastructure.
- [ ] Abstraction mới giảm tổng độ phức tạp thay vì chỉ chuyển nó sang nhiều file.
- [ ] Có thể giải thích lợi ích và chi phí của abstraction trong code review.

## Kết luận

DDD không đo chất lượng mô hình bằng số lượng pattern hoặc số class. Một abstraction đáng giữ khi nó diễn đạt một khái niệm, bảo vệ invariant, cô lập boundary, hỗ trợ biến thiên thực tế hoặc làm thay đổi dễ hiểu hơn. Một lớp chỉ chuyển tiếp, wrapper không có semantics hoặc interface được tạo theo nghi thức có thể làm tăng indirection mà không giảm độ phức tạp. Hãy bắt đầu từ ngôn ngữ và quy tắc nghiệp vụ, đặt hành vi ở Entity, Value Object hoặc Domain Service phù hợp, dùng Application Service để điều phối và giữ adapter ở ranh giới kỹ thuật. Khi có bằng chứng về trách nhiệm mới, hãy thêm cấu trúc; khi một lớp không còn lý do tồn tại, hãy gộp nó bằng các bước nhỏ có test bảo vệ behavior.
