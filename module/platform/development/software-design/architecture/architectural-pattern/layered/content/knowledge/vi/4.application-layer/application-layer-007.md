# Tách luồng đọc và luồng ghi khi có nhu cầu thực tế

Trong tầng ứng dụng (Application), luồng ghi thay đổi trạng thái của hệ thống, còn luồng đọc truy xuất và trình bày thông tin hiện có. Khi hai loại thao tác có nhu cầu khác nhau về quy tắc nghiệp vụ, cấu trúc dữ liệu, hiệu năng hoặc khả năng mở rộng, có thể tách chúng thành các ca sử dụng và mô hình riêng. Cách tổ chức này thường được gọi là CQRS (Command Query Responsibility Segregation).

Tách đọc và ghi là một lựa chọn thiết kế, không phải yêu cầu mặc định của mọi kiến trúc phân tầng. Với một ứng dụng CRUD nhỏ, một service và một mô hình dữ liệu chung thường đã đủ rõ ràng. Chỉ nên tăng mức độ tách khi có vấn đề thực tế mà cách tổ chức hiện tại khó giải quyết.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, tầng ứng dụng chịu trách nhiệm điều phối các ca sử dụng. Tách luồng đọc và ghi giúp tầng này thể hiện rõ hành động nào làm thay đổi trạng thái, hành động nào chỉ truy vấn dữ liệu, đồng thời cho phép mỗi luồng có cách triển khai phù hợp.

## 1. Luồng đọc và luồng ghi khác nhau ở đâu?

Một **command** diễn đạt yêu cầu thay đổi trạng thái, ví dụ tạo đơn hàng, xác nhận thanh toán hoặc hủy đơn. Khi xử lý command, ứng dụng cần thực thi các quy tắc nghiệp vụ, kiểm tra trạng thái hiện tại và lưu thay đổi một cách nhất quán.

Một **query** diễn đạt yêu cầu lấy thông tin, ví dụ xem chi tiết đơn hàng, tìm đơn theo trạng thái hoặc hiển thị tổng hợp doanh thu. Query không được làm thay đổi trạng thái nghiệp vụ. Nó có thể đọc một hoặc nhiều nguồn dữ liệu và định dạng kết quả theo nhu cầu của màn hình hoặc báo cáo.

| Khía cạnh | Luồng ghi (Command) | Luồng đọc (Query) |
|---|---|---|
| Mục đích | Thay đổi trạng thái | Trả về thông tin |
| Ví dụ | Đặt hàng, xác nhận, hủy | Xem chi tiết, tìm kiếm, thống kê |
| Trọng tâm | Quy tắc, bất biến, giao dịch | Bộ lọc, sắp xếp, phân trang, hình dạng dữ liệu |
| Đầu ra thường gặp | Kết quả xử lý, mã tài nguyên, trạng thái thành công | DTO hoặc read model phục vụ client |
| Rủi ro chính | Ghi sai trạng thái, vi phạm quy tắc, mất cập nhật | Dữ liệu thiếu, truy vấn chậm, kết quả cũ |

Quy tắc quan trọng là query chỉ đọc. Nếu một thao tác vừa trả dữ liệu vừa thay đổi trạng thái, cần xem lại ý nghĩa của nó và tách phần thay đổi thành command nếu phù hợp. Chẳng hạn, “đánh dấu thông báo đã đọc” là command vì nó cập nhật trạng thái; “liệt kê thông báo chưa đọc” là query.

## 2. CQRS không nhất thiết có hai cơ sở dữ liệu

CQRS có thể được áp dụng ở nhiều mức:

- **Tách ở mức use case:** có command handler và query handler riêng, nhưng vẫn dùng chung cơ sở dữ liệu và có thể dùng chung một số mô hình.
- **Tách mô hình đọc và ghi:** luồng ghi làm việc với mô hình miền để bảo vệ quy tắc; luồng đọc dùng projection hoặc read model được thiết kế theo màn hình, báo cáo hay nhu cầu truy vấn.
- **Tách cả kho dữ liệu:** luồng ghi và luồng đọc có thể dùng các kho lưu trữ khác nhau, thường khi tải, cấu trúc hoặc yêu cầu mở rộng thực sự đòi hỏi.

CQRS không đồng nghĩa với microservices, event sourcing hoặc bắt buộc có hai database. Có thể bắt đầu bằng hai nhóm ca sử dụng trong cùng một ứng dụng Spring Boot, cùng một database quan hệ. Cách làm này đã tạo ra ranh giới trách nhiệm rõ hơn mà không phải trả chi phí vận hành của một hệ thống phân tán.

