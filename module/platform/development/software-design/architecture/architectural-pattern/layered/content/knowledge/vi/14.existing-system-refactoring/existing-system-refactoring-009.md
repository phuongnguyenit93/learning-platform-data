# Đánh giá kết quả bằng chi phí thay đổi, kết dính và khả năng kiểm thử

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** (Học tổ chức phần mềm theo kiến trúc phân tầng), cải tiến hệ thống hiện có không kết thúc khi mã nguồn đã được chia thành nhiều package hoặc service nhỏ hơn. Cần đánh giá xem cấu trúc mới có giúp nhóm thay đổi phần mềm an toàn và ít tốn công hơn hay không. Bài học này tập trung vào ba góc nhìn: chi phí thay đổi, độ kết dính và khả năng kiểm thử.

Ta dùng một hệ thống quản lý đơn hàng làm ví dụ. Ban đầu, một lớp `OrderService` xử lý HTTP request, tính giá, kiểm tra tồn kho, cập nhật trạng thái, lưu JPA entity và gửi email. Sau một đợt refactor, trách nhiệm được tách thành controller, application use case, mô hình miền và các adapter. Việc có thêm lớp chưa chứng minh kiến trúc tốt hơn. Kết quả cần được đánh giá bằng những thay đổi mà nhóm thực sự phải thực hiện, mức độ lan truyền của thay đổi và khả năng phát hiện lỗi.

## 1. Đánh giá refactor bằng kết quả có thể quan sát

Refactor là thay đổi cấu trúc bên trong nhằm cải thiện thiết kế mà vẫn giữ hành vi được quan sát từ bên ngoài. Vì vậy, đánh giá cần trả lời hai câu hỏi:

1. Hành vi hiện tại có được giữ nguyên trong phạm vi refactor không?
2. Cấu trúc mới có làm những thay đổi tương lai trở nên dễ dự đoán, ít rủi ro và dễ kiểm tra hơn không?

Một đợt refactor có thể làm số lớp tăng lên nhưng chi phí thay đổi giảm. Ngược lại, nó cũng có thể tạo nhiều interface, mapper và service chuyển tiếp mà không làm trách nhiệm rõ hơn.

| Góc nhìn | Điều cần đánh giá | Dấu hiệu cải thiện |
|---|---|---|
| Chi phí thay đổi | Một yêu cầu mới cần sửa bao nhiêu phần và mất bao nhiêu công sức? | Thay đổi tập trung, ít sửa chéo, review và triển khai dễ hơn |
| Độ kết dính (cohesion) | Các thành phần trong một module có phục vụ cùng một mục đích rõ ràng không? | Logic liên quan nằm gần nhau, ít lý do thay đổi không liên quan |
| Khả năng kiểm thử (testability) | Có thể kiểm tra quy tắc và use case với mức cô lập phù hợp không? | Test nhanh, rõ, ổn định và phát hiện lỗi có ý nghĩa |
| Tính an toàn khi thay đổi | Có phát hiện được hồi quy và giới hạn phạm vi ảnh hưởng không? | Hợp đồng rõ, test đúng tầng, ít lỗi lan sang chức năng khác |

Không có một chỉ số duy nhất mô tả đầy đủ chất lượng kiến trúc. Cần kết hợp số liệu, ví dụ thay đổi thực tế, phản hồi của người phát triển và bằng chứng từ kiểm thử.

## 2. Đo chi phí thay đổi bằng các công việc thực tế

Chi phí thay đổi là công sức và rủi ro cần bỏ ra để điều chỉnh phần mềm khi yêu cầu thay đổi. Không nên chỉ đếm số dòng code hoặc số file sửa. Một thay đổi chạm nhiều file có thể vẫn hợp lý nếu mỗi file thuộc một trách nhiệm cần thiết; một thay đổi chỉ sửa một file có thể rất rủi ro nếu file đó chứa nhiều chính sách không liên quan.

Có thể theo dõi một số dấu hiệu:

- **Thời gian từ lúc bắt đầu đến khi hoàn tất thay đổi:** gồm tìm hiểu, sửa mã, viết test, review và sửa hồi quy.
- **Số thành phần phải hiểu hoặc sửa:** controller, service, entity, repository, batch job, message consumer và các adapter khác.
- **Số nơi chứa cùng một quy tắc:** nếu chính sách giảm giá được lặp ở API, tác vụ nền và báo cáo, mỗi lần đổi chính sách đều phải tìm đủ các bản sao.
- **Phạm vi kiểm thử hồi quy:** một thay đổi nhỏ có buộc chạy hoặc sửa rất nhiều test không liên quan không?
- **Số lỗi phát sinh sau thay đổi:** đặc biệt là lỗi do một module khác bị ảnh hưởng ngoài dự kiến.
- **Độ khó khi review:** reviewer có thể xác định quy tắc thay đổi và tác động của nó qua một luồng rõ ràng không?

Ví dụ, yêu cầu mới là áp dụng phí giao hàng theo khu vực. Trước refactor, logic có thể nằm rải rác trong `OrderController`, `OrderService`, `CheckoutBatchJob` và `OrderEntity`. Nhóm phải tìm từng vị trí để tránh tính phí khác nhau giữa đặt hàng trực tuyến và xử lý đơn hàng theo lô.

Sau refactor, nếu việc tính phí được tập trung trong một chính sách được application use case sử dụng, thay đổi có thể chỉ cần cập nhật chính sách và các test liên quan. Chi phí giảm vì quy tắc có một nơi sở hữu rõ ràng, không phải vì số dòng code ít hơn.

### So sánh bằng một bảng thay đổi

| Công việc | Trước refactor | Sau refactor có ranh giới rõ |
|---|---|---|
| Tìm nơi tính phí | Tìm nhiều controller/job/service | Tìm chính sách định giá |
| Sửa quy tắc | Cập nhật nhiều bản sao | Cập nhật một nơi có trách nhiệm |
| Kiểm tra | Test qua nhiều đường gọi, setup phức tạp | Test chính sách và use case theo phạm vi |
| Rủi ro | Một đường xử lý có thể bị bỏ sót | Các đường vào dùng chung quy tắc |
| Review | Khó biết thay đổi ảnh hưởng nơi nào | Hợp đồng và dependency dễ lần theo |

Bảng này là ví dụ về dấu hiệu mong đợi, không phải cam kết rằng mọi refactor đều làm giảm số file hoặc thời gian ngay lập tức. Đợt đầu có thể cần thêm test, adapter và mapper nên chi phí ngắn hạn tăng. Hãy đánh giá lợi ích trên các thay đổi lặp lại trong tương lai.

## 3. Phạm vi lan truyền của thay đổi và coupling

Coupling (mức độ phụ thuộc) mô tả một thành phần cần biết hoặc bị ảnh hưởng bởi thành phần khác đến mức nào. Khi coupling cao, một thay đổi ở nơi này dễ buộc nơi khác thay đổi theo.

Trong hệ thống phân tầng, một số phụ thuộc là tự nhiên: controller gọi application use case; application sử dụng abstraction cần thiết; adapter triển khai các abstraction để kết nối database hoặc dịch vụ ngoài. Vấn đề xuất hiện khi phụ thuộc đi qua ranh giới không phù hợp hoặc nhiều module cùng biết chi tiết nội bộ của nhau.

Ví dụ, nếu controller tự tạo `OrderJpaEntity`, gọi `EntityManager` và cập nhật trạng thái, nó phụ thuộc vào cấu trúc persistence. Nếu schema đổi hoặc JPA được thay bằng JDBC, tầng trình bày cũng phải sửa.

Có thể đánh giá coupling qua câu hỏi:

- Một thay đổi nghiệp vụ có buộc sửa nhiều package không?
- Module có import các class triển khai cụ thể từ tầng khác không?
- Có vòng phụ thuộc giữa các package hoặc module không?
- Một thay đổi trong schema có làm thay đổi DTO API ngoài ý muốn không?
- Nhiều thành phần có phải biết thứ tự gọi và chi tiết của nhau không?
- Có một lớp trung tâm mà mọi chức năng đều phải sửa khi thêm quy tắc mới không?

Không nên coi mọi dependency là xấu. Một use case cần gọi repository là quan hệ hợp lý. Mục tiêu là làm phụ thuộc có chủ đích, hướng vào hợp đồng ổn định và giới hạn hiểu biết về chi tiết triển khai.

### Ví dụ: phụ thuộc vào chi tiết thay vì hợp đồng

Thiết kế gắn chặt:

```java
@RestController
@RequiredArgsConstructor
class OrderController {
    private final JpaOrderRepository jpaRepository;

    @PostMapping("/orders")
    OrderJpaEntity create(@RequestBody CreateOrderRequest request) {
        var entity = new OrderJpaEntity();
        entity.setStatus("NEW");
        entity.setCustomerId(request.customerId());
        return jpaRepository.save(entity);
    }
}
```

