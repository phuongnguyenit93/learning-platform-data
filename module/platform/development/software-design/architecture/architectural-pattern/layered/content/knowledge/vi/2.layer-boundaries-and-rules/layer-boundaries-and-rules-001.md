# Xác định trách nhiệm và tiêu chí đặt chức năng vào đúng tầng

Trong kiến trúc phân tầng, một chức năng được đặt vào tầng phù hợp dựa trên **trách nhiệm mà nó đảm nhận**, **loại kiến thức mà nó cần biết** và **những thành phần mà nó được phép phụ thuộc**. Mục tiêu là để mỗi phần của hệ thống có lý do thay đổi tương đối rõ ràng: thay đổi giao thức giao tiếp không làm xáo trộn quy tắc nghiệp vụ, thay đổi cách lưu dữ liệu không buộc giao diện phải thay đổi, và các quy tắc cốt lõi vẫn có thể được kiểm tra độc lập.

Tầng (layer) là ranh giới logic trong mã nguồn. Nó không nhất thiết tương ứng với một tiến trình, máy chủ hay container riêng. Một ứng dụng Spring Boot có thể chứa nhiều tầng logic trong cùng một tiến trình và kết nối tới một cơ sở dữ liệu ở tiến trình khác. Số tầng cũng không cố định: một ứng dụng nhỏ có thể dùng ba tầng; một hệ thống cần ranh giới rõ hơn có thể tách phần điều phối ca sử dụng khỏi mô hình nghiệp vụ và tách truy cập dữ liệu thành các adapter riêng.

## 1. Nhận diện trách nhiệm của từng tầng

Một cách phân chia thường gặp là giao diện, ứng dụng, nghiệp vụ và truy cập dữ liệu/hạ tầng. Đây là các nhóm trách nhiệm để suy nghĩ và thiết kế; không phải quy định rằng mọi dự án đều phải có đúng bốn thư mục hoặc bốn module.

| Tầng | Câu hỏi chính | Trách nhiệm phù hợp | Ví dụ |
|---|---|---|---|
| Giao diện (presentation) | Hệ thống nhận yêu cầu và trả kết quả qua cách nào? | Xử lý giao thức, nhận dữ liệu đầu vào, kiểm tra cấu trúc và định dạng, chuyển đổi request/response, ánh xạ lỗi sang mã phản hồi. | REST controller, trang web, CLI, message listener ở biên hệ thống. |
| Ứng dụng (application) | Hệ thống thực hiện ca sử dụng nào và phối hợp các bước ra sao? | Điều phối một luồng công việc, gọi các đối tượng nghiệp vụ và cổng cần thiết, xác định ranh giới giao dịch, phối hợp các bước và trả kết quả của ca sử dụng. | Đặt hàng, hủy đơn, đăng ký tài khoản, tạo báo cáo. |
| Nghiệp vụ (domain/business) | Quy tắc và trạng thái nào phải đúng bất kể người dùng hay công nghệ lưu trữ? | Biểu diễn khái niệm nghiệp vụ, bất biến, phép tính, chính sách và chuyển trạng thái. | Đơn hàng không được xác nhận khi chưa có dòng hàng; số tiền chiết khấu tuân theo chính sách bán hàng. |
| Truy cập dữ liệu/hạ tầng (data access/infrastructure) | Hệ thống trao đổi với cơ sở dữ liệu hoặc dịch vụ bên ngoài bằng cách nào? | Thực thi truy vấn, ánh xạ dữ liệu lưu trữ, gọi API bên ngoài, gửi thông điệp, đọc/ghi tệp và triển khai các cổng kỹ thuật. | Spring Data repository, JPA adapter, HTTP client, message publisher. |

**Tầng giao diện** biết về HTTP, JSON, biểu mẫu hoặc giao thức tương ứng. Nó có thể kiểm tra một trường có bị thiếu, chuỗi có đúng định dạng hay số lượng có phải là số dương theo hợp đồng request hay không. Nó không nên tự quyết định một đơn hàng có đủ điều kiện được xác nhận hay tự tính chính sách chiết khấu.