~~~mermaid
flowchart TB
    Client[Client / Presentation]
    subgraph Application[Tầng ứng dụng]
      C[Command handler]
      Q[Query handler]
    end
    subgraph Data[Hạ tầng dữ liệu]
      W[(Write model / database)]
      R[(Read model / projection)]
    end
    Client -->|Command| C
    Client -->|Query| Q
    C -->|Kiểm tra quy tắc và ghi| W
    Q -->|Truy vấn và tổng hợp| R
~~~

Sơ đồ thể hiện cách phân tách khái niệm. Trong triển khai đơn giản, Write model và Read model có thể cùng nằm trong một database; chúng không nhất thiết là hai máy chủ hay hai cụm dữ liệu riêng biệt.

## 3. Khi nào nên cân nhắc tách?

Một số dấu hiệu thực tế cho thấy việc tách có thể đem lại lợi ích:

- Một màn hình cần dữ liệu tổng hợp từ nhiều bảng hoặc nhiều miền, trong khi luồng ghi cần mô hình giàu hành vi để bảo vệ quy tắc.
- Truy vấn đọc có nhiều bộ lọc, sắp xếp, phân trang hoặc phép tổng hợp, khiến service ghi trở nên khó đọc và khó bảo trì.
- Tải đọc cao hơn nhiều so với tải ghi và cần tối ưu hoặc mở rộng hai phía theo cách khác nhau.
- Nhiều client cần các hình dạng dữ liệu khác nhau, nhưng không nên làm mô hình nghiệp vụ phụ thuộc vào từng màn hình.
- Báo cáo hoặc tìm kiếm cần một cấu trúc dữ liệu chuyên biệt mà không phù hợp để biểu diễn bằng entity ghi.

Ví dụ, hệ thống bán hàng có thể cần màn hình tổng quan đơn hàng hiển thị mã đơn, tên khách, số dòng hàng, tổng tiền và trạng thái. Dữ liệu này có thể được tổng hợp bằng một truy vấn projection. Trong khi đó, luồng đặt hàng cần kiểm tra sản phẩm còn được bán, số lượng hợp lệ, giá tại thời điểm đặt và các quy tắc liên quan. Hai nhu cầu có hình dạng và mục tiêu khác nhau.

Không nên tách chỉ vì dự án có nhiều bảng, vì một service có cả phương thức đọc và ghi, hoặc vì CQRS là một mẫu kiến trúc phổ biến. Nếu truy vấn đơn giản và cùng một mô hình đáp ứng tốt cả hai phía, việc tách thêm handler, DTO và adapter có thể chỉ làm tăng mã khung.

## 4. Ví dụ Java/Spring: tách use case đọc và ghi, dùng chung database

Giả sử ứng dụng quản lý đơn hàng. Luồng ghi đặt hàng cần thực thi nghiệp vụ và lưu một Order. Luồng đọc lấy bản tóm tắt đơn hàng theo định dạng mà màn hình cần.

### Luồng ghi: command xử lý quy tắc nghiệp vụ

Command mô tả ý định của người gọi:

~~~java
public record PlaceOrderCommand(
        UUID customerId,
        UUID productId,
        int quantity
) {}
~~~

Use case ghi điều phối nghiệp vụ thông qua mô hình miền và repository:

~~~java
public interface PlaceOrderUseCase {
    UUID handle(PlaceOrderCommand command);
}

@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductRepository products;
    private final OrderRepository orders;

    public PlaceOrderService(
            ProductRepository products,
            OrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Override
    @Transactional
    public UUID handle(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new InvalidOrderQuantityException();
        }

        Product product = products.findById(command.productId())
                .orElseThrow(ProductNotFoundException::new);

        Order order = Order.place(
                command.customerId(),
                product,
                command.quantity()
        );

        orders.save(order);
        return order.getId();
    }
}
~~~

Đây là ví dụ minh họa; Order.place chịu trách nhiệm áp dụng các quy tắc miền thích hợp, còn repository lưu aggregate theo thiết kế của ứng dụng. Giao dịch bao quanh thao tác ghi để các thay đổi liên quan được commit hoặc rollback cùng nhau. Command handler không cần biết JSON, HTTP status hay cấu trúc trang web.

### Luồng đọc: query trả về read model

Màn hình có thể cần một cấu trúc gọn hơn entity miền:

~~~java
public record OrderSummary(
        UUID orderId,
        String customerName,
        BigDecimal total,
        String status,
        Instant createdAt
) {}

public interface GetOrderSummaryUseCase {
    Optional<OrderSummary> findById(UUID orderId);
}
~~~

Query handler sử dụng một repository đọc chuyên biệt:

~~~java
public interface OrderReadRepository {
    Optional<OrderSummary> findSummaryById(UUID orderId);
}

@Service
public class GetOrderSummaryService
        implements GetOrderSummaryUseCase {
    private final OrderReadRepository readRepository;

    public GetOrderSummaryService(OrderReadRepository readRepository) {
        this.readRepository = readRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<OrderSummary> findById(UUID orderId) {
        return readRepository.findSummaryById(orderId);
    }
}
~~~

Adapter đọc có thể dùng Spring Data JPA projection, JPQL, JDBC hoặc công cụ truy vấn phù hợp. Ví dụ, với Spring Data JPA, projection chỉ lấy các trường cần cho màn hình:

~~~java
public interface OrderSummaryProjection {
    UUID getOrderId();
    String getCustomerName();
    BigDecimal getTotal();
    String getStatus();
    Instant getCreatedAt();
}

public interface SpringDataOrderReadRepository
        extends Repository<OrderJpaEntity, UUID> {

    @Query("""
        select o.id as orderId,
               c.name as customerName,
               o.total as total,
               o.status as status,
               o.createdAt as createdAt
          from OrderJpaEntity o
          join o.customer c
         where o.id = :orderId
        """)
    Optional<OrderSummaryProjection> findSummary(
            @Param("orderId") UUID orderId);
}
~~~

Một adapter thuộc Infrastructure có thể chuyển projection thành OrderSummary theo hợp đồng mà Application cần. Ở đây, luồng đọc không cần tải toàn bộ aggregate rồi duyệt từng dòng hàng chỉ để tạo một màn hình tóm tắt. Truy vấn lấy đúng dữ liệu cần thiết và tránh đưa chi tiết JPA ra ngoài adapter.

Các lớp trong ví dụ là những hợp đồng và thành phần minh họa; dự án thực tế cần định nghĩa entity, quan hệ và mapping theo schema của mình. Annotation @Transactional(readOnly = true) thể hiện ý định giao dịch chỉ đọc và có thể giúp framework hoặc database tối ưu trong một số cấu hình; nó không thay thế việc bảo đảm query không thực hiện thao tác ghi.

### Presentation gọi hai ca sử dụng riêng

Controller có thể gọi use case ghi để đặt hàng và use case đọc để lấy chi tiết:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;
    private final GetOrderSummaryUseCase getOrderSummary;

    public OrderController(
            PlaceOrderUseCase placeOrder,
            GetOrderSummaryUseCase getOrderSummary) {
        this.placeOrder = placeOrder;
        this.getOrderSummary = getOrderSummary;
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody PlaceOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal) {
        UUID orderId = placeOrder.handle(new PlaceOrderCommand(
                principal.customerId(),
                request.productId(),
                request.quantity()
        ));

        return ResponseEntity
                .created(URI.create("/api/orders/" + orderId))
                .build();
    }

    @GetMapping("/{orderId}")
    public ResponseEntity<OrderSummaryResponse> get(
            @PathVariable UUID orderId) {
        return getOrderSummary.findById(orderId)
                .map(summary -> ResponseEntity.ok(
                        OrderSummaryResponse.from(summary)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Presentation chỉ chuyển request thành command hoặc query, gọi use case và ánh xạ kết quả. Application vẫn điều phối công việc; Domain bảo vệ quy tắc; Infrastructure cung cấp cách đọc và ghi cụ thể. Đây là cách tách có thể triển khai ngay trong một ứng dụng phân tầng đơn khối.

## 5. Mô hình đọc chuyên biệt và tính nhất quán dữ liệu

Khi query cần cấu trúc khác với mô hình ghi, có thể tạo read model. Ví dụ, một màn hình tổng quan cần tổng tiền theo ngày và số lượng đơn theo trạng thái. Thay vì bắt domain aggregate phục vụ trực tiếp các phép tổng hợp, query adapter có thể chạy SQL tổng hợp hoặc đọc từ một bảng projection.

Có hai cách cập nhật read model thường gặp:

| Cách cập nhật | Đặc điểm | Đánh đổi |
|---|---|---|
| Đọc trực tiếp hoặc truy vấn projection trên cùng database | Dữ liệu phản ánh trạng thái đã commit của database tại thời điểm truy vấn | Truy vấn phức tạp có thể ảnh hưởng tải database; cần thiết kế index và câu truy vấn |
| Cập nhật read model bất đồng bộ từ sự kiện | Có thể tối ưu kho đọc riêng và tách tải đọc khỏi kho ghi | Read model có độ trễ; cần xử lý sự kiện lặp, sai thứ tự, lỗi và xây dựng lại projection |

Nếu cả thao tác ghi và cập nhật projection đều nằm trong cùng database và cùng transaction, có thể giữ tính nhất quán mạnh cho lần đọc tiếp theo sau khi transaction commit. Tuy nhiên, nếu projection được cập nhật bất đồng bộ qua message broker hoặc một database khác, client có thể chưa nhìn thấy thay đổi ngay sau khi command thành công. Đây là **eventual consistency** (nhất quán cuối cùng).

Ví dụ, người dùng vừa đặt hàng thành công rồi lập tức mở trang danh sách đơn. Nếu trang đọc từ projection bất đồng bộ, đơn hàng mới có thể chưa xuất hiện trong một khoảng ngắn. Giao diện và API cần có hành vi phù hợp: có thể trả mã đơn hàng ngay sau khi ghi, cho phép truy vấn trạng thái xử lý, hoặc thông báo rằng danh sách đang được cập nhật. Không nên giả định hai kho dữ liệu đã đồng bộ tức thời.

Khi dùng sự kiện để cập nhật read model, cần tính đến khả năng gửi lại. Một consumer có thể nhận cùng sự kiện nhiều lần, vì vậy thao tác cập nhật projection nên idempotent (có thể thực hiện lặp mà không làm sai kết quả). Nếu ứng dụng phải bảo đảm sự kiện không bị mất giữa lúc commit database và gửi message, có thể cân nhắc Transactional Outbox: ghi thay đổi nghiệp vụ và bản ghi sự kiện trong cùng transaction, sau đó tiến trình riêng chuyển sự kiện ra broker. Đây là giải pháp cho bài toán phân phối sự kiện, không phải thành phần bắt buộc của mọi triển khai CQRS.

## 6. Các nguyên tắc cần giữ khi tách hai luồng

**Command phải bảo vệ quy tắc nghiệp vụ.** Không cho phép luồng ghi bỏ qua Domain chỉ vì query model đã có sẵn dữ liệu. Ví dụ, số lượng tồn kho hiển thị trên màn hình có thể đã cũ; khi đặt hàng, hệ thống vẫn phải kiểm tra và cập nhật tồn kho bằng cơ chế an toàn trong luồng ghi.

**Query không được tạo tác dụng phụ nghiệp vụ.** Một query có thể ghi log truy cập hoặc cập nhật metric vận hành, nhưng không nên thay đổi trạng thái đơn hàng, trừ khi thao tác được xác định rõ là command riêng.

**Read model không phải nguồn chân lý cho mọi quyết định ghi.** Projection có thể thiếu trường hoặc cập nhật chậm. Quyết định nghiệp vụ quan trọng cần dựa trên nguồn dữ liệu và giao dịch có thẩm quyền của luồng ghi.

**Hợp đồng đọc nên phục vụ nhu cầu thực.** Một màn hình có thể cần OrderSummary, một báo cáo cần DailySalesReport. Không nhất thiết ép mọi query trả về cùng một entity hoặc tạo một DTO khổng lồ cho tất cả client.

**Giữ ranh giới tầng rõ ràng.** Application định nghĩa use case và hợp đồng mà nó cần. Infrastructure triển khai repository hoặc adapter đọc/ghi. Presentation không truy cập trực tiếp database và không tự ghép dữ liệu từ nhiều repository để thay thế một query use case.

**Không phân tán hệ thống sớm.** Có thể tách interface, handler và projection trong cùng một module trước. Chỉ cân nhắc database đọc riêng, broker hoặc dịch vụ độc lập khi số liệu tải, yêu cầu sẵn sàng hay nhu cầu sở hữu cho thấy lợi ích rõ ràng.

## 7. Kiểm thử riêng luồng ghi và luồng đọc

Vì hai luồng có mục tiêu khác nhau, chiến lược kiểm thử cũng nên khác nhau.

- **Command/application unit test:** xác minh handler gọi đúng repository, áp dụng các bước nghiệp vụ cần thiết, trả kết quả phù hợp và xử lý lỗi khi dữ liệu không hợp lệ hoặc tài nguyên không tồn tại.
- **Domain unit test:** kiểm tra bất biến, chuyển trạng thái và các quy tắc quan trọng của aggregate mà không cần database.
- **Query test:** xác minh bộ lọc, sắp xếp, phân trang, phép tổng hợp và hình dạng read model.
- **Repository integration test:** chạy adapter với database tương thích để phát hiện lỗi SQL/JPQL, mapping, index hoặc hành vi transaction.
- **Projection/consumer test:** nếu cập nhật bất đồng bộ, xác minh sự kiện được áp dụng đúng, xử lý lặp an toàn và projection có thể phục hồi hoặc xây dựng lại.

Ví dụ, command test cần chứng minh đặt hàng với số lượng không hợp lệ không lưu đơn hàng. Query test cần chứng minh findSummaryById trả đúng các trường mà API công bố. Một test end-to-end có thể xác minh toàn bộ đường đi, nhưng không thay thế các kiểm thử tập trung vào quy tắc và truy vấn.

## 8. Những chi phí và lỗi thiết kế thường gặp

Tách đọc và ghi tạo ra thêm các hợp đồng, handler, DTO, repository và đôi khi thêm cơ chế đồng bộ. Nếu tách cả database, nhóm còn phải vận hành backup, giám sát, triển khai schema, phục hồi dữ liệu và xử lý độ trễ đồng bộ cho kho đọc.

Một số lỗi thường gặp:

- Tạo command handler và query handler riêng nhưng cả hai chỉ chuyển tiếp qua nhiều lớp không mang thêm trách nhiệm.
- Dùng read model đã cũ để quyết định ghi, dẫn đến vi phạm bất biến khi dữ liệu thay đổi đồng thời.
- Cho rằng transaction trên database ghi tự động bao phủ message broker hoặc database đọc khác.
- Không xử lý sự kiện lặp, sai thứ tự hoặc lỗi khi consumer cập nhật projection.
- Tạo một read model mới cho mọi màn hình dù truy vấn trực tiếp vẫn đủ nhanh và đơn giản.
- Đưa logic nghiệp vụ vào query vì query đang có sẵn các dữ liệu cần thiết.

Khi phát hiện những vấn đề này, cần xem lại mức độ tách. CQRS tốt phải làm rõ trách nhiệm hoặc giải quyết một nhu cầu có thể quan sát được; nếu chỉ tăng số lớp và số hệ thống cần vận hành, lợi ích của nó chưa được chứng minh.

## 9. Cách lựa chọn mức độ tách phù hợp

Có thể dùng các bước sau để quyết định:

1. Bắt đầu bằng cách phân biệt phương thức thay đổi trạng thái với phương thức truy vấn trong Application service.
2. Khi hai luồng có nhu cầu thay đổi khác nhau, tách command use case và query use case thành các hợp đồng riêng.
3. Nếu mô hình ghi không phù hợp với nhu cầu hiển thị hoặc báo cáo, tạo projection/read model riêng, trước tiên có thể vẫn nằm trong cùng database.
4. Chỉ tách kho dữ liệu hoặc cập nhật bất đồng bộ khi có lý do rõ ràng về tải, cấu trúc dữ liệu, khả năng mở rộng hoặc yêu cầu vận hành.
5. Đo độ trễ đọc, thời gian truy vấn, tải database và tỷ lệ lỗi để kiểm chứng lợi ích sau khi thay đổi.

Không có quy tắc rằng mọi ứng dụng phân tầng đều phải dùng CQRS. Một ứng dụng nhỏ có thể dùng chung mô hình và database, với các phương thức đọc/ghi rõ ràng trong Application. Một hệ thống lớn hơn có thể cần read model chuyên biệt hoặc kho đọc độc lập. Mức độ tách nên tương xứng với độ phức tạp thực tế.

Tách luồng đọc và ghi có ý nghĩa khi mỗi luồng cần cách tổ chức khác nhau để phục vụ tốt mục tiêu của nó: luồng ghi bảo vệ quy tắc và tính nhất quán của trạng thái, còn luồng đọc trả dữ liệu hiệu quả theo nhu cầu truy vấn. Tầng ứng dụng là nơi thể hiện hai loại ca sử dụng này; các tầng Domain và Infrastructure tiếp tục đảm nhiệm quy tắc nghiệp vụ và chi tiết kỹ thuật tương ứng.