Controller biết entity và repository cụ thể. Nó còn tự đặt trạng thái, nên chính sách tạo đơn nằm ở tầng trình bày.

Thiết kế hướng vào hợp đồng use case:

```java
@RestController
@RequiredArgsConstructor
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    @PostMapping("/orders")
    OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        var result = placeOrder.handle(
            new PlaceOrderCommand(request.customerId(), request.items())
        );

        return new OrderResponse(result.orderId(), result.status());
    }
}
```

Controller chỉ phụ thuộc hợp đồng ứng dụng. Use case phối hợp nghiệp vụ và persistence qua các abstraction phù hợp. Nếu cách lưu trữ thay đổi, controller không cần biết.

Việc tạo interface không tự động làm coupling thấp. Nếu interface chỉ sao chép nguyên vẹn API của một class cụ thể hoặc mọi caller vẫn phụ thuộc vào chi tiết của adapter, ranh giới chưa có nhiều giá trị. Hãy đánh giá xem abstraction có biểu đạt nhu cầu của bên gọi và che được chi tiết mà bên gọi không cần biết hay không.

## 4. Độ kết dính: một module có tập trung vào một mục đích không?

Cohesion (độ kết dính) mô tả mức độ các phần tử trong một module cùng phục vụ một nhiệm vụ hoặc khái niệm liên quan. Module có cohesion tốt thường có trách nhiệm dễ diễn đạt bằng một câu và các thay đổi trong module có lý do tương đồng.

Ví dụ, `OrderPricingPolicy` chứa quy tắc tính giá, giảm giá và phí giao hàng có thể có cohesion tốt nếu các quy tắc này cùng phục vụ quyết định giá đơn hàng. Một lớp `OrderService` chứa xử lý HTTP, gửi email, tính giá, tạo PDF, truy vấn báo cáo và đồng bộ kho có cohesion thấp vì các chức năng thay đổi vì nhiều lý do khác nhau.

Dấu hiệu cohesion thấp:

- Tên module chung chung như `CommonService`, `Manager` hoặc `Utils` nhưng chứa nhiều nghiệp vụ không liên quan.
- Một thay đổi về phí giao hàng buộc sửa cùng lớp với thay đổi template email.
- Một class có nhiều dependency không cùng phục vụ một use case hoặc khái niệm.
- Phương thức trong cùng module thường dùng những nhóm dữ liệu hoàn toàn khác nhau.
- Người đọc không thể giải thích ngắn gọn module chịu trách nhiệm gì.

Dấu hiệu cohesion tốt:

- Các class cùng bảo vệ một nhóm quy tắc hoặc phục vụ một capability.
- Dữ liệu và hành vi thường thay đổi cùng nhau nằm gần nhau.
- Module có API công khai nhỏ, nội bộ được che giấu.
- Người sửa một chính sách có thể tìm được các test và thành phần liên quan.
- Module có thể được hiểu mà không cần đọc toàn bộ hệ thống.

### Cohesion không đồng nghĩa với gom tất cả vào một lớp

Một class nhỏ không nhất thiết có cohesion tốt, và một module có nhiều class vẫn có thể kết dính cao. Ví dụ, package `order.pricing` có thể chứa `PriceCalculator`, `DiscountPolicy`, `ShippingFeePolicy` và các value object liên quan. Chúng có nhiều class nhưng cùng phục vụ năng lực định giá.

Ngược lại, tạo một package cho mỗi class hoặc một service cho mỗi phương thức có thể chia nhỏ quá mức. Nếu các lớp luôn thay đổi cùng nhau, phụ thuộc qua lại chặt và không có lý do độc lập để tách, ranh giới có thể đang quá vụn.

## 5. Đánh giá bằng lý do thay đổi và khả năng cô lập

Một cách thực tế để đánh giá cohesion và coupling là xem lịch sử thay đổi hoặc mô phỏng các yêu cầu thường gặp:

- Thay đổi cách tính giá có thường đi cùng thay đổi giao diện không?
- Thay đổi schema có buộc sửa application service và controller không?
- Thêm kênh đầu vào mới (REST, message, batch) có cần sao chép quy tắc nghiệp vụ không?
- Thay đổi nhà cung cấp email có làm các lớp đơn hàng phải sửa không?
- Một module có thể được kiểm thử bằng hợp đồng của nó mà không cần dựng toàn bộ hệ thống không?

