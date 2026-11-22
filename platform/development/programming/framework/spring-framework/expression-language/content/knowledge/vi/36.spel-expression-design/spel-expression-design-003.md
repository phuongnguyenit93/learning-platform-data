# Tách logic nghiệp vụ lớn khỏi SpEL

## 1. Vai trò phù hợp của SpEL

Spring Expression Language (SpEL) là ngôn ngữ biểu thức dùng để đọc property, gọi method, tính toán và đánh giá điều kiện trên object tại runtime. SpEL hữu ích khi ứng dụng cần một quy tắc ngắn, có thể cấu hình hoặc cần tích hợp với một điểm mở rộng của Spring.

Tuy nhiên, SpEL không nên trở thành nơi chứa toàn bộ quy trình nghiệp vụ. Một expression dài có thể kết hợp nhiều điều kiện, truy cập object nhiều cấp, lọc collection, gọi method và xử lý null. Khi đó, người đọc khó hiểu mục đích, khó xác định lỗi nằm ở bước nào và khó kiểm thử từng quy tắc.

Một cách phân chia trách nhiệm thực tế:

- Java chứa quy tắc nghiệp vụ nhiều bước, phối hợp dữ liệu và xử lý lỗi.
- Domain object hoặc policy class cung cấp method có tên thể hiện quyết định nghiệp vụ.
- Service điều phối repository, API, transaction và các dependency.
- SpEL giữ các điều kiện ngắn, rõ ràng và thực sự cần được cấu hình hoặc đánh giá tại runtime.

Mục tiêu không phải loại bỏ SpEL. Mục tiêu là để mỗi công cụ làm phần việc mà nó diễn đạt rõ nhất.

## 2. Dấu hiệu logic đã quá lớn đối với một expression

Hãy cân nhắc chuyển logic sang Java khi expression có một hoặc nhiều dấu hiệu sau:

- Có nhiều cấp ngoặc, toán tử and/or và nhánh điều kiện lồng nhau.
- Kết hợp selection và projection trên nhiều collection lồng nhau.
- Truy cập một property path dài lặp lại nhiều lần.
- Phải xử lý nhiều trạng thái null ở các cấp object khác nhau.
- Một biểu thức vừa xác thực dữ liệu, vừa tính toán, vừa quyết định nghiệp vụ.
- Gọi nhiều method hoặc bean để phối hợp nhiều bước.
- Có truy vấn database, gọi API, ghi log nghiệp vụ hoặc thay đổi trạng thái.
- Cần xử lý exception, retry, transaction hoặc phân quyền.
- Chỉ có thể hiểu expression sau khi lần theo nhiều biến #this.
- Test cần dựng một object graph lớn và khó xác định assertion cho từng điều kiện.

Độ dài ký tự không phải tiêu chí duy nhất. Một expression ngắn vẫn có thể chứa một quyết định nghiệp vụ khó hiểu; ngược lại, một property path dài nhưng rõ ràng có thể vẫn phù hợp với SpEL.

Hãy hỏi: người đọc có thể giải thích expression bằng một câu nghiệp vụ đơn giản không? Nếu phải mô tả nhiều bước trung gian, nên đặt các bước đó vào method Java có tên.

## 3. Ví dụ một expression đang làm quá nhiều việc

Giả sử hệ thống cần xác định đơn hàng có thể chuyển sang kho để giao hay không. Quy tắc bao gồm trạng thái thanh toán, khách hàng còn hoạt động, địa chỉ hợp lệ, tổng tiền tối thiểu và có ít nhất một mặt hàng còn hàng.

Một expression lớn có thể trông như sau:

~~~text
status == T(com.example.OrderStatus).PAID
and customer != null
and customer.active
and customer.address != null
and customer.address.countryCode == #allowedCountry
and total != null
and total.compareTo(#minimumTotal) >= 0
and items != null
and items.?[product != null and product.active and quantity > 0 and product.stock >= quantity].size() > 0
~~~

Biểu thức trên trộn nhiều trách nhiệm:

1. Kiểm tra trạng thái đơn hàng.
2. Kiểm tra điều kiện của khách hàng và địa chỉ.
3. So sánh tổng tiền.
4. Duyệt từng mặt hàng.
5. Kiểm tra trạng thái sản phẩm và tồn kho.
6. Quyết định kết quả cuối cùng.

Khi test thất bại, chỉ biết kết quả là false chưa đủ để hiểu điều kiện nào không đạt. Khi quy tắc thay đổi, người sửa phải chỉnh một chuỗi biểu thức dài và dễ bỏ sót một nhánh.

Đây là dấu hiệu nên chuyển quyết định chính sang Java.

## 4. Tách quy tắc thành method có tên nghiệp vụ

Bắt đầu bằng cách đặt tên cho từng khái niệm. Ví dụ:

- isPaid: đơn hàng đã thanh toán.
- hasEligibleCustomer: khách hàng và địa chỉ đáp ứng yêu cầu.
- meetsMinimumTotal: tổng tiền đạt ngưỡng.
- hasAvailableItems: có ít nhất một mặt hàng đủ điều kiện giao.
- isEligibleForDispatch: kết hợp các điều kiện trên.

Một policy class có thể triển khai các method này:

~~~java
public class DispatchEligibilityPolicy {

    public boolean isEligibleForDispatch(
            Order order,
            DispatchPolicy policy) {

        return order != null
                && isPaid(order)
                && hasEligibleCustomer(order, policy)
                && meetsMinimumTotal(order, policy)
                && hasAvailableItems(order);
    }

    private boolean isPaid(Order order) {
        return order.getStatus() == OrderStatus.PAID;
    }

    private boolean hasEligibleCustomer(
            Order order,
            DispatchPolicy policy) {

        Customer customer = order.getCustomer();

        return customer != null
                && customer.isActive()
                && customer.getAddress() != null
                && policy.getAllowedCountry()
                        .equals(customer.getAddress().getCountryCode());
    }

    private boolean meetsMinimumTotal(
            Order order,
            DispatchPolicy policy) {

        BigDecimal total = order.getTotal();

        return total != null
                && total.compareTo(policy.getMinimumTotal()) >= 0;
    }

    private boolean hasAvailableItems(Order order) {
        if (order.getItems() == null) {
            return false;
        }

        return order.getItems().stream()
                .filter(Objects::nonNull)
                .anyMatch(this::isAvailableItem);
    }

    private boolean isAvailableItem(OrderItem item) {
        Product product = item.getProduct();

        return product != null
                && product.isActive()
                && item.getQuantity() > 0
                && product.getStock() >= item.getQuantity();
    }
}
~~~

Tên method cho biết từng điều kiện đang kiểm tra điều gì. Mỗi method có thể được kiểm thử riêng, đặt breakpoint và tái sử dụng.

Policy class nên chứa quyết định nghiệp vụ thuần khi có thể. Nếu một bước cần repository hoặc API, hãy cân nhắc đưa bước lấy dữ liệu vào service rồi truyền dữ liệu cần thiết cho policy.

## 5. Đưa việc phối hợp dependency vào service

Một service thường chịu trách nhiệm lấy dữ liệu, kiểm tra sự tồn tại, gọi policy và thực hiện hành động tiếp theo:

~~~java
@Service
public class DispatchService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;
    private final DispatchEligibilityPolicy eligibilityPolicy;
    private final DispatchPolicyProvider policyProvider;

    public DispatchService(
            OrderRepository orderRepository,
            InventoryService inventoryService,
            DispatchEligibilityPolicy eligibilityPolicy,
            DispatchPolicyProvider policyProvider) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
        this.eligibilityPolicy = eligibilityPolicy;
        this.policyProvider = policyProvider;
    }

    public DispatchDecision evaluate(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        InventorySnapshot inventory =
                inventoryService.loadSnapshot(order);

        DispatchPolicy policy = policyProvider.currentPolicy();

        return eligibilityPolicy.evaluate(order, inventory, policy);
    }
}
~~~

