# Tránh service khổng lồ và tầng trung gian chỉ chuyển tiếp lời gọi

Trong ứng dụng phân tầng, các lớp `Service` thường là nơi dễ tích tụ trách nhiệm nhất. Một service ban đầu chỉ xử lý một ca sử dụng có thể dần nhận thêm chức năng tạo, sửa, hủy, tìm kiếm, báo cáo, gửi email và tích hợp thanh toán. Kết quả là một lớp biết quá nhiều về nhiều phần của hệ thống, khó kiểm thử và thay đổi ở một chức năng có thể làm hỏng chức năng khác.

Ở chiều ngược lại, một số ứng dụng tạo quá nhiều lớp trung gian nhưng mỗi lớp chỉ gọi tiếp phương thức của lớp kế tiếp mà không tạo ra ranh giới, chính sách hay chuyển đổi có ý nghĩa. Luồng xử lý dài hơn, việc điều hướng khó hơn, trong khi sự phụ thuộc thực tế vẫn giữ nguyên.

Hai vấn đề này thường xuất hiện cùng nhau khi nhóm hiểu kiến trúc phân tầng như yêu cầu phải có một lớp cho mọi thao tác hoặc một số tầng cố định. Kiến trúc phân tầng nhằm tách trách nhiệm trình bày, điều phối use case, quy tắc nghiệp vụ và truy cập dữ liệu. Số lớp và độ dày của từng tầng cần phản ánh nhu cầu thực tế của hệ thống.

## 1. Nhận diện service khổng lồ

Service khổng lồ (God Service hoặc God Class) không được xác định chỉ bằng số dòng code. Một lớp có nhiều dòng vẫn có thể có trách nhiệm rõ ràng; ngược lại, một lớp ngắn có thể nắm quyền điều phối nhiều phần không liên quan. Hãy xem xét mức độ tập trung trách nhiệm và các lý do khiến lớp phải thay đổi.

Các dấu hiệu thường gặp:

- Một lớp có các phương thức cho nhiều use case khác nhau, chẳng hạn tạo đơn, hủy đơn, hoàn tiền, tìm kiếm, xuất báo cáo và gửi thông báo.
- Constructor nhận quá nhiều dependency thuộc nhiều lĩnh vực: repository đơn hàng, khách hàng, kho, thanh toán, email, lưu tệp, báo cáo và cấu hình.
- Nhiều phương thức có các nhánh điều kiện lớn theo trạng thái, loại khách hàng hoặc loại giao dịch; các quy tắc tương tự bị lặp ở nhiều nhánh.
- Một thay đổi nhỏ về chính sách kho hoặc thanh toán buộc phải sửa lớp đang chứa cả chức năng đọc và báo cáo.
- Unit test phải mock rất nhiều dependency, thiết lập dữ liệu phức tạp và thường chỉ kiểm tra một nhánh nhỏ của lớp.
- Các nhóm khác nhau cùng sửa một lớp, dễ xung đột khi merge và khó xác định ai sở hữu quy tắc nào.

Ví dụ một service có xu hướng trở thành điểm tập trung:

```java
@Service
class OrderService {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final InventoryPort inventory;
    private final PaymentPort payments;
    private final EmailPort email;
    private final ReportRepository reports;
    private final FileStoragePort files;

    OrderService(
            OrderRepository orders,
            CustomerRepository customers,
            InventoryPort inventory,
            PaymentPort payments,
            EmailPort email,
            ReportRepository reports,
            FileStoragePort files) {
        this.orders = orders;
        this.customers = customers;
        this.inventory = inventory;
        this.payments = payments;
        this.email = email;
        this.reports = reports;
        this.files = files;
    }

    // placeOrder(), cancelOrder(), refund(), search(), exportReport(), ...
}
```

Việc một service có nhiều dependency không tự động chứng minh thiết kế sai. Nhưng nếu các dependency phục vụ những use case độc lập, lớp đang có nhiều lý do để thay đổi và ranh giới trách nhiệm không còn rõ. Đây là tín hiệu cần xem lại cách nhóm hành vi.

