# Phân biệt giao diện trừu tượng và thành phần cụ thể

Trong module **MODEL_VIEW_CONTROLLER**, MVC tổ chức ứng dụng web thành các trách nhiệm Model, View và Controller: quản lý trạng thái và nghiệp vụ, trình bày thông tin, tiếp nhận tương tác. Khi các trách nhiệm phối hợp, chúng cần những ranh giới trao đổi rõ ràng. Một bên có thể mô tả điều mình cần bằng **giao diện trừu tượng**; bên còn lại cung cấp **thành phần cụ thể** thực hiện hợp đồng đó.

Phân biệt hai khái niệm này giúp ta thiết kế các phần ít phụ thuộc vào chi tiết triển khai. Controller có thể gọi một use case mà không cần biết dữ liệu được lưu bằng JPA hay một hệ quản trị cơ sở dữ liệu khác. View có thể nhận một hợp đồng dữ liệu ổn định mà không cần biết Model lấy dữ liệu từ đâu. Nhờ vậy, nhóm phát triển dễ thay đổi công nghệ, thay thế thành phần và kiểm thử từng phần.

## 1. Giao diện trừu tượng là gì?

Giao diện trừu tượng mô tả **một thành phần cung cấp khả năng gì và những điều kiện trao đổi dữ liệu ra sao**, nhưng không buộc bên sử dụng phải biết cách khả năng đó được thực hiện. Nó là một hợp đồng giữa bên yêu cầu và bên cung cấp.

Trong Java, từ khóa **interface** là cách phổ biến để biểu diễn hợp đồng ở mức kiểu dữ liệu:

~~~java
public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId id);
}
~~~

Hợp đồng trên cho biết bên gọi có thể lưu một đơn hàng và tìm đơn hàng theo mã. Nó không nói dữ liệu được lưu trong PostgreSQL, MongoDB, bộ nhớ hay một dịch vụ bên ngoài. Bên gọi chỉ cần dựa vào những thao tác đã công bố.

Khái niệm trừu tượng rộng hơn từ khóa Java **interface**. Một hợp đồng có thể được biểu diễn bằng:

- Interface hoặc abstract class trong mã nguồn.
- Kiểu dữ liệu đầu vào và đầu ra như request DTO, command, response DTO hoặc view model.
- API HTTP với endpoint, phương thức, cấu trúc request, response và mã lỗi được quy định.
- Sự kiện hoặc thông điệp có cấu trúc mà các thành phần trao đổi.
- Một giao thức hoặc quy ước gọi giữa hai thành phần.

Không phải mọi DTO đều là interface Java. DTO là hợp đồng dữ liệu: nó quy định thông tin được truyền đi. Interface Java thường mô tả các thao tác mà một đối tượng có thể cung cấp. Hai hình thức này có thể bổ trợ cho nhau.

Một hợp đồng tốt cần nói rõ ý nghĩa của thao tác, dữ liệu đầu vào, kết quả, lỗi có thể xảy ra và những điều kiện mà bên sử dụng được phép kỳ vọng. Chỉ khai báo tên phương thức mà không xác định ngữ nghĩa thì chưa đủ để các bên phối hợp an toàn.

## 2. Thành phần cụ thể là gì?

Thành phần cụ thể là phần mã hoặc dịch vụ thực sự thực hiện công việc. Nó cung cấp hành vi theo một hợp đồng đã xác định, đồng thời có thể sử dụng các chi tiết kỹ thuật như cơ sở dữ liệu, framework, template engine, file system hoặc HTTP client.

Ví dụ, một lớp có thể triển khai hợp đồng lưu trữ đơn hàng:

