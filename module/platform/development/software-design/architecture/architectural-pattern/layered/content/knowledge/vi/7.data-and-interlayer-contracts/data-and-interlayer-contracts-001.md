# Phân biệt request, response, DTO, đối tượng nghiệp vụ và entity ORM

Một ứng dụng phân tầng thường có nhiều kiểu đối tượng cùng mô tả một phần dữ liệu, nhưng chúng phục vụ các hợp đồng và vòng đời khác nhau. Ví dụ, thông tin đặt hàng có thể xuất hiện trong JSON mà khách hàng gửi lên, command mà tầng ứng dụng xử lý, đối tượng Order bảo vệ quy tắc nghiệp vụ, entity JPA được lưu trong cơ sở dữ liệu và JSON phản hồi cho khách hàng. Những đối tượng này có thể chứa một vài trường giống nhau, nhưng không vì thế mà chúng nên là cùng một lớp.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — việc phân biệt các kiểu dữ liệu giúp giữ ranh giới giữa tầng trình bày, tầng ứng dụng, tầng nghiệp vụ và tầng truy cập dữ liệu. Mỗi kiểu nên phản ánh đúng hợp đồng mà nó phục vụ: request và response phục vụ giao tiếp; DTO chuyển dữ liệu giữa các thành phần; đối tượng nghiệp vụ thể hiện khái niệm và quy tắc của miền; entity ORM phản ánh cách dữ liệu được ánh xạ và lưu trữ.

## 1. Vì sao không nên dùng một lớp cho mọi tầng?

Giả sử hệ thống bán hàng có chức năng tạo đơn. Một đơn hàng có thể cần các thông tin sau ở những thời điểm khác nhau:

- Khách hàng gửi mã sản phẩm và số lượng trong HTTP request.
- Tầng ứng dụng nhận một lệnh đặt hàng, xác định khách hàng hiện tại và phối hợp tải dữ liệu sản phẩm.
- Mô hình nghiệp vụ tạo Order, kiểm tra đơn có dòng hàng hợp lệ và tính tổng tiền theo quy tắc.
- Tầng lưu trữ ghi dữ liệu vào các bảng order, order_line và các quan hệ tương ứng.
- API trả mã đơn, trạng thái và tổng tiền cho khách hàng.

Nếu dùng một lớp duy nhất cho tất cả, lớp đó có thể phải chứa annotation của JSON, validation của request, hành vi nghiệp vụ, annotation JPA và cả trường phản hồi. Khi API đổi tên trường, mô hình nghiệp vụ có thể bị ảnh hưởng. Khi cấu trúc bảng thay đổi, hợp đồng API có thể bị thay đổi ngoài ý muốn. Khi trả một đối tượng JPA trực tiếp, dữ liệu nội bộ hoặc quan hệ lazy-loading có thể bị lộ ra ngoài.

Tách các kiểu dữ liệu theo mục đích giúp mỗi tầng thay đổi theo lý do của nó. Không cần tạo một lớp riêng cho mọi lần truyền dữ liệu; chỉ tách khi có ranh giới, vòng đời hoặc lý do thay đổi khác nhau.

## 2. Phân biệt các khái niệm

| Khái niệm | Mục đích | Thường được dùng ở đâu? | Đặc điểm |
|---|---|---|---|
| Request model / request DTO | Mô tả dữ liệu mà một kênh gửi vào hệ thống. | Tầng trình bày, ví dụ REST controller. | Phản ánh hợp đồng đầu vào; có thể có annotation validation và tên trường theo API. |
| Response model / response DTO | Mô tả dữ liệu hệ thống trả ra cho một kênh. | Tầng trình bày. | Chỉ công bố thông tin cần thiết; có thể khác cấu trúc nội bộ. |
| DTO (Data Transfer Object) | Mang dữ liệu qua một ranh giới mà không mang trách nhiệm xử lý nghiệp vụ. | Giữa các tầng, module hoặc tiến trình. | Là khái niệm tổng quát; request/response model và application input/output model thường là các dạng DTO. |
| Đối tượng nghiệp vụ (domain object) | Biểu diễn khái niệm nghiệp vụ, trạng thái và quy tắc. | Tầng nghiệp vụ/domain. | Có thể có identity, hành vi và bất biến; không phụ thuộc cấu trúc JSON hay ORM. |
| Entity ORM (ví dụ JPA entity) | Ánh xạ dữ liệu lưu trữ sang đối tượng mà ORM quản lý. | Tầng truy cập dữ liệu/hạ tầng. | Có annotation và quan hệ lưu trữ; vòng đời gắn với persistence context và cơ chế ORM. |