Service điều phối dependency và xử lý lỗi ở ranh giới ứng dụng. Policy diễn đạt quyết định nghiệp vụ. Cách chia này giúp test policy mà không cần database hoặc API thật, đồng thời test service riêng để xác nhận luồng phối hợp.

Không đưa truy vấn repository, HTTP request, gửi message hoặc transaction vào một expression SpEL dài. Các thao tác này cần dependency injection, exception handling và vòng đời rõ ràng của Java/Spring.

## 6. Dùng SpEL cho điều kiện cấu hình ngắn

Sau khi quyết định nghiệp vụ chính đã có tên, SpEL vẫn có thể hữu ích cho một điều kiện ngắn do cấu hình quyết định.

Ví dụ, ứng dụng có thể cho phép cấu hình thêm một ngưỡng hoặc một cờ vận hành:

~~~java
Expression expression = parser.parseExpression(
        "dispatchReady and #warehouseEnabled and total >= #minimumTotal");

StandardEvaluationContext context =
        new StandardEvaluationContext(orderView);

context.setVariable("warehouseEnabled", warehouseEnabled);
context.setVariable("minimumTotal", configuredMinimum);

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

Trong ví dụ này, dispatchReady là property hoặc getter đã được tính bằng Java. SpEL chỉ kết hợp một số điều kiện ngắn và có ý nghĩa rõ ràng.

Nếu điều kiện không cần cấu hình hoặc không cần đánh giá động, Java condition đơn giản có thể dễ đọc hơn. Không cần dùng SpEL chỉ vì một hệ thống đã có parser.

## 7. Dùng method có tên thay cho predicate dài

Một predicate phức tạp trong selection thường có thể trở thành method Java:

~~~java
List<OrderItem> eligibleItems = order.getItems().stream()
        .filter(this::isEligibleItem)
        .toList();
~~~

Method predicate:

~~~java
private boolean isEligibleItem(OrderItem item) {
    if (item == null || item.getProduct() == null) {
        return false;
    }

    Product product = item.getProduct();

    return product.isActive()
            && item.getQuantity() > 0
            && product.getStock() >= item.getQuantity();
}
~~~

So với selection nhiều điều kiện trong SpEL, method có thể được đọc như một câu nghiệp vụ. Có thể viết test cho từng trường hợp: item null, product null, sản phẩm ngừng hoạt động, số lượng không hợp lệ và tồn kho không đủ.

Java Stream vẫn phù hợp với thao tác collection ngắn. Nếu pipeline có nhiều bước, hãy tách thành method hoặc biến trung gian có tên.

## 8. Tách collection operation lồng nhau

Giả sử cần chọn các phòng ban có ít nhất hai nhân viên đang hoạt động, sau đó lấy tên các nhân viên đó. Expression lồng nhiều tầng sẽ khó theo dõi:

~~~text
departments.?[employees.?[active and salary > #minimumSalary].size() >= 2].![employees.?[active].![name]]
~~~

Có thể diễn đạt thành các bước Java:

~~~java
List<Department> eligibleDepartments = departments.stream()
        .filter(this::hasEnoughQualifiedEmployees)
        .toList();

List<List<String>> activeNames = eligibleDepartments.stream()
        .map(this::activeEmployeeNames)
        .toList();

private boolean hasEnoughQualifiedEmployees(Department department) {
    return department.getEmployees() != null
            && department.getEmployees().stream()
                    .filter(Objects::nonNull)
                    .filter(Employee::isActive)
                    .filter(employee -> employee.getSalary() > minimumSalary)
                    .count() >= 2;
}

private List<String> activeEmployeeNames(Department department) {
    return department.getEmployees().stream()
            .filter(Objects::nonNull)
            .filter(Employee::isActive)
            .map(Employee::getName)
            .toList();
}
~~~

Tên biến và method cho thấy mỗi bước tạo ra dữ liệu gì. Nếu một bước sai, có thể kiểm tra kết quả trung gian mà không phải giải mã toàn bộ expression.

Khi thao tác collection chỉ là một selection hoặc projection ngắn và có chủ đích cấu hình, SpEL vẫn phù hợp. Khi phải lồng nhiều cấp hoặc kết hợp quy tắc nghiệp vụ, Java thường rõ ràng hơn.

## 9. Dùng object kết quả để biểu diễn nhiều lý do

Một method Boolean chỉ trả về true hoặc false. Trong nhiều quy trình nghiệp vụ, người dùng hoặc hệ thống cần biết vì sao một đơn hàng không đủ điều kiện.

Thay vì nhồi nhiều nhánh vào SpEL, có thể trả về một object kết quả:

~~~java
public record EligibilityResult(
        boolean eligible,
        List<String> reasons) {

    public static EligibilityResult allowed() {
        return new EligibilityResult(true, List.of());
    }

    public static EligibilityResult rejected(String reason) {
        return new EligibilityResult(false, List.of(reason));
    }
}
~~~

Policy có thể thu thập lý do:

~~~java
public EligibilityResult evaluate(
        Order order,
        DispatchPolicy policy) {

    List<String> reasons = new ArrayList<>();

    if (order == null) {
        reasons.add("Order is missing");
        return new EligibilityResult(false, reasons);
    }

    if (order.getStatus() != OrderStatus.PAID) {
        reasons.add("Order is not paid");
    }

    if (order.getCustomer() == null
            || !order.getCustomer().isActive()) {
        reasons.add("Customer is not active");
    }

    if (order.getTotal() == null
            || order.getTotal().compareTo(policy.getMinimumTotal()) < 0) {
        reasons.add("Order total is below the minimum");
    }

    return new EligibilityResult(reasons.isEmpty(), reasons);
}
~~~

Kết quả có thể được log, hiển thị hoặc dùng trong luồng xử lý tiếp theo. Tách lý do khỏi biểu thức giúp tránh các chuỗi Boolean dài mà không giải thích được quyết định.

Mã lý do nên ổn định nếu được dùng bởi API hoặc hệ thống khác. Nội dung hiển thị cho người dùng có thể được dịch hoặc định dạng ở lớp trình bày.

## 10. Phân biệt validation với quyết định nghiệp vụ

Validation kiểm tra dữ liệu có hợp lệ về cấu trúc và ràng buộc đầu vào hay không. Quyết định nghiệp vụ xác định một hành động có được phép hoặc phù hợp trong trạng thái hiện tại hay không.

Ví dụ:

- Validation: quantity phải lớn hơn 0.
- Quyết định nghiệp vụ: kho có đủ hàng để đáp ứng quantity không.
- Validation: email có định dạng hợp lệ.
- Quyết định nghiệp vụ: khách hàng có được phép đặt hàng ở khu vực này không.

Không nên trộn mọi validation, tra cứu dữ liệu và quyết định nghiệp vụ vào một expression. Dùng Bean Validation hoặc validation logic phù hợp cho ràng buộc đầu vào; dùng policy/service cho quyết định cần nhiều dữ liệu hoặc trạng thái.

SpEL có thể hỗ trợ một điều kiện ngắn trong cấu hình, nhưng không thay thế một quy trình validation có lỗi theo field, message và nhóm kiểm tra rõ ràng.

## 11. Đưa dữ liệu động vào context thay vì nối chuỗi

Nếu một expression ngắn vẫn cần giá trị động, truyền dữ liệu qua root object hoặc variables:

~~~java
Expression expression = parser.parseExpression(
        "total >= #minimumTotal and region == #allowedRegion");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimumTotal", minimumTotal);
context.setVariable("allowedRegion", allowedRegion);

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

Không tạo expression source bằng cách nối trực tiếp dữ liệu request vào chuỗi. Dữ liệu có thể chứa dấu nháy hoặc ký tự làm thay đổi cú pháp.

Giữ source cố định giúp parse một lần, dễ kiểm thử và giảm nguy cơ dữ liệu đầu vào bị diễn giải như cú pháp SpEL. Nếu source expression đến từ cấu hình, hãy xác thực và kiểm soát ai có quyền sửa cấu hình đó.

## 12. Dùng helper method có kiểm soát

SpEL có thể gọi method trên root object hoặc object/bean được cung cấp qua context. Với một helper nhỏ, thuần và có tên rõ ràng, method call có thể giúp expression ngắn hơn.

Ví dụ root object expose một property tính toán:

~~~java
public boolean isDispatchReady() {
    return status == OrderStatus.PAID
            && customer != null
            && customer.isActive();
}
~~~

Expression sau chỉ còn:

~~~text
dispatchReady and #warehouseEnabled
~~~

Một số tích hợp Spring cũng cho phép bean reference như @policyBean.method(...), tùy BeanResolver và EvaluationContext được cấu hình. Không giả định cú pháp này có sẵn trong mọi context tự tạo.

Không dùng helper method để giấu một quy trình dài khác phía sau một tên ngắn. Method nên có contract rõ, dễ test và có hành vi dự đoán được. Tránh gọi method gây side effect từ expression, nhất là khi expression có thể được đánh giá nhiều lần.

## 13. Giữ expression thuần và tránh side effect

Expression có thể được đánh giá nhiều lần tùy module, vòng đời annotation, compiler mode hoặc cách ứng dụng gọi evaluator. Nếu expression gửi message, cập nhật database, tăng counter hoặc thay đổi trạng thái, việc đánh giá lặp lại có thể gây kết quả khó dự đoán.

Nên ưu tiên expression chỉ đọc dữ liệu và trả về kết quả:

~~~text
#order.total >= #minimumTotal
~~~

Không nên đặt thao tác thay đổi trạng thái vào expression:

~~~text
#order.confirmAndPublish()
~~~

Thay đổi trạng thái nên nằm trong Java service với transaction, idempotency, logging và exception handling rõ ràng. Expression chỉ nên quyết định hoặc tính kết quả nếu đó là vai trò được thiết kế.

Nếu một method được gọi từ SpEL, hãy kiểm tra nó có thuần hay không, có thể được gọi nhiều lần không và có cần quyền truy cập rộng không.

## 14. Xử lý null tại ranh giới phù hợp

Null handling phức tạp là một dấu hiệu nên tách logic. Thay vì viết nhiều toán tử null-safe trong cùng expression, có thể chuẩn hóa hoặc xác thực dữ liệu trong Java trước:

~~~java
Customer customer = order.getCustomer();

if (customer == null) {
    return EligibilityResult.rejected("Customer is missing");
}

Address address = customer.getAddress();

if (address == null) {
    return EligibilityResult.rejected("Customer address is missing");
}
~~~

Sau khi kiểm tra, các method nghiệp vụ tiếp theo có thể nhận dữ liệu đã được xác thực rõ ràng. Điều này giúp phân biệt object chưa có dữ liệu với collection rỗng hoặc giá trị mặc định.

Không chuẩn hóa null thành giá trị mặc định nếu hai trạng thái mang ý nghĩa nghiệp vụ khác nhau. Ví dụ, “chưa tải dữ liệu” và “đã tải nhưng không có kết quả” cần được giữ riêng nếu luồng xử lý phân biệt chúng.

## 15. Kiểm thử riêng policy Java và expression

Sau khi tách logic, mỗi phần có thể có test tập trung.

Test policy Java:

~~~java
@Test
void rejectsOrderWhenCustomerIsInactive() {
    Order order = TestData.paidOrder(
            new Customer("Lan", false),
            new BigDecimal("150.00"));

    EligibilityResult result =
            eligibilityPolicy.evaluate(order, testPolicy());

    assertFalse(result.eligible());
    assertTrue(result.reasons().contains("Customer is not active"));
}
~~~

Test expression ngắn:

~~~java
@Test
void evaluatesConfiguredThreshold() {
    OrderView order = new OrderView(150);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", 100);

    Expression expression = new SpelExpressionParser()
            .parseExpression("total >= #minimumTotal");

    assertTrue(expression.getValue(context, Boolean.class));
}
~~~

Test policy tập trung vào quy tắc nghiệp vụ và các lý do. Test SpEL tập trung vào cú pháp, root object, variables và kiểu kết quả. Không cần kiểm tra lại toàn bộ policy trong từng test expression nếu policy đã được test độc lập.

## 16. Kiểm thử service orchestration riêng

Nếu service gọi repository, API hoặc nhiều collaborator, dùng mock cho các dependency đó và xác nhận luồng phối hợp:

~~~java
@Test
void loadsOrderAndEvaluatesEligibility() {
    Order order = TestData.paidOrder();
    when(orderRepository.findById(10L))
            .thenReturn(Optional.of(order));

    when(policyProvider.currentPolicy())
            .thenReturn(testPolicy());

    DispatchDecision decision = dispatchService.evaluate(10L);

    assertNotNull(decision);
    verify(orderRepository).findById(10L);
    verify(policyProvider).currentPolicy();
}
~~~

Không cần mock các object dữ liệu đơn giản nếu có thể tạo fixture thật. Mock phù hợp cho repository, client và collaborator có hành vi bên ngoài.

Nếu service mở transaction hoặc cập nhật trạng thái, bổ sung integration test tại ranh giới đó. Unit test policy không chứng minh transaction hoặc persistence được cấu hình đúng.

## 17. Nếu expression đến từ cấu hình hoặc database

Một số ứng dụng lưu rule expression trong cấu hình để thay đổi điều kiện mà không cần build lại. Trường hợp này cần giữ expression ngắn, có contract đầu vào rõ và có bước kiểm tra khi nạp rule.

Quy trình gợi ý:

1. Định nghĩa tập property và variables được phép sử dụng.
2. Parse expression khi khởi động hoặc khi rule được cập nhật.
3. Kiểm tra cú pháp và kiểu kết quả mong đợi.
4. Evaluate trên fixture đại diện để phát hiện thiếu property hoặc variable.
5. Chỉ publish rule đã được kiểm tra.
6. Theo dõi lỗi evaluate và phiên bản rule trong log.
7. Giữ phiên bản trước đó để rollback khi rule mới không hoạt động.

Không cho phép người dùng không tin cậy tự do cung cấp SpEL source rồi đánh giá bằng StandardEvaluationContext có quyền rộng. Hãy giới hạn root object, property access, method resolver, bean resolver và type access theo nhu cầu thực tế.

Nếu rule cần truy cập database, gọi service hoặc thực hiện nhiều bước, lưu dữ liệu cấu hình có cấu trúc và xử lý bằng Java thường an toàn, dễ kiểm thử hơn một chuỗi expression tùy ý.

## 18. Tổ chức rule phức tạp bằng Strategy hoặc Specification

Khi có nhiều chính sách theo loại khách hàng, khu vực hoặc kênh bán hàng, không nên nối tất cả vào một expression có nhiều nhánh. Có thể dùng Strategy:

~~~java
public interface DispatchRule {
    boolean supports(Order order);
    EligibilityResult evaluate(Order order);
}
~~~

Mỗi implementation chịu trách nhiệm một nhóm quy tắc:

~~~java
@Component
public class DomesticDispatchRule implements DispatchRule {

    @Override
    public boolean supports(Order order) {
        return order.getCustomer() != null
                && "VN".equals(
                        order.getCustomer().getAddress().getCountryCode());
    }

    @Override
    public EligibilityResult evaluate(Order order) {
        // Quy tắc giao hàng nội địa.
        return evaluateDomesticOrder(order);
    }
}
~~~

Service chọn rule phù hợp:

~~~java
DispatchRule rule = rules.stream()
        .filter(candidate -> candidate.supports(order))
        .findFirst()
        .orElseThrow(() -> new UnsupportedDispatchRegionException());

EligibilityResult result = rule.evaluate(order);
~~~

Specification pattern cũng phù hợp khi các điều kiện nghiệp vụ cần được đặt tên, kết hợp và tái sử dụng. Hãy chọn cấu trúc đơn giản nhất đáp ứng số lượng rule và cách thay đổi của nghiệp vụ.

## 19. Theo dõi lỗi và khả năng quan sát

Một expression lớn thường chỉ cho biết evaluation thất bại ở một vị trí chung. Khi logic đã tách thành method, có thể ghi nhận kết quả từng bước với tên rõ ràng.

Ví dụ:

~~~java
boolean paid = policy.isPaid(order);
boolean customerEligible = policy.hasEligibleCustomer(order);
boolean totalEligible = policy.meetsMinimumTotal(order);

log.debug(
        "Dispatch checks: paid={}, customerEligible={}, totalEligible={}",
        paid,
        customerEligible,
        totalEligible);
~~~

Không ghi toàn bộ object hoặc dữ liệu cá nhân vào log chỉ để debug. Chỉ ghi mã định danh được phép, tên bước, trạng thái và correlation ID phù hợp.

Với expression được cấu hình động, log thêm mã rule hoặc phiên bản cấu hình để có thể xác định source nào đã được đánh giá. Tránh log secret hoặc dữ liệu đầu vào nhạy cảm.

## 20. Hiệu năng và tái sử dụng expression

Tách logic sang Java thường làm luồng xử lý dễ quan sát hơn, nhưng không nên coi đó là tối ưu hiệu năng tự động. Hãy đo trên workload thực tế.

Nếu một expression ngắn được dùng lặp lại, parse source một lần rồi tái sử dụng Expression:

~~~java
private final Expression eligibilityExpression =
        new SpelExpressionParser().parseExpression(
                "dispatchReady and #warehouseEnabled");
~~~

Mỗi lần evaluate, truyền context phù hợp với root object và variables của lần đó. Không chia sẻ một StandardEvaluationContext mutable giữa các request đồng thời nếu các request có thể ghi đè variables hoặc root object của nhau.

Nếu Java method thực hiện truy vấn lặp lại hoặc duyệt collection nhiều lần, hãy xem xét việc chuẩn bị dữ liệu một lần và truyền kết quả vào policy. Profiling giúp xác định chi phí thực tế nằm ở expression, data access hay logic nghiệp vụ.

## 21. Quy trình chuyển một expression lớn sang Java

Có thể thực hiện từng bước để giảm rủi ro thay đổi:

1. Ghi lại mục đích nghiệp vụ của expression hiện tại bằng một câu.
2. Chia expression thành các điều kiện và thao tác trung gian.
3. Đặt tên cho từng điều kiện bằng ngôn ngữ nghiệp vụ.
4. Xác định dữ liệu nào đến từ root object, variable, bean hoặc method.
5. Chuyển mỗi nhóm quy tắc sang method Java hoặc policy phù hợp.
6. Đưa repository/API orchestration sang service.
7. Giữ SpEL cho điều kiện cấu hình ngắn còn lại nếu có nhu cầu thật.
8. Viết unit test cho từng policy và test riêng cho expression.
9. Viết integration test cho luồng service và annotation nếu có.
10. So sánh kết quả mới với các case nghiệp vụ đại diện trước khi loại bỏ expression cũ.

Trong giai đoạn chuyển đổi, có thể chạy hai cách tính trên fixture hoặc dữ liệu test để đối chiếu kết quả. Không chạy đồng thời logic có side effect trên production chỉ để so sánh.

## 22. Khi nào vẫn nên giữ logic trong SpEL?

SpEL vẫn là lựa chọn tốt khi:

- Điều kiện ngắn và dễ đọc.
- Expression là một phần của cấu hình Spring như @Value, cache hoặc security.
- Rule cần thay đổi qua cấu hình được kiểm soát.
- Dữ liệu đầu vào và kiểu kết quả có contract rõ ràng.
- Không cần truy vấn dữ liệu, điều phối nhiều dependency hoặc side effect.
- Người bảo trì có thể hiểu expression mà không phải lần theo nhiều tầng helper.

Ví dụ:

~~~text
#request.total >= #minimumTotal and #request.active
~~~

Expression này kết hợp hai điều kiện rõ ràng trên dữ liệu đã được chuẩn bị. Nếu cần thêm nhiều bước kiểm tra, hãy chuyển phần đó sang Java.

## 23. Bảng quyết định: SpEL hay Java?

| Nhu cầu | Nơi phù hợp |
|---|---|
| Đọc property hoặc tính toán ngắn | SpEL |
| Điều kiện cấu hình đơn giản | SpEL |
| Selection/projection một cấp, predicate ngắn | SpEL hoặc Java Stream tùy điểm tích hợp |
| Nhiều collection lồng nhau | Java |
| Quy tắc nghiệp vụ nhiều điều kiện | Domain method hoặc policy |
| Truy vấn repository hoặc gọi API | Service Java |
| Transaction, retry và side effect | Service Java |
| Validation có lỗi theo field | Validator/DataBinder |
| Nhiều chiến lược theo loại nghiệp vụ | Strategy hoặc Specification |
| Rule động do quản trị viên cấu hình | SpEL giới hạn quyền, hoặc rule model có cấu trúc |
| Cần lý do chi tiết cho quyết định | Policy trả về result object |

Không có một ranh giới cứng cho mọi ứng dụng. Hãy ưu tiên cách biểu đạt mà nhóm có thể đọc, kiểm thử và thay đổi an toàn.

## 24. Lỗi thường gặp

**Giữ toàn bộ quy tắc trong một chuỗi expression**

Một expression dài làm khó tìm lỗi và khó đặt tên cho từng quyết định. Tách thành method hoặc policy.

**Chỉ đổi expression dài thành một method khổng lồ**

Đặt toàn bộ logic vào một method không tự động cải thiện khả năng bảo trì. Chia theo khái niệm nghiệp vụ và trách nhiệm có tên.

**Đưa repository hoặc API vào expression**

Expression không phải nơi điều phối dependency. Thực hiện data access trong service rồi truyền dữ liệu cần thiết vào policy.

**Dùng helper method để che logic không rõ ràng**

Tên method phải mô tả đúng hành vi. Tránh một helper ngắn nhưng bên trong có nhiều side effect hoặc nhiều bước khó đoán.

**Trộn validation với quyết định nghiệp vụ**

Ràng buộc đầu vào, kiểm tra trạng thái và quyết định hành động có mục đích khác nhau. Đặt chúng ở đúng lớp.

**Nối dữ liệu người dùng vào expression source**

Truyền dữ liệu qua root object hoặc variables. Giữ expression source cố định và được kiểm soát.

**Dùng context mutable chung cho nhiều request**

Root object và variables có thể thay đổi. Tạo context phù hợp cho từng lần đánh giá.

**Không test các lý do thất bại riêng**

Test chỉ kiểm tra Boolean cuối cùng có thể bỏ qua nguyên nhân. Với quy tắc quan trọng, trả về result object có lý do và test từng nhánh.

## 25. Ghi nhớ

- Dùng SpEL cho biểu thức ngắn, rõ và có nhu cầu đánh giá/cấu hình động.
- Chuyển logic nhiều bước, nhiều nhánh hoặc collection lồng nhau sang Java.
- Đặt tên method theo quyết định nghiệp vụ như isEligibleForDispatch hoặc hasAvailableItems.
- Dùng policy/domain method cho quyết định thuần; dùng service cho repository, API, transaction và orchestration.
- Trả về result object khi cần giải thích vì sao một quyết định được chấp nhận hoặc từ chối.
- Tách validation dữ liệu đầu vào khỏi quyết định nghiệp vụ.
- Truyền dữ liệu động qua root object hoặc variables, không nối dữ liệu vào expression source.
- Giữ expression thuần và tránh side effect vì expression có thể được đánh giá nhiều lần.
- Test policy, expression và service orchestration ở các tầng riêng.
- Dùng Strategy hoặc Specification khi có nhiều rule cần đặt tên và tái sử dụng.
- Chỉ giữ SpEL khi nó làm quy tắc dễ cấu hình và dễ hiểu hơn Java.