~~~java
public final class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository dataRepository;

    public JpaOrderRepository(SpringDataOrderRepository dataRepository) {
        this.dataRepository = dataRepository;
    }

    @Override
    public void save(Order order) {
        dataRepository.save(OrderEntity.from(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return dataRepository.findById(id.value())
                .map(OrderEntity::toDomain);
    }
}
~~~

**JpaOrderRepository** là một triển khai cụ thể. Nó chuyển đổi đối tượng nghiệp vụ sang entity lưu trữ và sử dụng một repository của Spring Data. Lớp gọi thông qua **OrderRepository** không cần biết những chi tiết đó.

Một hợp đồng có thể có một hoặc nhiều triển khai cụ thể. Ví dụ, ứng dụng có thể dùng **JpaOrderRepository** trong môi trường chạy thật và **InMemoryOrderRepository** trong kiểm thử. Các triển khai có thể khác nhau về công nghệ nhưng phải giữ cùng ý nghĩa hợp đồng.

## 3. So sánh hai khái niệm

| Khía cạnh | Giao diện trừu tượng | Thành phần cụ thể |
| --- | --- | --- |
| Trả lời câu hỏi | Cần cung cấp khả năng gì? | Khả năng đó được thực hiện thế nào? |
| Nội dung | Hợp đồng, thao tác, kiểu dữ liệu, ngữ nghĩa | Thuật toán, truy vấn, gọi framework, xử lý thực tế |
| Phụ thuộc | Cố gắng ổn định trước thay đổi triển khai | Có thể phụ thuộc vào công nghệ hoặc hạ tầng |
| Thay đổi | Thay đổi khi nhu cầu hoặc hợp đồng thay đổi | Thay đổi khi cách thực hiện hoặc công nghệ thay đổi |
| Ví dụ | OrderRepository, PlaceOrderUseCase, OrderPageData | JpaOrderRepository, PlaceOrderService, Thymeleaf template |

Hai khái niệm này không phải hai loại thành phần tách biệt tuyệt đối. Một lớp cụ thể có thể cung cấp nhiều interface; một interface có thể được nhiều lớp triển khai. Một lớp cũng có thể là thành phần cụ thể của MVC và đồng thời phụ thuộc vào các hợp đồng trừu tượng khác.

## 4. Phân biệt ở từng phần của MVC

Model, View và Controller trước hết là **vai trò kiến trúc**, không phải tên bắt buộc của ba interface Java. Khi thiết kế một ứng dụng, ta xác định hợp đồng tại những ranh giới cần tách biệt và chọn thành phần cụ thể thực hiện hợp đồng đó.

### Model và các hợp đồng nghiệp vụ

Model giữ dữ liệu và quy tắc có ý nghĩa nghiệp vụ. Những lớp miền như **Order** hoặc **Product** thường là các lớp cụ thể thể hiện trạng thái và hành vi. Khi cần tách nghiệp vụ khỏi lưu trữ, ta định nghĩa một hợp đồng repository hoặc use case.

- Hợp đồng **OrderRepository** mô tả thao tác lưu và truy xuất đơn hàng.
- Triển khai **JpaOrderRepository** dùng JPA để truy cập cơ sở dữ liệu.
- Triển khai **InMemoryOrderRepository** giữ dữ liệu trong bộ nhớ để kiểm thử hoặc dùng trong một tình huống phù hợp.
- Hợp đồng **PlaceOrderUseCase** mô tả hành động đặt hàng.
- Triển khai **PlaceOrderService** điều phối các quy tắc và thao tác cần thiết để đặt hàng.

Không nên nhầm Model với interface. Một đối tượng miền có thể là lớp cụ thể vì nó chứa trạng thái và quy tắc trực tiếp. Việc tạo interface cho mọi entity không làm mô hình nghiệp vụ tự động tốt hơn.

### Controller và hợp đồng use case

Controller là nơi tiếp nhận request HTTP. Controller thường là một lớp cụ thể gắn với framework web, route và HTTP method. Để không phụ thuộc vào một dịch vụ nghiệp vụ cụ thể, Controller có thể gọi qua hợp đồng use case.

Ví dụ, Controller chỉ cần biết rằng nó có thể gọi **PlaceOrderUseCase** với một lệnh đặt hàng và nhận lại mã đơn hàng. Nó không cần biết dịch vụ đang dùng JPA, gửi thông điệp hay gọi một hệ thống khác.

### View và hợp đồng trình bày

View là vai trò trình bày dữ liệu. Hợp đồng ở ranh giới này thường là view model hoặc response DTO, quy định chính xác các trường cần hiển thị. Một template Thymeleaf, JSP hoặc một component giao diện phía client là cách triển khai trình bày cụ thể.

Ví dụ, **OrderPageData** có thể cung cấp mã đơn, nhãn trạng thái và tổng tiền đã định dạng. Template nhận các trường đó để dựng HTML. Template không cần biết phép tính tổng tiền được thực hiện ở đâu hoặc dữ liệu được lưu trong bảng nào.

Một template không nhất thiết phải triển khai interface Java. Trong nhiều framework, hợp đồng trình bày được thể hiện bằng tên view, các thuộc tính trong model hoặc cấu trúc JSON. Cần xem xét cơ chế cụ thể của framework thay vì áp đặt cùng một hình thức interface cho mọi View.

## 5. Ví dụ: Controller phụ thuộc vào hợp đồng, dịch vụ thực hiện nghiệp vụ

Giả sử ứng dụng có chức năng tạo đơn hàng. Ta định nghĩa hợp đồng use case:

~~~java
public interface PlaceOrderUseCase {
    OrderId execute(PlaceOrderCommand command);
}
~~~

Lệnh đầu vào là một hợp đồng dữ liệu:

~~~java
public record PlaceOrderCommand(
        CustomerId customerId,
        List<OrderLineCommand> lines
) {}
~~~

Một dịch vụ cụ thể triển khai hợp đồng và sử dụng Model cùng repository:

~~~java
public final class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public OrderId execute(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.lines());
        order.validateForPlacement();
        orders.save(order);
        return order.id();
    }
}
~~~