### Request và response là hợp đồng của kênh

Request model thể hiện những gì người gọi được phép gửi. Nó có thể dùng kiểu dữ liệu đơn giản, tên trường dễ hiểu và annotation kiểm tra cú pháp hoặc cấu trúc. Ví dụ, API có thể nhận productId và quantity. Request không nhất thiết chứa giá sản phẩm hoặc tổng tiền, vì đây là dữ liệu hệ thống phải tự xác định.

Response model thể hiện những gì người gọi được phép nhìn thấy. API có thể trả orderId, status và total. Nó không nhất thiết trả toàn bộ thông tin khách hàng, đối tượng nội bộ, trạng thái ORM hoặc các trường phục vụ vận hành.

Hợp đồng request/response thường cần ổn định đối với người dùng API. Vì vậy, không nên để nó tự động thay đổi chỉ vì tên thuộc tính trong domain hoặc tên cột trong cơ sở dữ liệu thay đổi.

### DTO là tên gọi theo vai trò truyền dữ liệu

DTO không phải một tầng kiến trúc cụ thể và cũng không nhất thiết là một loại class đặc biệt của Java. Nó mô tả một đối tượng được dùng để chuyển dữ liệu qua ranh giới. Một record Java bất biến có thể là DTO; một class thông thường cũng có thể là DTO.

Request DTO và response DTO là các ví dụ quen thuộc, nhưng ứng dụng cũng có thể định nghĩa command hoặc result riêng để giao tiếp giữa adapter và ca sử dụng. DTO thường chứa dữ liệu và các phép chuyển đổi đơn giản, không nên chứa quy trình nghiệp vụ hoặc tự truy cập cơ sở dữ liệu.

### Đối tượng nghiệp vụ có trách nhiệm bảo vệ ý nghĩa nghiệp vụ

Đối tượng nghiệp vụ mô tả khái niệm trong miền, chẳng hạn Order, Account, Product hoặc Money. Một domain entity thường có định danh ổn định và vòng đời nghiệp vụ; nó có thể cung cấp hành vi để thay đổi trạng thái theo quy tắc.

Không phải mọi đối tượng domain đều là entity. Value object như Money, Address hoặc OrderLine có thể được nhận diện bằng giá trị và không cần identity riêng. Điều quan trọng là mô hình nghiệp vụ biểu diễn ngôn ngữ và quy tắc của miền, thay vì chỉ phản chiếu cấu trúc bảng.

### Entity ORM là mô hình lưu trữ

JPA entity là đối tượng được ORM ánh xạ vào bảng hoặc cấu trúc lưu trữ. Nó có thể dùng @Entity, @Id, @OneToMany, @ManyToOne và các annotation khác. ORM quản lý trạng thái, quan hệ, dirty checking và quá trình đồng bộ với cơ sở dữ liệu.

Từ "entity" trong JPA không đồng nghĩa với "domain entity". Một dự án có thể dùng cùng một lớp cho cả hai vai trò nếu mô hình đơn giản và sự phụ thuộc được chấp nhận. Nhưng đó là một lựa chọn có đánh đổi, không phải yêu cầu của kiến trúc phân tầng. Khi quy tắc nghiệp vụ phức tạp hoặc cấu trúc lưu trữ thay đổi thường xuyên, tách domain entity khỏi JPA entity thường giúp kiểm soát ranh giới tốt hơn.