## 2. Tách trách nhiệm theo use case và khái niệm nghiệp vụ

Trong kiến trúc phân tầng, mỗi phần nên giữ loại quyết định phù hợp:

| Phần | Nên chịu trách nhiệm | Không nên trở thành nơi chứa |
|---|---|---|
| Presentation/controller | HTTP, xác thực đầu vào ở biên, chuyển request/response và mã trạng thái | Quy tắc nghiệp vụ hoặc truy vấn SQL |
| Application service | Điều phối một use case, gọi các port và domain behavior, xác định ranh giới giao dịch | Toàn bộ phép tính và bất biến nghiệp vụ của mọi chức năng |
| Domain model/domain service | Bất biến, hành vi và chính sách có ý nghĩa nghiệp vụ | HTTP, JPA, gửi email hoặc chi tiết giao thức |
| Infrastructure adapter | Thực hiện I/O bằng JPA, JDBC, HTTP, SMTP, file/object storage | Quyết định nghiệp vụ về việc có được đặt/hủy/hoàn tiền hay không |

Một cách tổ chức thường hữu ích là nhóm application service theo hành động hoặc use case: `PlaceOrderService`, `CancelOrderService`, `GetOrderDetailsService`. Tên lớp cho biết nó điều phối việc gì. Tuy nhiên, không cần tạo lớp riêng cho mọi dòng lệnh. Nếu một số thao tác nhỏ thuộc cùng một use case, có cùng lý do thay đổi và dễ hiểu khi đặt cạnh nhau, chúng có thể ở cùng một lớp.

Ví dụ, các hành động tạo và hủy đơn có thể tách riêng vì chúng có quy trình, dependency và chính sách khác nhau:

```java
@Service
class PlaceOrderService {
    private final ProductRepository products;
    private final OrderRepository orders;
    private final InventoryPort inventory;

    PlaceOrderService(
            ProductRepository products,
            OrderRepository orders,
            InventoryPort inventory) {
        this.products = products;
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        var product = products.findSellableById(command.productId())
                .orElseThrow(ProductNotAvailableException::new);

        inventory.reserve(product.id(), command.quantity());

        var order = Order.place(
                command.customerId(), product, command.quantity());
        orders.save(order);
        return order.id();
    }
}
```

```java
@Service
class CancelOrderService {
    private final OrderRepository orders;
    private final RefundPort refunds;
    private final InventoryPort inventory;

    CancelOrderService(
            OrderRepository orders,
            RefundPort refunds,
            InventoryPort inventory) {
        this.orders = orders;
        this.refunds = refunds;
        this.inventory = inventory;
    }

    @Transactional
    public void cancel(CancelOrderCommand command) {
        var order = orders.findById(command.orderId())
                .orElseThrow(OrderNotFoundException::new);

        var cancellation = order.cancel(command.reason());
        if (cancellation.requiresRefund()) {
            refunds.request(cancellation.paymentReference(), cancellation.refundAmount());
        }
        inventory.release(order.productId(), order.quantity());
        orders.save(order);
    }
}
```

Đây là mã minh họa về ranh giới use case, đã lược bỏ xử lý lỗi và một số chi tiết tích hợp. Hai service có thể dùng chung repository và port, nhưng không cần gom vào một `OrderService` chỉ vì cùng thao tác với đơn hàng. Trong hệ thống thực tế, gọi cổng hoàn tiền hoặc kho bên ngoài không trở thành một phần nguyên tử của transaction database chỉ nhờ `@Transactional`; cần thiết kế retry, idempotency, outbox hoặc quy trình bù trừ theo yêu cầu nhất quán.

## 3. Đưa quy tắc về đúng nơi sở hữu

Tách một service lớn thành nhiều application service sẽ không giải quyết triệt để nếu mọi quy tắc vẫn nằm trong các service mới. Hãy xem quy tắc nào thuộc về trạng thái của entity hoặc value object và chuyển hành vi tới nơi sở hữu dữ liệu đó.