Controller tiếp nhận form, chuyển dữ liệu sang command và gọi hợp đồng:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderUseCase placeOrder;

    public OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public String create(@Valid @ModelAttribute OrderForm form,
                         BindingResult errors) {
        if (errors.hasErrors()) {
            return "orders/new";
        }

        OrderId id = placeOrder.execute(form.toCommand());
        return "redirect:/orders/" + id.value();
    }
}
~~~

Trong ví dụ này:

- **PlaceOrderUseCase** là hợp đồng trừu tượng mà Controller cần.
- **PlaceOrderService** là triển khai cụ thể thực hiện use case.
- **OrderRepository** là hợp đồng lưu trữ mà dịch vụ cần.
- **JpaOrderRepository** có thể là triển khai cụ thể dùng JPA.
- **OrderForm** là dữ liệu nhận từ biểu mẫu; nó được chuyển thành command trước khi đi vào use case.
- **OrderController** là thành phần web cụ thể; nó tiếp nhận HTTP và chọn response chuyển hướng.

Điểm quan trọng là Controller không gọi trực tiếp một lớp JPA hoặc tự thực hiện quy tắc tạo đơn. Hợp đồng làm rõ nhu cầu của Controller; dịch vụ cụ thể chịu trách nhiệm thực hiện nghiệp vụ.

## 6. Quan hệ phụ thuộc và luồng thực thi

Khi đọc sơ đồ kiến trúc, cần phân biệt **hướng phụ thuộc trong mã nguồn** và **luồng gọi khi chương trình chạy**. Controller biên dịch dựa trên kiểu **PlaceOrderUseCase**. Khi ứng dụng khởi động, bộ tiêm phụ thuộc có thể cung cấp đối tượng **PlaceOrderService** cho Controller. Khi người dùng gửi request, Controller gọi phương thức trên đối tượng cụ thể đó.

~~~mermaid
classDiagram
    class OrderController {
        -PlaceOrderUseCase placeOrder
        +create(OrderForm form) String
    }
    class PlaceOrderUseCase {
        <<interface>>
        +execute(PlaceOrderCommand) OrderId
    }
    class PlaceOrderService {
        -OrderRepository orders
        +execute(PlaceOrderCommand) OrderId
    }
    class OrderRepository {
        <<interface>>
        +save(Order order)
    }
    class JpaOrderRepository {
        +save(Order order)
    }
    OrderController --> PlaceOrderUseCase : phụ thuộc vào
    PlaceOrderService ..|> PlaceOrderUseCase : triển khai
    PlaceOrderService --> OrderRepository : phụ thuộc vào
    JpaOrderRepository ..|> OrderRepository : triển khai
~~~

Trong sơ đồ lớp, mũi tên nét đứt với tam giác rỗng biểu diễn quan hệ triển khai interface. Mũi tên phụ thuộc cho thấy lớp sử dụng một hợp đồng. Khi chạy, lời gọi đi qua đối tượng cụ thể đã được cấu hình:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as OrderController
    participant U as PlaceOrderService
    participant R as JpaOrderRepository
    participant DB as Cơ sở dữ liệu
    User->>C: POST /orders
    C->>U: execute(command)
    U->>U: Tạo và kiểm tra Order
    U->>R: save(order)
    R->>DB: INSERT / UPDATE
    DB-->>R: Kết quả lưu
    R-->>U: Hoàn tất
    U-->>C: OrderId
    C-->>User: Redirect đến trang đơn hàng
~~~

Sơ đồ trình tự mô tả một cách triển khai cụ thể. Nếu thay repository JPA bằng repository trong bộ nhớ, Controller và hợp đồng use case không cần thay đổi, miễn là triển khai mới đáp ứng đúng hợp đồng.