## 3. Ví dụ: một luồng tạo đơn qua các kiểu dữ liệu khác nhau

Giả sử khách hàng gửi request:

~~~json
{
  "items": [
    {
      "productId": "c39a1c0a-5f4a-47bc-aaf7-84f79f02e41e",
      "quantity": 2
    },
    {
      "productId": "7a09b08d-f77e-42f5-bd0d-7d99f0d1c9c2",
      "quantity": 1
    }
  ],
  "note": "Giao vào buổi chiều"
}
~~~

Request không gửi giá và tổng tiền. Giá phải được lấy từ nguồn dữ liệu đáng tin cậy của hệ thống, sau đó domain mới tính tổng. Một request DTO có thể được định nghĩa như sau:

~~~java
public record CreateOrderRequest(
    @NotEmpty List<@Valid CreateOrderItemRequest> items,
    @Size(max = 300) String note
) {}

public record CreateOrderItemRequest(
    @NotNull UUID productId,
    @Positive int quantity
) {}
~~~

Đây là hợp đồng HTTP. Annotation @NotEmpty, @NotNull, @Positive và @Size kiểm tra cấu trúc, kiểu và giới hạn đầu vào. Các annotation không chứng minh sản phẩm tồn tại, còn được bán hoặc khách hàng có quyền đặt sản phẩm đó. Những điều kiện này cần được đánh giá trong ca sử dụng và nghiệp vụ.

Controller chuyển request thành command cho ứng dụng:

~~~java
public record CreateOrderItemCommand(
    ProductId productId,
    int quantity
) {}

public record CreateOrderCommand(
    CustomerId customerId,
    List<CreateOrderItemCommand> items,
    String note
) {}

public record CreateOrderResult(
    OrderId orderId,
    OrderStatus status,
    Money total
) {}
~~~

Command và result thể hiện hợp đồng của ca sử dụng. Chúng có thể khác request/response DTO: customerId có thể được lấy từ danh tính đã xác thực thay vì tin vào dữ liệu người dùng gửi; ProductId và CustomerId là kiểu giá trị nội bộ thay cho UUID thô; kết quả có thể chứa Money để adapter quyết định cách định dạng tiền.

Controller chỉ thực hiện chuyển đổi ở biên và gọi ca sử dụng:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final CreateOrderUseCase createOrder;

    OrderController(CreateOrderUseCase createOrder) {
        this.createOrder = createOrder;
    }

    @PostMapping
    ResponseEntity<CreateOrderResponse> create(
            @AuthenticationPrincipal CurrentUser user,
            @Valid @RequestBody CreateOrderRequest request) {
        CreateOrderCommand command = new CreateOrderCommand(
            CustomerId.of(user.customerId()),
            request.items().stream()
                .map(item -> new CreateOrderItemCommand(
                    ProductId.of(item.productId()), item.quantity()))
                .toList(),
            request.note()
        );

        CreateOrderResult result = createOrder.handle(command);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new CreateOrderResponse(
                result.orderId().value(),
                result.status().name(),
                result.total().amount(),
                result.total().currency().getCurrencyCode()
            ));
    }
}

public record CreateOrderResponse(
    UUID orderId,
    String status,
    BigDecimal total,
    String currency
) {}
~~~

Ví dụ giả định CurrentUser được Spring Security cung cấp sau khi xác thực. Controller lấy danh tính khách hàng từ ngữ cảnh bảo mật thay vì tin một customerId tùy ý trong request. Trong một ứng dụng khác, thông tin này có thể được truyền vào ca sử dụng qua một đối tượng context riêng.

### Domain object biểu diễn quy tắc

