# Giữ nghiệp vụ độc lập với HTTP, ORM và cấu trúc bảng; không ép áp dụng DDD

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Tầng nghiệp vụ**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, trong đó mỗi phần có trách nhiệm rõ ràng và cộng tác qua những ranh giới có chủ đích. Trọng tâm ở đây là giữ các quy tắc nghiệp vụ có thể hiểu và kiểm tra được mà không bị chi phối bởi giao thức HTTP, thư viện ORM hay cách dữ liệu được chia thành bảng.

Giữ nghiệp vụ độc lập không có nghĩa là phải xây dựng một mô hình miền lớn, áp dụng đầy đủ Domain-Driven Design (DDD), hoặc loại bỏ mọi thư viện khỏi dự án. Mục tiêu thực tế là đặt quyết định nghiệp vụ ở nơi phù hợp, để thay đổi ở API hoặc cơ sở dữ liệu không tự động buộc phải thay đổi quy tắc của doanh nghiệp.

## 1. Tầng nghiệp vụ chịu trách nhiệm về điều gì?

Tầng nghiệp vụ biểu diễn những quy tắc và khái niệm quyết định phần mềm phải làm gì trong lĩnh vực đang giải quyết. Ví dụ trong hệ thống bán hàng:

- Một đơn hàng không được xác nhận nếu không có dòng hàng hợp lệ.
- Số lượng đặt phải lớn hơn không và không vượt quá giới hạn được phép.
- Khách hàng thuộc một hạng nhất định có thể được hưởng chính sách chiết khấu.
- Đơn hàng đã giao không được quay lại trạng thái chờ xác nhận.
- Tổng tiền phải được tính theo quy tắc làm tròn và tiền tệ đã thống nhất.

Các quy tắc này vẫn đúng dù người dùng gửi yêu cầu qua REST, giao diện dòng lệnh, tác vụ chạy theo lịch hay một message consumer. Chúng cũng không thay đổi chỉ vì nhóm phát triển chuyển từ PostgreSQL sang một hệ quản trị khác, đổi tên bảng hoặc thay Hibernate bằng một cách truy cập dữ liệu khác.

Trong kiến trúc phân tầng, có thể phân biệt các trách nhiệm như sau:

| Phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Presentation | Tiếp nhận và trả dữ liệu theo giao thức bên ngoài | Spring MVC controller, HTTP request/response |
| Application | Điều phối một ca sử dụng và xác định ranh giới giao dịch | Xử lý yêu cầu đặt hàng, gọi nghiệp vụ và lưu kết quả |
| Business/domain | Quy tắc, chính sách và trạng thái nghiệp vụ | Tính chiết khấu, xác nhận đơn hàng |
| Data access/infrastructure | Đọc ghi dữ liệu và tích hợp kỹ thuật | Spring Data JPA, JDBC, HTTP client |

Trong một ứng dụng nhỏ, application và business có thể nằm trong cùng một package hoặc một vài lớp service. Bảng trên mô tả trách nhiệm logic, không quy định số package, số module hay số tiến trình phải có.

Một cách kiểm tra hữu ích là hỏi: “Nếu ngày mai thay giao diện HTTP hoặc cách lưu dữ liệu, quy tắc này có còn giữ nguyên không?” Nếu câu trả lời là có, quy tắc đó thường thuộc phần nghiệp vụ.

## 2. Độc lập với HTTP: giao thức không quyết định quy tắc

HTTP là chi tiết của cách hệ thống giao tiếp với client. Controller nên biết về URL, method, header, mã trạng thái, định dạng JSON và cách chuyển lỗi thành phản hồi. Tầng nghiệp vụ nên biết về đơn hàng, khách hàng, số tiền, trạng thái và chính sách.

Ví dụ, một request có thể có cấu trúc:

```java
public record CreateOrderRequest(
        String customerId,
        List<OrderLineRequest> lines
) {}

public record OrderLineRequest(
        String productCode,
        int quantity
) {}
```