## 7. Thành phần cụ thể được chọn như thế nào?

Ứng dụng cần một cơ chế gắn hợp đồng với triển khai. Cách phổ biến là **dependency injection** (tiêm phụ thuộc): thành phần cần sử dụng khai báo kiểu hợp đồng trong constructor; cấu hình ứng dụng hoặc framework cung cấp đối tượng triển khai phù hợp.

Ví dụ với Spring, một lớp triển khai có thể được đăng ký làm bean:

~~~java
@Service
public final class PlaceOrderService implements PlaceOrderUseCase {
    // Constructor và phần xử lý nghiệp vụ
}
~~~

Nếu chỉ có một bean phù hợp, Spring có thể tiêm bean đó vào constructor của Controller. Khi có nhiều triển khai, cấu hình cần xác định rõ bean nào được chọn, chẳng hạn bằng qualifier hoặc cấu hình có điều kiện. Không nên dựa vào lựa chọn ngầm nếu nhiều triển khai có ý nghĩa khác nhau.

Tiêm phụ thuộc cũng có thể thực hiện thủ công trong composition root của ứng dụng:

~~~java
OrderRepository repository = new JpaOrderRepository(dataRepository);
PlaceOrderUseCase useCase = new PlaceOrderService(repository);
OrderController controller = new OrderController(useCase);
~~~

Ví dụ này cho thấy nơi khởi tạo ứng dụng biết các lớp cụ thể và kết nối chúng với nhau. Các lớp nghiệp vụ vẫn có thể phụ thuộc vào hợp đồng.

## 8. Lợi ích và giới hạn

Sử dụng hợp đồng trừu tượng tại ranh giới phù hợp mang lại một số lợi ích:

- **Giảm phụ thuộc vào công nghệ.** Controller không cần biết chi tiết JPA, SQL hoặc nhà cung cấp dịch vụ.
- **Dễ thay thế triển khai.** Có thể dùng adapter khác khi đổi cơ sở dữ liệu, tích hợp API hoặc môi trường chạy.
- **Dễ kiểm thử.** Có thể thay phụ thuộc thật bằng fake hoặc stub để kiểm tra hành vi của thành phần đang xét.
- **Làm rõ trách nhiệm.** Hợp đồng cho biết thành phần cần gì và cung cấp gì, giúp việc đọc mã và phân chia công việc dễ hơn.
- **Giữ ranh giới dữ liệu.** DTO và view model giới hạn thông tin đi qua mỗi ranh giới, giảm nguy cơ làm lộ cấu trúc nội bộ.

Tuy vậy, mỗi interface cũng tạo thêm một hợp đồng phải duy trì. Nếu một lớp chỉ có một triển khai ổn định, không có ranh giới cần bảo vệ và không có nhu cầu thay thế hoặc kiểm thử độc lập, việc tạo interface riêng có thể chỉ làm mã nguồn dài hơn. Trừu tượng hóa quá sớm dễ tạo ra nhiều lớp chuyển tiếp, tên gọi chung chung và hợp đồng không phản ánh nhu cầu thật.

Không nên tạo interface chỉ vì một lớp có hậu tố **Service**, **Controller** hoặc **Repository**. Hãy tạo hợp đồng khi có một ranh giới có ý nghĩa: bên sử dụng cần một khả năng ổn định, còn cách cung cấp khả năng đó có thể thay đổi hoặc cần được cô lập.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Controller phụ thuộc trực tiếp vào lớp lưu trữ cụ thể | Đổi công nghệ lưu trữ có thể kéo theo sửa Controller | Đặt hợp đồng tại ranh giới phù hợp và để adapter cụ thể triển khai |
| Interface công khai các kiểu của framework hoặc ORM | Hợp đồng bị khóa vào một công nghệ | Dùng kiểu dữ liệu có ý nghĩa ở ranh giới, chuyển đổi ở adapter |
| Tạo interface cho mọi lớp dù không có nhu cầu tách biệt | Tăng số lượng kiểu và chi phí bảo trì | Chỉ trừu tượng hóa ranh giới có lý do rõ ràng |
| Nhiều triển khai nhưng không có quy tắc chọn | Ứng dụng có thể tiêm nhầm thành phần hoặc khởi động thất bại | Cấu hình rõ bean, qualifier hoặc factory |
| Các triển khai cùng interface nhưng hành vi khác nghĩa | Bên gọi không thể tin cậy hợp đồng | Quy định ngữ nghĩa, lỗi và điều kiện; kiểm thử mọi triển khai theo cùng hợp đồng |
| Đưa quy tắc nghiệp vụ vào adapter kỹ thuật | Nghiệp vụ có thể bị bỏ qua khi đổi đường gọi | Đặt quy tắc trong Model hoặc use case, giữ adapter tập trung vào chuyển đổi và giao tiếp |