Mô hình nghiệp vụ không cần biết JSON hoặc tên trường của API:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private final String note;
    private OrderStatus status;

    private Order(
            OrderId id,
            CustomerId customerId,
            List<OrderLine> lines,
            String note) {
        if (lines == null || lines.isEmpty()) {
            throw new EmptyOrderException();
        }
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
        this.note = note;
        this.status = OrderStatus.DRAFT;
    }

    public static Order place(
            CustomerId customerId,
            List<OrderLine> lines,
            String note) {
        return new Order(OrderId.newId(), customerId, lines, note);
    }

    public Money total() {
        return lines.stream()
            .map(OrderLine::subtotal)
            .reduce(Money.zero(), Money::add);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException();
        }
        status = OrderStatus.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return lines;
    }

    public String note() {
        return note;
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Đoạn mã minh họa một domain entity có identity, trạng thái và hành vi. OrderLine và Money là các kiểu nghiệp vụ; chúng không nhất thiết là entity ORM. Domain có thể bảo vệ điều kiện đơn phải có dòng hàng và chỉ cho phép xác nhận khi trạng thái hiện tại phù hợp. Trong hệ thống thực tế, quy tắc về giá, tồn kho, thuế và giảm giá có thể được mô hình hóa bằng value object hoặc domain policy riêng.

### JPA entity phản ánh cấu trúc lưu trữ

Một lớp JPA có thể được tổ chức theo bảng và quan hệ cần lưu:

~~~java
@Entity
@Table(name = "orders")
class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(length = 300)
    private String note;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLineJpaEntity> lines = new ArrayList<>();

    protected OrderJpaEntity() {}

    // Constructor và phương thức chuyển đổi được lược giản.
}
~~~

OrderJpaEntity có thể chứa chi tiết ánh xạ bảng, khóa ngoại, cascade và quy tắc vòng đời ORM. Nó không nên trở thành nơi duy nhất bảo vệ quy tắc đặt hàng nếu hệ thống cần domain độc lập. Một callback JPA hoặc constraint cơ sở dữ liệu có thể bảo vệ một số điều kiện kỹ thuật, nhưng không thay thế hành vi nghiệp vụ rõ ràng.

Repository adapter chuyển đổi giữa domain và persistence model:

~~~java
@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderRepository repository;

    JpaOrderRepositoryAdapter(SpringDataOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void save(Order order) {
        OrderJpaEntity entity = OrderJpaMapper.toEntity(order);
        repository.save(entity);
    }
}
~~~

Mapper có thể là lớp riêng hoặc phương thức trong adapter. Khi tải dữ liệu, adapter cũng có thể chuyển JPA entity thành domain object. Nhờ đó, application/domain làm việc với hợp đồng repository và mô hình nghiệp vụ, không phải phụ thuộc trực tiếp vào kiểu Hibernate hoặc Spring Data.

## 4. Ranh giới và nơi đặt mapper

Mapper chuyển dữ liệu từ một mô hình sang mô hình khác. Vị trí mapper nên đi theo ranh giới mà nó chuyển đổi:

| Chuyển đổi | Vị trí thường phù hợp | Lý do |
|---|---|---|
| HTTP request DTO → application command | REST adapter/controller hoặc mapper thuộc presentation. | Chuyển hợp đồng HTTP thành hợp đồng ca sử dụng. |
| Application result → HTTP response DTO | REST adapter/controller hoặc presentation mapper. | Chỉ công bố dữ liệu phù hợp với API. |
| Domain object ↔ JPA entity | Repository adapter hoặc persistence mapper ở hạ tầng. | Che giấu cấu trúc ORM và bảng dữ liệu. |
| Message payload → application command | Message adapter. | Chuyển schema của message thành hợp đồng ứng dụng. |
| Domain object → view model | Adapter trình bày tương ứng. | Chuẩn bị dữ liệu cho màn hình mà không làm domain biết UI. |