**Tầng ứng dụng** mô tả hành động mà hệ thống cung cấp. Một ca sử dụng thường tải dữ liệu cần thiết, gọi các hành vi nghiệp vụ, phối hợp các cổng lưu trữ hoặc dịch vụ, rồi lưu kết quả. Tầng này có thể quyết định thứ tự các bước và ranh giới giao dịch, nhưng không nên trở thành nơi chứa mọi quy tắc nghiệp vụ chỉ vì nó có tên là Service.

**Tầng nghiệp vụ** giữ những quy tắc cần đúng dù yêu cầu đến từ REST API, tác vụ nền hay một giao diện khác. Quy tắc nên được đặt gần dữ liệu và khái niệm nghiệp vụ mà nó bảo vệ. Ví dụ, điều kiện chuyển đơn hàng từ trạng thái nháp sang đã xác nhận thuộc về hành vi của đơn hàng hoặc chính sách nghiệp vụ, thay vì nằm trong controller.

**Tầng truy cập dữ liệu/hạ tầng** biết cách làm việc với công nghệ cụ thể. Nó chuyển đổi giữa mô hình mà ứng dụng/nghiệp vụ sử dụng và cấu trúc lưu trữ, xử lý chi tiết SQL/ORM, hoặc giao tiếp với hệ thống ngoài. Quy tắc như “không cho phép xác nhận đơn rỗng” không nên bị giấu trong câu truy vấn hay callback của ORM.

Một số hệ thống gộp ứng dụng và nghiệp vụ vào một tầng business; hệ thống khác tách chúng vì luồng điều phối và quy tắc nghiệp vụ có nhịp thay đổi khác nhau. Tương tự, truy cập dữ liệu có thể chỉ là một phần của tầng hạ tầng. Hãy tách khi sự khác biệt về trách nhiệm tạo ra lợi ích rõ ràng, thay vì tạo thêm tầng chỉ để có cấu trúc thư mục đẹp.

## 2. Tiêu chí quyết định một chức năng thuộc tầng nào

Khi chưa rõ nên đặt một hàm, lớp hoặc quy tắc ở đâu, hãy lần lượt đặt các câu hỏi sau.

1. **Chức năng đang xử lý giao thức hay hợp đồng tương tác?** Nếu nó đọc HTTP header, giải mã JSON, chuyển request thành lệnh, định dạng response hoặc ánh xạ lỗi sang HTTP status, nó thuộc biên giao diện. Với một giao thức khác, biên có thể là CLI, consumer hoặc adapter tương ứng.
2. **Chức năng đang điều phối một mục tiêu của người dùng/hệ thống?** Nếu nó xác định ca sử dụng, gọi nhiều thành phần theo trình tự, mở giao dịch hoặc phối hợp lưu kết quả, nó thường thuộc tầng ứng dụng.
3. **Chức năng đang bảo vệ một sự thật nghiệp vụ?** Nếu quy tắc phải đúng dù được gọi từ API, batch job hay kiểm thử, hãy đặt nó trong mô hình nghiệp vụ hoặc một dịch vụ/chính sách nghiệp vụ phù hợp.
4. **Chức năng đang chuyển đổi hoặc giao tiếp với công nghệ bên ngoài?** Nếu nó biết bảng SQL, entity của ORM, URL của dịch vụ, định dạng message hay đường dẫn tệp, nó thuộc tầng truy cập dữ liệu/hạ tầng.
5. **Chức năng thay đổi vì lý do nào?** Nếu nó thay đổi khi API đổi phiên bản, đó là dấu hiệu của giao diện. Nếu nó thay đổi khi quy trình nghiệp vụ đổi, đó là dấu hiệu của ứng dụng. Nếu nó thay đổi khi chính sách nghiệp vụ đổi, đó là dấu hiệu của domain. Nếu nó thay đổi khi đổi PostgreSQL sang một hệ quản trị khác, đó là dấu hiệu của hạ tầng.

Không phải lúc nào một lớp cũng chỉ chứa một dòng lệnh của một loại. Một ca sử dụng có thể đi qua nhiều tầng; điều cần tách là những phần có trách nhiệm khác nhau. Ví dụ, kiểm tra số lượng ở request để trả lỗi đầu vào sớm là hợp lý, nhưng domain vẫn phải bảo vệ bất biến số lượng hợp lệ vì một tác nhân khác có thể gọi domain mà không đi qua REST controller.