Đây là DTO dành cho hợp đồng HTTP. Nó có thể thay đổi vì API cần đổi tên trường, hỗ trợ một phiên bản mới hoặc bổ sung thông tin chỉ phục vụ giao diện. Không nên để quy tắc nghiệp vụ phụ thuộc trực tiếp vào lớp request này.

Controller chuyển dữ liệu giao thức thành đầu vào mà ca sử dụng hiểu được:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderService placeOrder;

    OrderController(PlaceOrderService placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        var command = new PlaceOrderCommand(
                request.customerId(),
                request.lines().stream()
                        .map(line -> new PlaceOrderLine(
                                line.productCode(),
                                line.quantity()))
                        .toList());

        var result = placeOrder.handle(command);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderResponse(result.orderId()));
    }
}
```

Ví dụ rút gọn này cho thấy controller chuyển đổi dữ liệu và chọn phản hồi HTTP. Phần quyết định có được đặt hàng hay không nằm trong ca sử dụng và nghiệp vụ. Nếu cùng hành động được gọi từ tác vụ nền, tác vụ đó có thể tạo cùng loại command và gọi cùng ca sử dụng mà không cần giả lập một HTTP request.

Một số dấu hiệu nghiệp vụ đang bị gắn vào HTTP:

- Lớp nghiệp vụ nhận `HttpServletRequest`, trả về `ResponseEntity` hoặc dùng mã trạng thái HTTP để quyết định kết quả.
- Quy tắc đặt hàng chỉ được kiểm tra bằng annotation hoặc validation trong controller, nên một luồng gọi khác có thể bỏ qua quy tắc.
- Ngoại lệ nghiệp vụ trực tiếp kế thừa hoặc phụ thuộc vào kiểu ngoại lệ của Spring MVC.
- Mô hình nghiệp vụ chứa tên trường được chọn chỉ vì cách client gửi JSON.

Validation ở biên HTTP vẫn cần thiết. Chẳng hạn, kiểm tra JSON có đúng kiểu, trường bắt buộc có được gửi hay không, hoặc chuỗi có đúng định dạng. Nhưng những bất biến quan trọng như số lượng phải dương, đơn hàng phải có ít nhất một dòng hoặc trạng thái hiện tại có cho phép xác nhận hay không cần được bảo vệ ở nơi thực thi nghiệp vụ. Kiểm tra ở biên giúp phản hồi sớm và thân thiện; kiểm tra trong nghiệp vụ bảo vệ quy tắc cho mọi đường gọi.

Lỗi cũng cần được chuyển đổi tại ranh giới. Nghiệp vụ có thể biểu diễn tình huống `OrderCannotBeConfirmed` hoặc `InsufficientInventory`. Controller hoặc một exception handler quyết định tình huống đó tương ứng với HTTP 409, 422 hay phản hồi khác theo hợp đồng API. Không nên để domain quyết định mã HTTP.

## 3. Độc lập với ORM: mô hình nghiệp vụ không phải bản sao của entity lưu trữ

ORM như Hibernate/JPA giúp ánh xạ đối tượng Java với dữ liệu quan hệ. Nó cung cấp annotation, quan hệ, cơ chế tải dữ liệu, lifecycle callback và theo dõi thay đổi. Những khả năng đó phục vụ việc lưu trữ; chúng không nhất thiết là cách tốt nhất để biểu diễn quy tắc nghiệp vụ.

Một entity JPA có thể trông như sau:

```java
@Entity
@Table(name = "sales_order")
class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "customer_code", nullable = false)
    private String customerCode;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLineJpaEntity> lines = new ArrayList<>();

    protected OrderJpaEntity() {
        // Constructor dành cho JPA
    }
}
```

Entity trên có những chi tiết cần cho ORM: tên bảng, tên cột, quan hệ và constructor phù hợp với cách framework khởi tạo đối tượng. Những chi tiết ấy có thể thay đổi khi schema hoặc cách lưu trữ thay đổi.

Mô hình nghiệp vụ có thể biểu diễn cùng khái niệm bằng kiểu Java thông thường:

```java
public final class Order {
    private final UUID id;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public Order(UUID id, List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException(
                    "Đơn hàng phải có ít nhất một dòng");
        }
        this.id = id;
        this.lines = new ArrayList<>(lines);
        this.status = OrderStatus.DRAFT;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Chỉ đơn hàng nháp mới được xác nhận");
        }
        status = OrderStatus.CONFIRMED;
    }

    public UUID id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }
}
```

Lớp `Order` tập trung vào trạng thái và hành vi có ý nghĩa nghiệp vụ. Nó không cần biết bảng tên gì, cột nào là khóa ngoại, Hibernate tải collection theo chiến lược nào hay dữ liệu được lưu bằng SQL ra sao.

Khi hai mô hình có mục đích khác nhau, một adapter hoặc mapper ở ranh giới lưu trữ chuyển đổi giữa chúng. Ví dụ:

```java
@Repository
class JpaOrderStore implements OrderStore {
    private final SpringDataOrderRepository repository;
    private final OrderPersistenceMapper mapper;

    JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderPersistenceMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(UUID id) {
        return repository.findById(id).map(mapper::toDomain);
    }
}
```

`OrderStore` là hợp đồng mà phần gọi cần dùng; `JpaOrderStore` là một cách triển khai hợp đồng bằng Spring Data JPA. Vị trí đặt interface phụ thuộc cách tổ chức module và hướng phụ thuộc của ứng dụng. Trong cấu trúc cần cô lập nghiệp vụ, interface thường được đặt ở phía application hoặc business, còn adapter JPA nằm ở infrastructure. Với một ứng dụng đơn giản hơn, có thể dùng repository của tầng dữ liệu trực tiếp ở application service mà vẫn giữ quy tắc nghiệp vụ khỏi phụ thuộc entity JPA.

Không phải dự án nào cũng cần tạo hai lớp mô hình cho mọi bảng. Nếu đối tượng chỉ là dữ liệu CRUD đơn giản, không có hành vi hoặc quy tắc đáng kể và vòng đời của API với schema gần như giống nhau, dùng JPA entity trong application service có thể là lựa chọn chấp nhận được. Khi làm vậy, cần nhận thức rằng thay đổi ORM hoặc schema có thể lan rộng hơn.

Các dấu hiệu cần cân nhắc tách mô hình:

- Entity có nhiều annotation và quan hệ ORM khiến việc đọc quy tắc nghiệp vụ khó khăn.
- Một thay đổi tên cột hoặc cấu trúc bảng buộc phải sửa nhiều nơi không liên quan đến quy tắc.
- API vô tình trả trực tiếp entity, làm lộ trường nội bộ hoặc quan hệ lazy.
- Việc tạo đối tượng nghiệp vụ đòi hỏi trạng thái hợp lệ nhưng entity có thể được khởi tạo ở trạng thái thiếu dữ liệu.
- Cùng một nghiệp vụ được dùng bởi nhiều adapter, ví dụ REST API và message consumer.

Cần chú ý rằng gọi getter của quan hệ lazy trong lúc chuyển đổi có thể phát sinh truy vấn bổ sung hoặc lỗi khi session đã đóng. Mapper nên làm việc với dữ liệu đã được tải phù hợp với ca sử dụng; không nên vô tình biến việc ánh xạ thành một chuỗi truy vấn không kiểm soát.

## 4. Độc lập với cấu trúc bảng: lưu trữ là cách biểu diễn dữ liệu

Mô hình quan hệ được thiết kế theo các yêu cầu lưu trữ như khóa chính, khóa ngoại, chỉ mục, chuẩn hóa, hiệu năng truy vấn và tính toàn vẹn dữ liệu. Mô hình nghiệp vụ được thiết kế theo khái niệm và quy tắc của lĩnh vực. Hai mô hình có thể tương đồng, nhưng không có nghĩa phải giống nhau.

Ví dụ, nghiệp vụ có thể xem một địa chỉ giao hàng là một giá trị gồm đường, phường, thành phố và mã bưu chính. Cơ sở dữ liệu có thể lưu địa chỉ trong một bảng riêng, trong các cột của bảng đơn hàng hoặc trong một cấu trúc JSON. Việc chọn cách lưu là quyết định kỹ thuật. Quy tắc “địa chỉ giao hàng phải có đủ thông tin để vận chuyển” thuộc nghiệp vụ.

Một số thay đổi lưu trữ không nên làm thay đổi quy tắc:

- Đổi tên bảng hoặc tên cột để thống nhất quy ước.
- Tách một bảng lớn thành nhiều bảng hoặc gộp một số bảng.
- Thêm chỉ mục, khóa ngoại hoặc cột phục vụ truy vấn.
- Chuyển một trường từ kiểu chuỗi sang kiểu số hoặc kiểu ngày trong schema, sau khi có chuyển đổi phù hợp ở adapter.
- Chuyển từ một cơ sở dữ liệu quan hệ sang một hệ lưu trữ khác.

Trong thực tế, thay đổi schema vẫn có thể ảnh hưởng đến cách dữ liệu được truy vấn, transaction hoặc đồng bộ. Độc lập không có nghĩa là không cần sửa adapter, migration hay kiểm thử tích hợp. Ý nghĩa là thay đổi kỹ thuật được xử lý ở phần chịu trách nhiệm lưu trữ, trong khi quy tắc nghiệp vụ chỉ thay đổi khi yêu cầu kinh doanh thay đổi.

Cũng không nên biến domain thành một bản sao máy móc của lược đồ quan hệ. Một bảng có thể được chia thành nhiều đối tượng phục vụ các quy tắc khác nhau; ngược lại, một khái niệm nghiệp vụ có thể được lưu qua nhiều bảng. Mối quan hệ giữa mô hình và schema là một quyết định ánh xạ, không phải quan hệ một-một bắt buộc.

## 5. DDD có thể hữu ích, nhưng không phải điều kiện để có tầng nghiệp vụ

Domain-Driven Design là một tập hợp tư duy và kỹ thuật giúp nhóm hiểu sâu lĩnh vực, thống nhất ngôn ngữ và mô hình hóa các quy tắc phức tạp. Một số khái niệm thường gặp gồm:

- **Ubiquitous language:** ngôn ngữ chung mà chuyên gia nghiệp vụ và nhóm phát triển cùng sử dụng.
- **Entity:** đối tượng có danh tính và vòng đời.
- **Value object:** đối tượng được xác định bởi giá trị, thường bất biến.
- **Aggregate:** ranh giới nhất quán cho một nhóm đối tượng và các thay đổi của chúng.
- **Domain service:** nơi đặt quy tắc nghiệp vụ không tự nhiên thuộc về một entity hoặc value object cụ thể.
- **Repository:** hợp đồng truy cập và khôi phục đối tượng nghiệp vụ.

Những kỹ thuật này có thể giúp khi lĩnh vực có nhiều quy tắc, trạng thái và ngoại lệ; nhiều nhóm cần thống nhất ý nghĩa; hoặc các quy trình thay đổi thường xuyên nhưng phải giữ bất biến chặt chẽ. DDD không đồng nghĩa với việc tạo thật nhiều class, interface hay repository cho mọi bảng.

Một ứng dụng vẫn có tầng nghiệp vụ hữu ích mà không cần áp dụng đầy đủ DDD. Có thể chọn mức độ phù hợp:

| Tình huống | Cách tổ chức có thể phù hợp |
|---|---|
| CRUD nhỏ, quy tắc ít, dữ liệu đơn giản | Service điều phối cùng DTO/entity; kiểm tra các quy tắc cần thiết |
| Nghiệp vụ vừa phải, có chính sách dùng chung | Application service điều phối và các lớp nghiệp vụ thuần Java cho chính sách |
| Nghiệp vụ phức tạp, nhiều trạng thái và bất biến | Mô hình domain giàu hành vi; chọn lọc entity, value object, aggregate và domain service |
| Nhiều miền nghiệp vụ hoặc nhiều nhóm độc lập | Có thể xem xét bounded context và ranh giới module rõ ràng |

Không nên áp dụng aggregate, domain event hay repository abstraction chỉ vì một tài liệu kiến trúc đề cập đến chúng. Mỗi khái niệm thêm vào đều có chi phí: cần hiểu, triển khai, kiểm thử và duy trì. Chỉ sử dụng khi nó giải quyết một vấn đề thực tế.

Ngược lại, không cần DDD không có nghĩa là để nghiệp vụ trôi vào controller hoặc repository. Một lớp service thông thường vẫn có thể chứa quy tắc nghiệp vụ rõ ràng, có tên dễ hiểu và được kiểm thử độc lập. Điều quan trọng là tách quyết định kinh doanh khỏi chi tiết giao thức và lưu trữ ở mức phù hợp.

## 6. Ví dụ: chính sách chiết khấu không phụ thuộc Spring hay JPA

Giả sử cửa hàng áp dụng quy tắc: khách hàng thành viên được giảm 5%; đơn có giá trị từ 500.000 đồng được giảm thêm 2%. Đây là ví dụ minh họa, không phải chính sách chung cho mọi hệ thống.

Có thể viết chính sách bằng Java thuần:

```java
public enum CustomerType {
    REGULAR,
    MEMBER
}