Không có quy tắc bắt buộc rằng mapper phải là một lớp riêng. Với chuyển đổi đơn giản, constructor hoặc phương thức tĩnh có thể đủ. Khi mapping nhiều trường, xử lý quan hệ, chuyển đổi enum hoặc có nhiều kênh, một mapper chuyên biệt giúp dễ đọc và kiểm thử hơn.

Điều cần giữ là hướng phụ thuộc. Domain không nên import request DTO, response DTO hoặc JPA entity. Nếu domain cần một khái niệm như Money, hãy định nghĩa nó trong mô hình nghiệp vụ thay vì dùng kiểu của API hoặc ORM. Adapter ở biên chịu trách nhiệm chuyển đổi sang và từ kiểu mà tầng bên trong hiểu.

## 5. Rủi ro khi dùng chung request, domain object và ORM entity

Dùng một lớp cho nhiều vai trò có thể nhanh trong ví dụ nhỏ, nhưng tạo ra các vấn đề khi hệ thống phát triển:

- **Lộ dữ liệu:** serialize JPA entity trực tiếp có thể làm lộ trường nội bộ, dữ liệu nhạy cảm hoặc cấu trúc quan hệ không dành cho người dùng API.
- **Ràng buộc API với cơ sở dữ liệu:** đổi tên cột, quan hệ hoặc cách chuẩn hóa bảng có thể làm thay đổi JSON ngoài ý muốn.
- **Khó kiểm soát dữ liệu ghi:** nếu request bind trực tiếp vào entity đang được quản lý, người gọi có thể gửi các trường như id, role, status hoặc ownerId mà họ không được phép sửa. Đây là một dạng mass assignment.
- **Phụ thuộc ORM:** domain gọi getter có thể kích hoạt lazy loading, phát sinh truy vấn bất ngờ hoặc lỗi khi persistence context đã đóng.
- **Vòng đời không phù hợp:** entity JPA có trạng thái transient, managed, detached và removed; những trạng thái này không nên chi phối cách ứng dụng mô tả nghiệp vụ.
- **Khó thay đổi từng hợp đồng:** API, command ứng dụng, mô hình nghiệp vụ và schema lưu trữ có thể cần tiến hóa theo nhịp khác nhau.

Ví dụ, API tạo đơn không nên nhận status do khách hàng tự chọn nếu trạng thái ban đầu phải luôn là DRAFT. Request DTO chỉ chứa các trường được phép gửi. Domain tạo trạng thái ban đầu theo quy tắc. Persistence adapter lưu trạng thái đó vào bảng. Response DTO quyết định có công bố trạng thái cho khách hàng hay không.

## 6. Khi nào có thể dùng chung một kiểu dữ liệu?

Không phải ứng dụng nào cũng cần tách tất cả các lớp. Với một dịch vụ CRUD nhỏ, ít quy tắc nghiệp vụ và ít khả năng thay đổi schema, việc dùng một kiểu cho request và persistence model có thể giảm mã chuyển đổi. Một JPA entity đơn giản đôi khi cũng được trả qua API nội bộ nếu hợp đồng đó được kiểm soát và không có rủi ro về dữ liệu hoặc quan hệ.

Tuy nhiên, cần cân nhắc trước khi dùng chung:

- Có trường nào người gọi được gửi nhưng không được quyền sửa không?
- Cấu trúc API có cần tương thích ngược khi database đổi không?
- Domain có quy tắc hoặc hành vi cần độc lập với ORM không?
- Entity có quan hệ lazy, cascade hoặc trường nội bộ không nên serialize không?
- Có nhiều kênh giao tiếp với schema đầu vào khác nhau không?
- Có cần kiểm thử domain mà không khởi động Spring/JPA không?

Nếu câu trả lời cho các câu hỏi này cho thấy các trách nhiệm khác nhau, hãy tách kiểu dữ liệu. Nếu hệ thống đơn giản và các vòng đời thực sự trùng nhau, có thể dùng chung có chủ đích và ghi nhận đánh đổi. Không cần áp dụng DDD hoặc tạo nhiều lớp chỉ vì một quy ước hình thức.