### Một số trường hợp dễ nhầm

| Chức năng | Nơi đặt thường phù hợp | Lý do |
|---|---|---|
| Kiểm tra JSON có trường bắt buộc, ngày có đúng định dạng | Giao diện | Đây là hợp đồng của request. |
| Kiểm tra đơn hàng phải có ít nhất một dòng hàng | Nghiệp vụ | Đây là bất biến của đơn hàng, không phụ thuộc giao thức. |
| Tải sản phẩm, gọi hành vi tạo đơn, lưu đơn trong một ca sử dụng | Ứng dụng | Đây là điều phối các bước. |
| Tính mức giảm giá theo chính sách khách hàng | Nghiệp vụ | Đây là quyết định kinh doanh. |
| Mở giao dịch cho ca sử dụng đặt hàng | Ứng dụng | Giao dịch bao quanh một đơn vị công việc. |
| Viết câu truy vấn hoặc ánh xạ bản ghi sang đối tượng | Truy cập dữ liệu/hạ tầng | Đây là chi tiết lưu trữ. |
| Chuyển ngoại lệ nghiệp vụ thành HTTP 409 | Giao diện | Mã HTTP là cách biểu diễn lỗi ở biên. |
| Xác thực token và tích hợp cơ chế đăng nhập | Biên bảo mật/hạ tầng | Đây là cơ chế kỹ thuật; quyền thực hiện hành động vẫn cần được kiểm tra theo ngữ cảnh nghiệp vụ ở ca sử dụng hoặc chính sách domain. |

Một quy tắc hữu ích là phân biệt **kiểm tra dữ liệu đầu vào** với **kiểm tra tính hợp lệ nghiệp vụ**. Ví dụ, annotation @Positive trên request có thể từ chối số lượng âm trước khi vào ca sử dụng. Tuy nhiên, đối tượng dòng hàng vẫn cần bảo vệ điều kiện số lượng dương nếu điều kiện đó là bất biến. Việc kiểm tra ở hai nơi có mục đích khác nhau: một nơi bảo vệ hợp đồng giao tiếp, nơi kia bảo vệ trạng thái nghiệp vụ.

## 3. Ví dụ luồng đặt hàng trong Java và Spring

Giả sử ứng dụng cung cấp API tạo đơn hàng. Người dùng gửi mã khách hàng và các dòng sản phẩm. Luồng xử lý có thể được chia như sau:

1. Controller nhận HTTP request, kiểm tra cấu trúc request và chuyển nó thành lệnh của ứng dụng.
2. Dịch vụ ứng dụng tải thông tin sản phẩm cần thiết, phối hợp việc tạo đơn và lưu kết quả trong một giao dịch.
3. Mô hình nghiệp vụ kiểm tra các bất biến và tạo trạng thái đơn hợp lệ.
4. Adapter lưu trữ chuyển đối tượng nghiệp vụ sang dạng dữ liệu phù hợp với JPA/cơ sở dữ liệu.

Controller chỉ điều phối giao tiếp HTTP:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderId id = placeOrder.handle(
            new PlaceOrderCommand(request.customerId(), request.lines()));

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new OrderResponse(id.value()));
    }
}
~~~

Controller không tự truy vấn bảng sản phẩm, tính tổng tiền hay quyết định trạng thái đơn. Những việc đó thuộc các trách nhiệm khác. Các kiểu CreateOrderRequest, PlaceOrderCommand và OrderResponse là ví dụ về mô hình dữ liệu ở ranh giới; dự án có thể tổ chức chúng theo quy ước riêng.

Dịch vụ ứng dụng phối hợp các bước:

~~~java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductRepository products;
    private final OrderRepository orders;

    PlaceOrderService(ProductRepository products, OrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Override
    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        List<OrderLine> lines = command.lines().stream()
            .map(line -> {
                Product product = products.findById(line.productId())
                    .orElseThrow(ProductNotFoundException::new);

                return OrderLine.of(
                    product.id(), line.quantity(), product.price());
            })
            .toList();

        Order order = Order.place(command.customerId(), lines);
        orders.save(order);
        return order.id();
    }
}
~~~