Ví dụ, kiểm tra đơn hàng có thể hủy hay không là quy tắc của đơn hàng:

```java
public class Order {
    private OrderStatus status;
    private final List<OrderLine> lines;

    public Cancellation cancel(String reason) {
        if (status == OrderStatus.SHIPPED || status == OrderStatus.CANCELLED) {
            throw new OrderCannotBeCancelledException();
        }

        status = OrderStatus.CANCELLED;
        return Cancellation.from(this, reason);
    }
}
```

Application service tải `Order`, gọi `order.cancel(...)`, rồi điều phối lưu trữ và các bước liên quan. Như vậy, controller hoặc tác vụ nền không thể bỏ qua bất biến chỉ vì chúng gọi một đường xử lý khác.

Một quy tắc liên quan nhiều đối tượng và không thuộc tự nhiên về một entity có thể đặt trong domain service hoặc policy. Ví dụ, chính sách tính phí giao hàng có thể cần hạng thành viên, địa chỉ và tổng giá trị đơn. Domain service biểu đạt quy tắc đó; application service vẫn chịu trách nhiệm lấy dữ liệu và quyết định thời điểm gọi.

Không nên tạo `OrderDomainService` chỉ để chuyển tiếp `order.cancel()` hoặc tạo `OrderApplicationService` chỉ để gọi `OrderRepository.save()`. Khi hành vi thuộc tự nhiên về entity, hãy để entity thực hiện. Khi thao tác chỉ là I/O, repository adapter thực hiện. Service cần tồn tại khi nó điều phối một use case hoặc biểu đạt một quy tắc miền có ý nghĩa.

## 4. Nhận diện tầng trung gian chỉ chuyển tiếp lời gọi

Một tầng trung gian (pass-through layer) thường chỉ nhận tham số rồi gọi lớp khác với cùng tham số, nhận kết quả rồi trả nguyên vẹn. Nếu nhiều lớp liên tiếp đều làm như vậy, đường đi của một request dài nhưng không có thêm trách nhiệm.

Ví dụ:

```java
@RestController
class OrderController {
    private final OrderFacade facade;

    @GetMapping("/orders/{id}")
    OrderResponse get(@PathVariable UUID id) {
        return facade.get(id);
    }
}

@Service
class OrderFacade {
    private final OrderService service;

    OrderFacade(OrderService service) {
        this.service = service;
    }

    OrderResponse get(UUID id) {
        return service.get(id);
    }
}

@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    OrderResponse get(UUID id) {
        return repository.findById(id)
                .map(OrderResponse::from)
                .orElseThrow(OrderNotFoundException::new);
    }
}
```

Nếu `OrderFacade` không áp dụng chính sách, không chuyển đổi hợp đồng, không điều phối thêm use case và không tạo ranh giới độc lập, nó chỉ tăng một bước điều hướng. Có thể bỏ lớp này để controller gọi trực tiếp application service.

Tuy nhiên, đừng đánh đồng một lớp mỏng với một lớp vô ích. Controller thường mỏng vì trách nhiệm của nó là chuyển giao thức HTTP sang use case; repository adapter có thể mỏng vì trách nhiệm của nó là triển khai port bằng JPA; application service có thể chỉ có vài dòng nhưng vẫn có ý nghĩa vì nó xác định transaction hoặc thứ tự các bước. Độ dài code không phải tiêu chí duy nhất.

## 5. Khi nào tầng trung gian có giá trị?

Một lớp chuyển tiếp có thể đáng giữ nếu nó tạo ra một trong các giá trị sau:

| Giá trị | Ví dụ | Vì sao giữ lớp đó có ích |
|---|---|---|
| Ranh giới giao tiếp ổn định | Controller gọi `GetOrderUseCase`, adapter triển khai `OrderRepository` | Phần gọi không phụ thuộc vào công nghệ hoặc chi tiết triển khai |
| Chuyển đổi mô hình | HTTP request DTO thành command; JPA entity thành domain object | Mỗi tầng giữ kiểu dữ liệu phù hợp với trách nhiệm của mình |
| Điều phối use case | Tải đơn, kiểm tra chính sách, yêu cầu hoàn tiền và lưu kết quả | Có một nơi thể hiện trình tự và lỗi của ca sử dụng |
| Chính sách dùng chung | Kiểm tra quyền truy cập, chuẩn hóa đầu vào hoặc áp dụng tenant scope | Nhiều điểm vào tuân theo cùng một quy tắc |
| Ranh giới transaction | `@Transactional` bao quanh thao tác đọc/thay đổi/lưu | Phạm vi nhất quán của use case được thể hiện rõ |
| Điểm thay thế và kiểm thử | Port cho cổng thanh toán hoặc hệ thống vận chuyển | Có thể thay adapter và kiểm thử use case mà không gọi hệ thống thật |
| Quan sát hoặc bảo vệ tài nguyên | Timeout, retry, metric, tracing hoặc circuit breaker tại adapter | Chi tiết kỹ thuật được tập trung đúng nơi |

Ví dụ, `OrderRepository` có thể chỉ có `findById` và `save`, nhưng interface vẫn có giá trị nếu nó là hợp đồng mà application sở hữu, còn `JpaOrderRepositoryAdapter` chuyển đổi entity và thực hiện persistence. Ngược lại, nếu `OrderService` chỉ gọi `repository.findById(id)` và trả nguyên entity mà không có chính sách hay hợp đồng use case nào, cần xem liệu controller có đang phụ thuộc trực tiếp vào persistence model hay service có đang tồn tại chỉ để đổi tên một phương thức.

## 6. Đừng xóa nhầm ranh giới của tầng trình bày và truy cập dữ liệu

Một controller mỏng không phải là pass-through layer cần loại bỏ. Controller nhận request, kiểm tra cấu trúc đầu vào, lấy thông tin xác thực, gọi use case và ánh xạ kết quả sang HTTP. Nó là ranh giới giữa giao thức bên ngoài và ứng dụng. Việc không chứa quy tắc nghiệp vụ là dấu hiệu tốt.

Tương tự, repository adapter có thể chuyển tiếp một lời gọi từ port sang Spring Data repository. Sự chuyển tiếp đó có thể cần thiết để chuyển đổi domain model và entity, thêm điều kiện tenant, xử lý truy vấn hoặc che giấu công nghệ lưu trữ. Nếu không có khác biệt nào và việc dùng chung một interface không tạo lợi ích, có thể cân nhắc đơn giản hóa, nhưng phải đánh giá sự phụ thuộc của các tầng trước khi bỏ adapter.

Không nên tạo các lớp `Manager`, `Helper`, `Facade`, `Delegate` hoặc `Processor` chỉ vì tên gọi nghe có vẻ có cấu trúc. Hãy mô tả trách nhiệm cụ thể trong tên lớp và phương thức. `PlaceOrderService` cho biết use case; `OrderJpaAdapter` cho biết công nghệ và vai trò; `OrderManager` không cho người đọc biết nó quản lý điều gì.

## 7. Refactor service khổng lồ theo từng bước

Tách service lớn an toàn hơn khi bắt đầu từ hành vi hiện có và giữ nguyên hợp đồng bên ngoài trong giai đoạn đầu:

1. **Liệt kê use case và dependency.** Nhóm các phương thức theo hành động thực tế, ghi lại dữ liệu và hệ thống mà từng nhóm sử dụng.
2. **Tìm quy tắc nghiệp vụ.** Xác định bất biến thuộc entity/value object và chính sách liên quan nhiều khái niệm; không sao chép chúng sang service mới.
3. **Chọn một use case để tách trước.** Ưu tiên phần có ranh giới rõ, ít phụ thuộc chéo và có test bảo vệ.
4. **Tạo application service mới.** Chuyển phần điều phối của use case, giữ nguyên thứ tự nghiệp vụ và xử lý lỗi.
5. **Đưa hành vi về domain khi phù hợp.** Thay các đoạn code sửa trực tiếp field bằng phương thức bảo vệ bất biến.
6. **Cập nhật composition root hoặc dependency injection.** Để controller, job hoặc message handler gọi use case mới.
7. **Xóa phương thức cũ khi mọi caller đã chuyển.** Không giữ hai đường xử lý cùng tồn tại lâu dài nếu chúng có thể lệch hành vi.
8. **Lặp lại theo từng nhóm trách nhiệm.** Tránh một lần refactor lớn làm thay đổi đồng thời nhiều use case khó kiểm soát.

Nếu cần giữ API tạm thời cho caller cũ, có thể dùng một facade tương thích chuyển tiếp tới use case mới. Hãy xem đó là bước chuyển đổi có thời hạn, có người chịu trách nhiệm và có kế hoạch xóa. Nếu facade tồn tại vĩnh viễn mà không còn vai trò riêng, nó sẽ trở thành một tầng pass-through.

## 8. Ví dụ trước và sau khi refactor

Giả sử `OrderService` ban đầu chứa `place`, `cancel`, `search` và `export`. Sau khi xem xét, ta nhận thấy:

| Hành vi cũ | Trách nhiệm mới | Lý do |
|---|---|---|
| `place()` | `PlaceOrderService` + `Order.place()` | Điều phối tạo đơn và bảo vệ bất biến đơn hàng |
| `cancel()` | `CancelOrderService` + `Order.cancel()` | Quy trình hủy khác tạo đơn, có thể gọi hoàn tiền và giải phóng kho |
| `search()` | `SearchOrdersService` và query port | Truy vấn đọc có bộ lọc/phân trang riêng, không cần tải aggregate nếu chỉ hiển thị projection |
| `export()` | `ExportOrdersService` và file/report adapter | Xuất báo cáo là use case riêng, phụ thuộc định dạng và nơi lưu tệp |

Sau khi tách, các use case vẫn có thể dùng chung `OrderRepository`, `OrderPolicy` hoặc một thành phần tính toán có ý nghĩa. Mục tiêu không phải loại bỏ mọi chia sẻ, mà đặt phần dùng chung ở nơi sở hữu khái niệm và giữ từng use case tập trung vào một mục tiêu.

Nếu hai use case luôn thay đổi cùng nhau, có cùng chính sách và chỉ khác tên phương thức, việc tách riêng có thể làm code phân mảnh không cần thiết. Khi đó một application service có một nhóm hành vi liên quan vẫn hợp lý. Quyết định nên dựa vào cohesion, lý do thay đổi và mức độ độc lập của use case.

## 9. Kiểm thử để xác nhận ranh giới sau refactor

Sau khi tách lớp, cần xác nhận cả hành vi và cấu trúc mới:

| Mức kiểm thử | Điều cần kiểm tra | Ví dụ |
|---|---|---|
| Unit test domain | Bất biến và hành vi không phụ thuộc I/O | Đơn đã giao không thể bị hủy; số lượng dòng hàng phải hợp lệ |
| Unit test application | Thứ tự điều phối và nhánh use case | Hủy đơn yêu cầu hoàn tiền đúng một lần khi trạng thái cho phép |
| Controller test | Hợp đồng HTTP, validation và ánh xạ lỗi | Request không hợp lệ trả `400`, đơn không tồn tại trả `404` |
| Adapter integration test | Chuyển đổi và tích hợp với công nghệ thật | JPA adapter lưu/tải đúng aggregate |
| Architecture test | Dependency đi đúng chiều, không có package cấm | Application không import infrastructure; controller không gọi repository adapter |

Test application service không nên phải mock hàng chục dependency chỉ để kiểm tra một use case đơn giản. Nếu test cần nhiều mock, hãy xem use case có đang điều phối quá nhiều việc hay các port có bị thiết kế quá rộng. Tuy nhiên, số mock không phải chỉ số tuyệt đối: một use case thực sự cần phối hợp nhiều hệ thống có thể có nhiều collaborator hợp lý.