## 7. Kiểm thử hợp đồng và chuyển đổi dữ liệu

Các kiểu dữ liệu riêng giúp kiểm thử từng ranh giới:

- **Presentation test:** xác minh request JSON được bind và validate đúng; trường không được phép sửa không thể được người dùng ghi đè; response chỉ chứa dữ liệu công bố.
- **Application test:** xác minh command mang đủ thông tin cho ca sử dụng, application điều phối đúng repository và domain policy.
- **Domain unit test:** xác minh Order, Money và các đối tượng nghiệp vụ bảo vệ bất biến, chuyển trạng thái đúng mà không cần JPA.
- **Mapper test:** xác minh dữ liệu được chuyển đầy đủ và đúng nghĩa giữa domain và JPA entity, hoặc giữa application result và response DTO.
- **Persistence integration test:** xác minh adapter lưu/tải đúng dữ liệu, quan hệ và transaction với cơ sở dữ liệu thực tế.

Đừng chỉ kiểm tra mapper rằng mọi trường có cùng tên đều được sao chép. Hãy kiểm tra các chuyển đổi có ý nghĩa: UUID thành ProductId, BigDecimal cùng đơn vị tiền thành Money, enum trạng thái được ánh xạ đúng, danh sách dòng hàng được tái tạo đầy đủ và trường nhạy cảm không xuất hiện trong response.

Nếu response DTO thay đổi chỉ vì một trường JPA được thêm vào, có thể API đang phụ thuộc trực tiếp vào persistence model. Nếu domain unit test phải dựng persistence context chỉ để kiểm tra một bất biến, domain có thể đang bị gắn chặt với ORM. Nếu controller cần tự tính tổng tiền từ request, quy tắc có thể đang nằm sai tầng.

## 8. Cách lựa chọn kiểu dữ liệu cho một chức năng mới

Khi thiết kế một chức năng, hãy xác định lần lượt:

1. **Người gọi gửi những gì?** Tạo request model theo hợp đồng của kênh và chỉ nhận các trường người gọi được phép cung cấp.
2. **Ca sử dụng cần dữ liệu gì?** Tạo command/input model theo ngôn ngữ ứng dụng; lấy danh tính và dữ liệu đáng tin cậy từ ngữ cảnh hoặc cổng cần thiết.
3. **Quy tắc nghiệp vụ thao tác trên khái niệm nào?** Dùng domain entity, value object hoặc policy để bảo vệ bất biến và hành vi.
4. **Dữ liệu được lưu theo cấu trúc nào?** Dùng persistence entity nếu cần ánh xạ ORM; để adapter quản lý việc chuyển đổi.
5. **Người gọi cần biết kết quả gì?** Tạo response model theo hợp đồng của kênh, không trả toàn bộ đối tượng nội bộ.
6. **Mapper thuộc ranh giới nào?** Đặt chuyển đổi tại adapter sở hữu giao thức hoặc persistence adapter sở hữu công nghệ lưu trữ.
7. **Có thể kiểm thử độc lập từng phần không?** Domain không cần biết JSON/JPA; mapper và adapter có kiểm thử riêng cho hợp đồng của chúng.

Một hệ thống phân tầng rõ ràng không được quyết định bởi số lượng class, mà bởi việc mỗi kiểu dữ liệu có mục đích và chủ sở hữu dễ nhận biết. Request/response bảo vệ hợp đồng giao tiếp; DTO mang dữ liệu qua ranh giới; domain object giữ ý nghĩa và quy tắc nghiệp vụ; ORM entity phục vụ lưu trữ. Khi các kiểu này được tách theo lý do thay đổi và mapper được đặt đúng ranh giới, API, nghiệp vụ và cơ sở dữ liệu có thể tiến hóa độc lập hơn mà không kéo theo những thay đổi ngoài ý muốn.