public final class DiscountPolicy {
    private static final BigDecimal MEMBER_RATE =
            new BigDecimal("0.05");
    private static final BigDecimal LARGE_ORDER_RATE =
            new BigDecimal("0.02");
    private static final BigDecimal LARGE_ORDER_THRESHOLD =
            new BigDecimal("500000");

    public BigDecimal payableAmount(
            BigDecimal subtotal,
            CustomerType customerType) {

        Objects.requireNonNull(subtotal, "subtotal");
        Objects.requireNonNull(customerType, "customerType");

        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "Giá trị đơn hàng không được âm");
        }

        BigDecimal rate = BigDecimal.ZERO;

        if (customerType == CustomerType.MEMBER) {
            rate = rate.add(MEMBER_RATE);
        }

        if (subtotal.compareTo(LARGE_ORDER_THRESHOLD) >= 0) {
            rate = rate.add(LARGE_ORDER_RATE);
        }

        return subtotal
                .multiply(BigDecimal.ONE.subtract(rate))
                .setScale(0, RoundingMode.HALF_UP);
    }
}
```

Lớp này không nhận request, không trả response, không gọi repository và không có annotation JPA. Nó nhận dữ liệu có ý nghĩa nghiệp vụ và trả kết quả theo chính sách. Nhóm có thể kiểm thử nó bằng JUnit mà không cần khởi động Spring hoặc kết nối cơ sở dữ liệu.

Một application service có thể điều phối việc dùng chính sách:

```java
public final class CalculateQuoteService {
    private final DiscountPolicy discountPolicy;
    private final ProductCatalog productCatalog;