Đoạn mã minh họa một ca sử dụng đơn giản: lấy dữ liệu sản phẩm, tạo các dòng hàng, yêu cầu domain tạo đơn và lưu đơn. Trong hệ thống thực tế, việc giữ giá tại thời điểm đặt hàng, kiểm tra tồn kho, giữ chỗ hàng hoặc xử lý thanh toán có thể cần các chính sách và bước phối hợp riêng. Hãy đặt từng quy tắc ở nơi sở hữu kiến thức đó, còn thứ tự phối hợp thuộc tầng ứng dụng.

Mô hình nghiệp vụ tự bảo vệ bất biến:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;

    private Order(OrderId id, CustomerId customerId, List<OrderLine> lines) {
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
    }

    public static Order place(CustomerId customerId, List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new EmptyOrderException();
        }
        if (lines.stream().anyMatch(line -> line.quantity() <= 0)) {
            throw new InvalidOrderQuantityException();
        }
        return new Order(OrderId.newId(), customerId, lines);
    }

    public OrderId id() {
        return id;
    }
}
~~~

Trong ví dụ này, domain không cần biết request đến từ HTTP hay dữ liệu được lưu bằng JPA. Nó nhận những khái niệm nghiệp vụ và bảo đảm đơn được tạo theo các điều kiện đã định nghĩa. Trong ứng dụng thật, việc kiểm tra có thể được đóng gói trong constructor, value object hoặc phương thức hành vi; ví dụ trên chỉ minh họa vị trí của quy tắc.

Adapter lưu trữ triển khai cổng mà ứng dụng sử dụng:

~~~java
@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderJpaRepository springData;

    JpaOrderRepositoryAdapter(SpringDataOrderJpaRepository springData) {
        this.springData = springData;
    }

    @Override
    public void save(Order order) {
        springData.save(OrderEntity.fromDomain(order));
    }
}
~~~

OrderRepository là hợp đồng mà ca sử dụng cần. JpaOrderRepositoryAdapter biết cách dùng Spring Data và chuyển đổi sang OrderEntity. Tùy thiết kế, hợp đồng repository có thể nằm trong package ứng dụng hoặc domain: hãy đặt nó tại nơi sở hữu nhu cầu nghiệp vụ đối với thao tác lưu/truy xuất. Điểm quan trọng là logic ứng dụng/domain phụ thuộc vào hợp đồng cần thiết, còn chi tiết Spring Data/JPA nằm trong adapter triển khai hợp đồng đó.

Luồng gọi khi chạy thường đi từ controller đến dịch vụ ứng dụng, qua cổng repository, rồi đến adapter và cơ sở dữ liệu. Hướng phụ thuộc mã nguồn có thể chi tiết hơn: adapter triển khai interface mà ứng dụng/domain định nghĩa, nên ứng dụng không cần import lớp triển khai JPA. Phân biệt luồng gọi lúc chạy với hướng phụ thuộc lúc biên dịch giúp tránh kết luận sai rằng mọi mũi tên trong sơ đồ đều phải chỉ cùng một hướng.

## 4. Quy tắc về ranh giới và hướng phụ thuộc

Một tầng chỉ nên biết những hợp đồng cần thiết để hoàn thành trách nhiệm của nó. Khi một lớp ở tầng trên gọi trực tiếp chi tiết của tầng dưới cùng, nó thường tạo ra liên kết chặt và làm cho việc thay đổi tầng dưới lan lên nhiều nơi.

Trong mô hình phân tầng đóng (closed layering), một tầng chỉ được sử dụng tầng kế tiếp theo quy ước. Ví dụ, giao diện gọi ứng dụng; ứng dụng gọi nghiệp vụ và các cổng cần thiết; adapter hạ tầng thực hiện các cổng đó. Quy tắc này buộc luồng xử lý đi qua nơi có thể áp dụng kiểm tra, chính sách và điều phối chung.

Trong mô hình phân tầng mở (open layering), một tầng được phép sử dụng trực tiếp một tầng thấp hơn mà không đi qua tầng trung gian. Điều này đôi khi hữu ích cho một truy vấn chỉ đọc hoặc một đường xử lý đặc biệt cần giảm bước trung gian. Tuy nhiên, nếu mọi nơi đều có thể bỏ qua tầng ứng dụng, quy tắc quyền truy cập, giao dịch và điều phối có thể bị phân tán. Vì vậy, ngoại lệ nên có lý do cụ thể, được ghi nhận và có kiểm thử bảo vệ.