Có thể ghi lại các thay đổi trong một khoảng thời gian và lập bản đồ file/package thường cùng thay đổi. Nếu các thành phần thường xuyên thay đổi cùng nhau nhưng không cùng trách nhiệm, có thể có coupling ẩn. Nếu một quy tắc thường phải cập nhật ở nhiều nơi, có thể đang có duplication hoặc thiếu một chủ sở hữu rõ ràng.

Tuy nhiên, co-change không phải bằng chứng tuyệt đối. Một tính năng lớn có thể chạm nhiều module hợp lý; một module ổn định có thể ít thay đổi vì chưa có yêu cầu. Hãy kết hợp lịch sử Git với hiểu biết nghiệp vụ và phỏng vấn người thực hiện thay đổi.

## 6. Khả năng kiểm thử là phép thử của ranh giới kiến trúc

Một thiết kế có khả năng kiểm thử tốt cho phép kiểm tra quy tắc và use case với setup vừa đủ, kết quả rõ ràng và ít phụ thuộc vào hạ tầng không liên quan.

Ví dụ, quy tắc "đơn đã giao không được hủy" nên kiểm tra được bằng unit test cho mô hình `Order`, không cần khởi động Spring, kết nối database và gửi HTTP request. Ngược lại, mapping JPA và transaction cần integration test với database thực tế hoặc database kiểm thử tương thích.

Các câu hỏi đánh giá:

- Có thể tạo đối tượng nghiệp vụ hợp lệ mà không khởi động framework không?
- Có thể thay adapter bên ngoài bằng fake hoặc stub không?
- Test có kiểm tra kết quả thay vì xác minh quá nhiều lời gọi nội bộ không?
- Có thể kiểm tra lỗi và trạng thái sau lỗi không?
- Test có chạy nhanh, ổn định và không phụ thuộc thứ tự chạy không?
- Khi test thất bại, có xác định được tầng hoặc quy tắc gây lỗi không?

Nếu muốn kiểm tra một quy tắc nhỏ nhưng phải khởi động cả ứng dụng và database, đó có thể là dấu hiệu logic nghiệp vụ đang phụ thuộc quá nhiều vào framework hoặc persistence. Nhưng không phải mọi test đều cần cô lập tối đa: integration test là cần thiết để xác minh adapter, transaction, constraint và cấu hình thực tế.

### Chọn đúng loại test

| Loại test | Điều nên xác minh | Setup thường gặp |
|---|---|---|
| Domain unit test | Bất biến, phép tính, chuyển trạng thái | Java object thuần |
| Application test | Điều phối use case, kết quả và lỗi | Fake/mock các port |
| Adapter integration test | SQL, mapping, HTTP client, message adapter | Database hoặc dịch vụ kiểm thử |
| Controller test | HTTP contract, validation, response mapping | Spring MVC test |
| End-to-end test | Luồng quan trọng qua nhiều thành phần | Ứng dụng và hạ tầng kiểm thử |

Thiết kế tốt không nhằm loại bỏ mock hoặc integration test. Nó giúp mỗi test dùng đúng mức phụ thuộc cần thiết và kiểm tra đúng hợp đồng.

## 7. Ví dụ trước và sau: tách quy tắc giảm giá

Giả sử trước refactor, một lớp `OrderService` vừa lấy sản phẩm, vừa tính giảm giá, vừa cập nhật đơn và gửi email:

```java
@Service
@RequiredArgsConstructor
class OrderService {
    private final ProductJpaRepository products;
    private final OrderJpaRepository orders;
    private final JavaMailSender mailSender;

    @Transactional
    public OrderEntity place(CreateOrderRequest request) {
        var product = products.findById(request.productId()).orElseThrow();

        BigDecimal total = product.getPrice()
            .multiply(BigDecimal.valueOf(request.quantity()));

        if (request.customerType().equals("VIP")) {
            total = total.multiply(new BigDecimal("0.90"));
        }

        var order = new OrderEntity();
        order.setTotal(total);
        order.setStatus("NEW");
        order.setProduct(product);
        order.setQuantity(request.quantity());

        var saved = orders.save(order);
        mailSender.send(buildConfirmation(saved));
        return saved;
    }
}
```