    public CalculateQuoteService(
            DiscountPolicy discountPolicy,
            ProductCatalog productCatalog) {
        this.discountPolicy = discountPolicy;
        this.productCatalog = productCatalog;
    }

    public QuoteResult calculate(QuoteCommand command) {
        var products = productCatalog.findAll(command.productCodes());

        BigDecimal subtotal = calculateSubtotal(
                command.lines(), products);

        BigDecimal payable = discountPolicy.payableAmount(
                subtotal, command.customerType());

        return new QuoteResult(subtotal, payable);
    }

    // Phần tính subtotal được rút gọn để tập trung vào ranh giới.
}
```

Ở đây application service phối hợp dữ liệu cần thiết và gọi chính sách. `ProductCatalog` có thể là một abstraction mà adapter dữ liệu triển khai. Nếu ứng dụng chỉ có một quy trình đơn giản, chính sách và điều phối có thể được đặt trong một lớp service duy nhất; không cần tách class chỉ để tạo thêm tầng.

HTTP controller chuyển request thành `QuoteCommand`. Adapter lưu trữ có thể lấy giá sản phẩm từ JPA. Nếu ngày mai giá được lấy từ một dịch vụ khác, phần tính chiết khấu vẫn giữ nguyên miễn là dữ liệu đầu vào mang cùng ý nghĩa.

## 7. Kiểm thử ranh giới và quy tắc

Giữ nghiệp vụ độc lập làm cho nhiều kiểm thử có thể chạy nhanh mà không cần hạ tầng:

- **Unit test nghiệp vụ:** kiểm tra quy tắc, bất biến, biên giá trị và các trạng thái hợp lệ.
- **Test application service:** kiểm tra việc điều phối, xử lý kết quả từ abstraction và thứ tự các bước cần thiết.
- **Web-layer/contract test:** kiểm tra JSON, validation, mã HTTP và cách chuyển lỗi nghiệp vụ thành phản hồi.
- **Integration test cho adapter:** kiểm tra mapping ORM, truy vấn, transaction và migration với cơ sở dữ liệu phù hợp.

Ví dụ unit test cho chính sách:

```java
class DiscountPolicyTest {
    private final DiscountPolicy policy = new DiscountPolicy();