Một số nguyên tắc thực hành:

- Không để controller gọi trực tiếp repository chỉ vì thao tác hiện tại có vẻ đơn giản, nếu việc đó bỏ qua quyền truy cập, giao dịch hoặc quy tắc dùng chung của ca sử dụng.
- Không để domain import HttpServletRequest, ResponseEntity, JpaRepository hoặc kiểu dữ liệu đặc thù của một dịch vụ bên ngoài.
- Không để repository quyết định chính sách như “khách hàng hạng vàng được giảm 10%”. Repository truy xuất dữ liệu; chính sách thuộc domain.
- Đặt ranh giới giao dịch ở nơi bao trọn đơn vị công việc ứng dụng. Không mở một giao dịch riêng cho từng câu lệnh nhỏ nếu ca sử dụng cần tính nhất quán xuyên suốt.
- Nếu một chức năng cần biết cả giao thức, quy tắc nghiệp vụ và SQL, hãy tách nó thành các phần có hợp đồng rõ ràng thay vì chuyển nguyên khối sang một tầng.

Các nguyên tắc này không yêu cầu mọi dự án phải áp dụng đầy đủ Domain-Driven Design hay một kiểu tổ chức package cụ thể. Với ứng dụng CRUD nhỏ, mô hình đơn giản có thể phù hợp. Khi quy tắc nghiệp vụ tăng lên, có nhiều điểm vào hệ thống hoặc cần thay thế công nghệ, việc tách ranh giới rõ hơn sẽ có giá trị lớn hơn.

## 5. Kiểm tra xem chức năng đã được đặt đúng tầng chưa

Kiểm thử cũng có thể phản ánh ranh giới kiến trúc:

- **Domain test:** kiểm tra bất biến, phép tính và chuyển trạng thái mà không cần khởi động Spring hoặc cơ sở dữ liệu.
- **Application test:** dùng repository giả hoặc stub để kiểm tra ca sử dụng gọi đúng bước, xử lý kết quả và phối hợp các cổng theo mong đợi.
- **Presentation test:** kiểm tra endpoint nhận request, gọi đúng ca sử dụng và ánh xạ kết quả/lỗi thành response phù hợp.
- **Infrastructure integration test:** kiểm tra adapter với cơ sở dữ liệu, ORM, message broker hoặc dịch vụ ngoài thực tế.

Nếu muốn kiểm tra một quy tắc nghiệp vụ mà phải dựng HTTP server và cơ sở dữ liệu, đó có thể là dấu hiệu quy tắc đang bị đặt quá xa domain hoặc bị gắn chặt với hạ tầng. Ngược lại, nếu một bài kiểm thử controller phải mô phỏng nhiều bước nghiệp vụ, controller có thể đang gánh quá nhiều trách nhiệm.

Trước khi chốt vị trí của một chức năng, hãy tự kiểm tra:

- Chức năng đang phục vụ giao thức, điều phối ca sử dụng, bảo vệ quy tắc nghiệp vụ hay tích hợp công nghệ?
- Nó cần biết những khái niệm và chi tiết nào? Có đang phụ thuộc vào chi tiết của tầng khác không?
- Nếu đổi giao diện, chính sách nghiệp vụ hoặc công nghệ lưu trữ, phần nào thực sự cần thay đổi?
- Quy tắc có được bảo vệ khi ca sử dụng được gọi từ một điểm vào khác không?
- Có thể kiểm thử trách nhiệm đó ở phạm vi nhỏ hơn mà không dựng toàn bộ ứng dụng không?

Một thiết kế phân tầng tốt giúp người đọc nhận ra nơi cần tìm khi một yêu cầu thay đổi. Controller xử lý cách giao tiếp, application điều phối công việc, domain bảo vệ quy tắc và hạ tầng xử lý chi tiết kỹ thuật. Khi ranh giới được đặt theo trách nhiệm và hướng phụ thuộc được kiểm soát, mỗi tầng có thể thay đổi với ít tác động ngoài phạm vi của nó hơn.