Một interface chỉ hữu ích khi các triển khai có thể thay thế nhau theo đúng kỳ vọng của bên gọi. Nếu một triển khai âm thầm bỏ qua thao tác lưu, trả kết quả không đúng quy ước hoặc dùng cách xử lý lỗi khác nghĩa, nó không thực hiện đúng hợp đồng dù vẫn biên dịch thành công.

## 10. Kiểm thử hợp đồng và triển khai

Có thể kiểm thử ở nhiều mức:

- **Kiểm thử thành phần sử dụng hợp đồng:** truyền một fake hoặc mock vào Controller/use case để xác nhận lời gọi, dữ liệu và phản hồi được xử lý đúng.
- **Kiểm thử triển khai cụ thể:** kiểm tra adapter JPA lưu và đọc dữ liệu đúng, ánh xạ entity sang domain object đúng, và xử lý trường hợp không tìm thấy.
- **Kiểm thử hợp đồng dùng chung:** chạy cùng một bộ tình huống trên các triển khai của một interface. Ví dụ, cả repository trong bộ nhớ và repository JPA đều phải giữ đúng quy ước lưu, tìm và trả kết quả.
- **Kiểm thử tích hợp:** khởi tạo cấu hình thật để xác nhận framework đã nối đúng Controller, use case, repository và View.

Ví dụ một fake repository đơn giản:

~~~java
public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> data = new HashMap<>();

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(data.get(id));
    }
}
~~~

Fake này có thể hỗ trợ kiểm thử use case mà không cần khởi động cơ sở dữ liệu. Khi dùng trong kiểm thử, nó vẫn cần tuân thủ cùng ngữ nghĩa của **OrderRepository** mà triển khai thật phải đáp ứng.

## 11. Cách quyết định có cần một giao diện trừu tượng hay không

Trước khi tạo interface hoặc một lớp adapter, hãy trả lời các câu hỏi sau:

1. Thành phần sử dụng cần khả năng nào? Viết hợp đồng bằng ngôn ngữ nghiệp vụ hoặc ngôn ngữ của use case.
2. Có chi tiết kỹ thuật nào cần được giữ bên ngoài thành phần sử dụng không? Nếu có, đặt ranh giới tại nơi chi tiết đó bắt đầu.
3. Có khả năng cần nhiều triển khai, thay đổi công nghệ hoặc thay thế trong kiểm thử không? Nếu có, hợp đồng trừu tượng có thể mang lại giá trị.
4. Các triển khai có thể tuân thủ cùng một ý nghĩa và điều kiện không? Nếu không, có thể chúng đang đại diện cho những hợp đồng khác nhau.
5. Hợp đồng có đang để lộ kiểu của framework, ORM hoặc chi tiết lưu trữ không? Nếu có, xem xét chuyển đổi dữ liệu tại adapter.
6. Chi phí duy trì interface có tương xứng với lợi ích của ranh giới không? Nếu không, một lớp cụ thể với constructor rõ ràng có thể đã đủ.

Với MVC, có thể bắt đầu bằng cách xác định nơi Controller giao tiếp với use case, nơi use case giao tiếp với lưu trữ hoặc dịch vụ bên ngoài, và nơi dữ liệu được chuyển sang View. Sau đó chỉ tạo các hợp đồng cần thiết cho những ranh giới có khả năng thay đổi hoặc cần kiểm thử độc lập.

## Kết luận

Giao diện trừu tượng mô tả hợp đồng mà bên sử dụng có thể dựa vào; thành phần cụ thể cung cấp cách thực hiện hợp đồng đó. Trong MVC, Controller có thể gọi use case qua interface, Model có thể dùng repository contract để tách nghiệp vụ khỏi lưu trữ, còn View nhận dữ liệu trình bày qua DTO hoặc view model. Khi đặt trừu tượng hóa đúng ranh giới và giữ cho mọi triển khai tuân thủ cùng ngữ nghĩa, ứng dụng dễ thay đổi, kiểm thử và phát triển theo từng phần hơn.