Lớp này có nhiều lý do thay đổi: schema sản phẩm, chính sách VIP, quy trình tạo đơn, template email và cơ chế gửi email. Test có thể cần mock JPA repository và mail sender; nếu kiểm tra giảm giá, test phải dựng cả lớp với các dependency không liên quan.

Sau refactor, có thể đặt chính sách giảm giá ở một thành phần miền có trách nhiệm rõ:

```java
public interface DiscountPolicy {
    BigDecimal apply(BigDecimal subtotal, CustomerType customerType);
}

public final class StandardDiscountPolicy implements DiscountPolicy {
    @Override
    public BigDecimal apply(
            BigDecimal subtotal,
            CustomerType customerType) {
        if (customerType == CustomerType.VIP) {
            return subtotal.multiply(new BigDecimal("0.90"));
        }
        return subtotal;
    }
}
```

Application use case điều phối:

```java
@Service
@RequiredArgsConstructor
public class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductCatalog productCatalog;
    private final DiscountPolicy discountPolicy;
    private final OrderRepository orderRepository;
    private final OrderNotification notification;

    @Transactional
    public OrderResult handle(PlaceOrderCommand command) {
        var product = productCatalog.getSellableProduct(command.productId());

        var subtotal = product.price()
            .multiply(BigDecimal.valueOf(command.quantity()));

        var total = discountPolicy.apply(subtotal, command.customerType());

        var order = Order.place(
            command.customerId(),
            product.id(),
            command.quantity(),
            product.price(),
            total
        );

        var saved = orderRepository.save(order);
        notification.orderPlaced(saved.id());

        return new OrderResult(saved.id(), saved.status());
    }
}
```

Ví dụ chỉ minh họa hướng phân chia trách nhiệm; hệ thống thực tế cần xác định rõ tiền tệ, làm tròn, thời điểm chốt giá và cách phát thông báo sau commit. Nếu thông báo phải được gửi sau khi transaction thành công, có thể dùng transactional outbox hoặc cơ chế after-commit phù hợp.

Sau refactor, chính sách giảm giá có thể được test trực tiếp:

```java
@Test
void appliesVipDiscount() {
    var policy = new StandardDiscountPolicy();

    var total = policy.apply(
        new BigDecimal("100000"),
        CustomerType.VIP
    );

    assertThat(total).isEqualByComparingTo("90000.00");
}
```

Test use case kiểm tra tổng tiền được tính và đơn được lưu đúng. Test adapter kiểm tra repository lưu dữ liệu đúng. Không cần một test duy nhất verify tất cả lời gọi theo thứ tự để chứng minh chính sách giảm giá hoạt động.

### Kết quả thiết kế cần quan sát

| Tiêu chí | Trước | Sau |
|---|---|---|
| Trách nhiệm | Một service làm nhiều việc | Policy, use case và adapter có vai trò rõ |
| Thay đổi chính sách giảm giá | Sửa lớp điều phối lớn | Sửa policy và test liên quan |
| Thay nhà cung cấp email | Có thể ảnh hưởng service đặt hàng | Thay adapter thông báo |
| Test quy tắc giảm giá | Setup repository và mail sender | Test trực tiếp policy |
| Coupling | Service phụ thuộc JPA và mail framework | Use case phụ thuộc abstraction |
| Cohesion | Nhiều lý do thay đổi trong một class | Logic định giá tập trung hơn |

Refactor chỉ có giá trị nếu các ranh giới mới thật sự giảm hiểu biết không cần thiết và hỗ trợ thay đổi. Nếu `DiscountPolicy` chỉ là một lớp chuyển tiếp nhưng chính sách vẫn nằm trong `OrderService`, hoặc application service tiếp tục phụ thuộc trực tiếp JPA và mail sender, kết quả chưa đạt mục tiêu.

## 8. Đo lường trước và sau mà không chạy theo một con số

Có thể lập baseline trước refactor rồi so sánh sau khi hoàn tất. Baseline nên bao gồm các ví dụ thay đổi đại diện và các chỉ số liên quan:

| Chỉ số | Cách thu thập | Cách diễn giải |
|---|---|---|
| Lead time của thay đổi | Thời gian từ lúc nhận yêu cầu đến khi sẵn sàng phát hành | Giảm có thể cho thấy việc tìm hiểu và triển khai dễ hơn |
| Số module cùng phải sửa | Ghi lại package/module bị thay đổi cho từng yêu cầu | Ít lan truyền hơn có thể cho thấy ranh giới tốt hơn |
| Số nơi chứa cùng quy tắc | Tìm các bản triển khai trùng lặp và xác minh bằng review | Ít bản sao giúp giảm nguy cơ lệch chính sách |
| Thời gian chạy test liên quan | Đo thời gian unit, integration và end-to-end | Test nhanh hơn giúp phản hồi sớm, nhưng không được bỏ test cần thiết |
| Tỷ lệ test thất bại do thay đổi không liên quan | Phân loại nguyên nhân các test bị ảnh hưởng | Giảm có thể phản ánh test ít phụ thuộc cấu trúc |
| Lỗi hồi quy sau phát hành | Theo dõi lỗi theo loại thay đổi và phạm vi ảnh hưởng | Giảm cho thấy kiểm soát rủi ro tốt hơn nếu khối lượng thay đổi tương đương |
| Số dependency giữa module | Phân tích dependency graph hoặc công cụ kiến trúc | Dùng để tìm coupling bất thường, không phải mục tiêu tối ưu độc lập |

Không nên đặt KPI kiểu "mỗi thay đổi chỉ được sửa tối đa ba file" hoặc "coverage phải đạt 90% bằng mọi giá". Những mục tiêu đơn giản có thể dẫn đến chia module giả tạo, test yếu hoặc tránh sửa những nơi cần thiết. Chỉ số là tín hiệu để điều tra, không thay thế đánh giá kỹ thuật.

### So sánh các thay đổi tương đương

Để phép so sánh có ý nghĩa, hãy chọn một số yêu cầu tương tự trước và sau refactor, ví dụ:

- Thêm một quy tắc giảm giá.
- Thêm một trạng thái đơn hàng.
- Thay nhà cung cấp email.
- Thêm một kênh đầu vào mới cho use case.
- Thay cách truy vấn danh sách đơn hàng.

Ghi lại thời gian tìm hiểu, số thành phần thay đổi, loại test phải chạy và các lỗi phát sinh. Nếu chỉ so sánh một thay đổi nhỏ trước refactor với một tính năng lớn sau refactor, kết luận sẽ sai lệch.

## 9. Dùng test để bảo vệ hành vi trong suốt quá trình refactor

Đánh giá cấu trúc mới chỉ có ý nghĩa khi hành vi được bảo vệ. Trước khi di chuyển logic, cần hiểu những gì hệ thống đang làm, kể cả các hành vi chưa được tài liệu hóa.

Có thể dùng characterization test (test ghi nhận hành vi hiện tại) cho các luồng quan trọng. Test này mô tả kết quả hiện tại để phát hiện thay đổi ngoài ý muốn trong quá trình refactor. Sau khi xác nhận hành vi đúng theo yêu cầu, có thể bổ sung hoặc điều chỉnh test để thể hiện quy tắc mong muốn.

Một quy trình an toàn:

1. Chọn một luồng có rủi ro hoặc thay đổi thường xuyên.
2. Ghi lại input, output, trạng thái lưu và các tác động bên ngoài quan trọng.
3. Viết test bảo vệ hành vi quan sát được.
4. Tách một trách nhiệm nhỏ, giữ test chạy xanh.
5. Kiểm tra dependency và nơi sở hữu quy tắc sau khi di chuyển.
6. Lặp lại với thay đổi nhỏ, review được.
7. So sánh chi phí thay đổi và khả năng kiểm thử trên yêu cầu tiếp theo.

Không nên viết test để đóng băng mọi hành vi cũ. Hệ thống cũ có thể chứa bug hoặc hành vi không mong muốn. Khi phát hiện, cần phân biệt hành vi đang được client phụ thuộc với lỗi cần sửa, thống nhất thay đổi và cập nhật test theo yêu cầu mới.

## 10. Phân biệt cải thiện thiết kế với tăng độ phức tạp

Một refactor có thể trông "kiến trúc hơn" vì có thêm nhiều lớp:

- `OrderController` gọi `OrderFacade`.
- `OrderFacade` gọi `OrderManager`.
- `OrderManager` gọi `OrderCoordinator`.
- `OrderCoordinator` chỉ gọi `OrderService`.

Nếu các lớp này chỉ chuyển tiếp dữ liệu, không sở hữu quy tắc, không che giấu chi tiết và không tạo hợp đồng hữu ích, chi phí đọc mã tăng nhưng chi phí thay đổi không giảm.

Một số dấu hiệu overengineering:

- Mỗi thao tác CRUD có nhiều interface và implementation một-một không có lý do thay thế.
- Mapper được tạo chỉ để đổi tên một trường duy nhất và không có khả năng tái sử dụng.
- Một domain service chỉ gọi một repository mà không chứa quyết định nghiệp vụ.
- Package quá nhỏ khiến người đọc phải mở nhiều file để hiểu một hành động.
- Các lớp có dependency vòng hoặc phải biết cấu trúc nội bộ của nhau.
- Test cần dựng nhiều mock chỉ để chạy một phép tính đơn giản.

Tuy nhiên, không nên loại bỏ abstraction chỉ vì nó làm tăng số file. Một port cho cổng thanh toán có giá trị vì nó che giao thức và cho phép kiểm thử; một domain policy có giá trị khi nó gom quy tắc thay đổi độc lập; một repository interface có giá trị khi nó tách use case khỏi công nghệ lưu trữ. Đánh giá dựa trên vai trò thực tế của ranh giới.

## 11. Đánh giá theo nhiều chiều, không tối ưu cục bộ

Một module có thể có cohesion cao nhưng coupling với module khác cũng cao. Ví dụ, `OrderPricing` tập trung toàn bộ logic định giá nhưng mọi module khác phải truy cập field nội bộ hoặc gọi nhiều phương thức theo thứ tự riêng. Khi đó, cohesion bên trong tốt nhưng hợp đồng bên ngoài chưa tốt.

Một test có thể rất nhanh nhưng chỉ mock mọi collaborator và không kiểm tra persistence hoặc transaction. Khả năng kiểm thử unit tốt chưa chứng minh hệ thống tích hợp đúng.

Một thay đổi có thể sửa ít file nhưng làm tăng logic điều kiện trong một class lớn. Số file giảm không đồng nghĩa chi phí thay đổi giảm.

Vì vậy, đánh giá cần cân bằng:

- Cohesion tốt giúp trách nhiệm rõ.
- Coupling có kiểm soát giúp thay đổi ít lan truyền.
- Testability tốt giúp phát hiện lỗi sớm và refactor an toàn.
- Chi phí thay đổi thực tế cho thấy các đặc tính đó có mang lại lợi ích hay không.

Không có một kiến trúc phân tầng duy nhất phù hợp mọi ứng dụng. Có dự án chỉ cần controller, application service, domain model và persistence adapter ở mức đơn giản; có dự án cần thêm policy, module boundary hoặc read model chuyên biệt. DDD cũng không phải điều kiện bắt buộc. Chọn mức phân tách tương xứng với độ phức tạp nghiệp vụ, quy mô nhóm và tốc độ thay đổi.

## 12. Checklist review kết quả refactor

Khi review một đợt cải tiến, hãy hỏi:

1. Hành vi nghiệp vụ và hợp đồng API có được giữ nguyên hoặc thay đổi có chủ đích không?
2. Một yêu cầu thay đổi đi qua những module nào? Các module đó có thực sự cần thay đổi không?
3. Mỗi module có trách nhiệm đủ rõ để mô tả bằng một câu không?
4. Quy tắc nghiệp vụ có một nơi sở hữu rõ ràng hay vẫn bị lặp ở nhiều đường vào?
5. Các tầng có phụ thuộc vào abstraction phù hợp không, hay còn biết chi tiết triển khai không cần thiết?
6. Có dependency vòng hoặc các class trung tâm phải biết quá nhiều module không?
7. Có thể kiểm thử quy tắc miền mà không khởi động hạ tầng không?
8. Test use case có kiểm tra kết quả và trạng thái quan sát được không?
9. Các hành vi phụ thuộc database, transaction và dịch vụ ngoài có integration test phù hợp không?
10. Test có đủ ổn định để hỗ trợ refactor hay đang khóa vào chuỗi gọi nội bộ?
11. Thời gian và phạm vi thay đổi đại diện có cải thiện so với baseline không?
12. Số lớp, interface và abstraction mới có giải quyết một vấn đề cụ thể không?

Một đợt refactor thành công làm cho trách nhiệm dễ hiểu hơn, quy tắc có chủ sở hữu rõ hơn và các thay đổi tương lai ít gây tác động ngoài dự kiến. Hãy đánh giá bằng ví dụ thay đổi thật, dependency thực tế và khả năng kiểm thử, thay vì chỉ dựa vào số package, số class hoặc một tỷ lệ coverage. 