Các kiểm thử kiến trúc như ArchUnit có thể giúp giữ quy tắc: controller phụ thuộc use case, domain không phụ thuộc Spring hoặc persistence, và application không phụ thuộc adapter cụ thể. Kiểm tra này bổ sung cho unit/integration test; nó không thay thế kiểm tra kết quả nghiệp vụ.

## 10. Câu hỏi dùng trong review thiết kế

Khi review một service mới hoặc một lớp trung gian, hãy hỏi:

1. Lớp này phục vụ use case hoặc khái niệm nghiệp vụ nào? Tên lớp có nói rõ trách nhiệm đó không?
2. Những lý do độc lập nào có thể khiến lớp phải thay đổi? Các phương thức có cùng một mục tiêu và cùng nhóm dependency không?
3. Quy tắc nào thuộc entity/value object nhưng hiện đang nằm trong service hoặc controller?
4. Lớp trung gian có chuyển đổi hợp đồng, điều phối, bảo vệ chính sách, xác định transaction hoặc tạo điểm thay thế không?
5. Nếu xóa lớp này, tầng gọi có phải biết chi tiết công nghệ hoặc thực hiện thêm trách nhiệm không?
6. Nếu giữ lớp này, nó có tạo một bước điều hướng mà không tạo giá trị nào không?
7. Có thể kiểm thử use case và domain ở đúng ranh giới mà không khởi động toàn bộ ứng dụng không?

| Dấu hiệu | Hướng xem xét |
|---|---|
| Một service có nhiều nhóm use case không liên quan và dependency dày đặc | Tách theo use case hoặc capability có cohesion rõ |
| Application service chứa nhiều quy tắc thao tác trạng thái entity | Chuyển hành vi về domain model hoặc domain policy phù hợp |
| Controller gọi repository trực tiếp và tự phối hợp nhiều bước | Bổ sung application service có trách nhiệm điều phối |
| Nhiều lớp chỉ nhận rồi chuyển tiếp cùng tham số/kết quả | Xem có thể gộp hoặc bỏ lớp không có ranh giới hữu ích |
| Adapter mỏng nhưng triển khai port và chuyển đổi mô hình | Thường nên giữ vì nó bảo vệ ranh giới hạ tầng |
| Service mỏng nhưng xác định transaction và điều phối use case | Có thể giữ; độ mỏng không làm mất giá trị của trách nhiệm |

## 11. Cân bằng giữa tập trung và phân mảnh

Một thiết kế tốt không phải là thiết kế có ít lớp nhất hoặc nhiều lớp nhất. Service khổng lồ làm nhiều trách nhiệm phụ thuộc vào cùng một điểm; quá nhiều tầng chuyển tiếp làm người đọc phải đi qua nhiều lớp mà không hiểu thêm điều gì. Cả hai đều khiến thay đổi khó dự đoán.

Hãy nhóm code theo lý do thay đổi và khái niệm mà nó phục vụ. Giữ controller tập trung vào giao thức, application service tập trung vào use case, domain model bảo vệ quy tắc và adapter thực hiện I/O. Tạo lớp trung gian khi nó thể hiện hợp đồng, chuyển đổi, điều phối hoặc chính sách có ích. Khi một lớp chỉ chuyển tiếp lời gọi, hãy cân nhắc loại bỏ; khi một lớp đang gánh nhiều mục tiêu độc lập, hãy tách nó theo trách nhiệm.

Trong kiến trúc phân tầng, điều quan trọng là mỗi ranh giới phải giúp người đọc biết quyết định nào thuộc về đâu và thay đổi nào có thể ảnh hưởng đến phần nào. Khi review và refactor theo tiêu chí đó, codebase có thể giữ được cấu trúc rõ ràng mà không biến mọi thao tác thành một chuỗi service dài hoặc tập trung toàn bộ ứng dụng vào một lớp duy nhất.