    @Test
    void memberWithLargeOrderGetsBothDiscounts() {
        var payable = policy.payableAmount(
                new BigDecimal("600000"),
                CustomerType.MEMBER);

        assertEquals(new BigDecimal("558000"), payable);
    }

    @Test
    void regularCustomerBelowThresholdGetsNoDiscount() {
        var payable = policy.payableAmount(
                new BigDecimal("200000"),
                CustomerType.REGULAR);

        assertEquals(new BigDecimal("200000"), payable);
    }
}
```

Test thứ nhất xác minh mức giảm cộng dồn theo ví dụ: 7% của 600.000 đồng. Test thứ hai kiểm tra trường hợp không đủ điều kiện nhận giảm giá. Những test này không phụ thuộc vào HTTP hoặc database, nên giúp phát hiện thay đổi quy tắc nhanh chóng.

Tuy nhiên, unit test không thay thế integration test. Mapper có thể ánh xạ sai loại khách hàng; repository có thể truy vấn thiếu dữ liệu; transaction có thể không rollback như mong đợi. Cần kiểm thử riêng các chi tiết đó ở đúng ranh giới của chúng.

## 8. Những cách làm dễ khiến tầng nghiệp vụ bị phụ thuộc

| Cách làm | Hệ quả | Điều chỉnh phù hợp |
|---|---|---|
| Trả JPA entity trực tiếp từ controller | API bị gắn với schema và quan hệ ORM | Dùng response DTO khi hợp đồng API cần độc lập |
| Đặt quy tắc chỉ trong controller | Luồng gọi khác có thể bỏ qua quy tắc | Bảo vệ bất biến ở nghiệp vụ; controller vẫn kiểm tra đầu vào giao thức |
| Domain trả `ResponseEntity` hoặc ném lỗi HTTP | Nghiệp vụ phụ thuộc Spring MVC | Dùng kết quả/lỗi nghiệp vụ và chuyển đổi ở adapter HTTP |
| Domain chứa annotation `@Entity`, `@Column` cho mọi trường | Mô hình nghiệp vụ bị chi phối bởi ORM | Tách persistence model khi lợi ích cô lập đáng kể |
| Tạo interface cho mọi class dù không có ranh giới cần bảo vệ | Tăng số kiểu và chi phí điều hướng | Chỉ tạo abstraction khi có nhu cầu thay thế, kiểm thử hoặc phân định phụ thuộc |
| Tách DTO, command, domain object và entity dù chúng giống hệt nhau | Tăng mapper và nguy cơ mất đồng bộ | Dùng chung mô hình khi ngữ nghĩa và vòng đời thực sự giống nhau |
| Đưa mọi logic vào một service khổng lồ | Khó hiểu trách nhiệm và kiểm thử | Chia theo chính sách hoặc hành vi nghiệp vụ có ý nghĩa |

Một số phụ thuộc framework ở tầng application có thể là lựa chọn thực dụng. Ví dụ, dùng `@Transactional` trên application service trong ứng dụng Spring giúp xác định ranh giới giao dịch của ca sử dụng. Điều đó không buộc quy tắc nghiệp vụ bên trong phải phụ thuộc Spring. Nếu cần khả năng chạy application logic trên nhiều runtime, có thể đặt transaction management ở adapter riêng; quyết định này cần dựa trên nhu cầu thực tế.

Tương tự, dùng Jakarta Validation ở DTO hoặc dùng thư viện tiền tệ không tự động làm kiến trúc sai. Cần phân biệt thư viện tiện ích ổn định với chi tiết của giao thức hoặc lưu trữ đang rò rỉ vào quyết định nghiệp vụ.

## 9. Cách quyết định mức độ tách biệt

Trước khi tách một mô hình hoặc thêm abstraction, hãy xem xét:

1. Quy tắc này có còn đúng nếu đổi HTTP thành message hoặc tác vụ nền không?
2. Quy tắc này có còn đúng nếu đổi tên bảng, đổi cột hoặc thay ORM không?
3. Có nhiều đường gọi cần dùng cùng một quy tắc không?
4. Mô hình lưu trữ có yêu cầu khác với cách nghiệp vụ diễn đạt khái niệm không?
5. Việc tách ra có giảm phụ thuộc hoặc giới hạn phạm vi thay đổi đủ để bù chi phí mapper và kiểm thử không?
6. Mức độ phức tạp hiện tại có cần các kỹ thuật DDD cụ thể không, hay một lớp service và vài đối tượng Java rõ ràng đã đủ?

Nếu ứng dụng chủ yếu CRUD, hãy bắt đầu đơn giản và bổ sung ranh giới khi có vấn đề thực tế. Nếu có quy tắc phức tạp, nhiều luồng gọi hoặc nhiều nguồn dữ liệu, hãy bảo vệ phần nghiệp vụ bằng mô hình và hợp đồng phù hợp. Không có một số lượng tầng, loại mô hình hay bộ kỹ thuật DDD bắt buộc cho mọi hệ thống.

## 10. Ghi nhớ

- Tầng nghiệp vụ chứa quy tắc và quyết định của lĩnh vực; HTTP, ORM và cấu trúc bảng là những cách giao tiếp hoặc lưu trữ.
- Controller xử lý giao thức và chuyển đổi request/response. Quy tắc quan trọng phải được bảo vệ ở nghiệp vụ để mọi đường gọi đều tuân thủ.
- JPA entity có thể phản ánh schema và nhu cầu ORM; mô hình nghiệp vụ nên phản ánh khái niệm, hành vi và trạng thái cần thiết.
- Đổi schema có thể cần sửa migration và adapter, nhưng không nên tự động làm thay đổi chính sách kinh doanh.
- DDD là bộ công cụ hữu ích cho miền phức tạp, không phải điều kiện bắt buộc để tổ chức tầng nghiệp vụ.
- Tách mô hình và abstraction khi chúng bảo vệ được một hợp đồng hoặc quyết định có khả năng thay đổi độc lập; giữ cấu trúc đơn giản khi chi phí thêm lớn hơn lợi ích.
- Kiểm thử quy tắc nghiệp vụ độc lập, đồng thời kiểm thử tích hợp ở các ranh giới HTTP và lưu trữ.

