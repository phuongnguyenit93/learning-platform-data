# Root object với property và method resolution

Trong Spring Expression Language (SpEL), biểu thức thường được đánh giá trong một EvaluationContext. Context cung cấp object gốc (root object), biến, property accessor, method resolver, type locator và các dịch vụ cần thiết để diễn giải biểu thức.

Root object là đối tượng mặc định mà biểu thức truy cập khi không ghi rõ tên biến. Ví dụ, nếu root object là một Order, biểu thức **status** có thể đọc property status của Order và **calculateTotal()** có thể gọi method tương ứng trên Order.

SpEL phân biệt **#root** và **#this**. **#root** luôn tham chiếu root object của lần đánh giá; **#this** là object hiện tại tại vị trí đang được đánh giá và có thể thay đổi trong các thao tác như selection hoặc projection. Hiểu đúng hai biến này giúp viết biểu thức rõ ràng, đặc biệt khi có nhiều object lồng nhau.

## 1. Root object là gì?

### 1.1. Đối tượng mặc định của biểu thức

Root object là đối tượng mà SpEL dùng làm điểm bắt đầu khi phân giải property hoặc method không có receiver được viết tường minh.

Ví dụ lớp Order:

~~~java
public class Order {

    private final String id;
    private final String status;
    private final BigDecimal total;

    public Order(String id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public boolean isPaid() {
        return "PAID".equals(status);
    }

    public BigDecimal calculateTotal() {
        return total;
    }
}
~~~

Tạo parser và context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        "O-100",
        "PAID",
        new BigDecimal("125.50")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Đánh giá property và method trên root object:

~~~java
String id = parser
        .parseExpression("id")
        .getValue(context, String.class);

Boolean paid = parser
        .parseExpression("isPaid()")
        .getValue(context, Boolean.class);
~~~

Ở đây, **id** và **isPaid()** được phân giải trên Order vì Order là root object của context.

### 1.2. Đặt root object sau khi tạo context

Có thể tạo context trước rồi thiết lập root object:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(order);
~~~

Hoặc tạo context với root object ngay từ đầu:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Cả hai cách đều đặt Order làm root object. Nếu context được dùng lại, hãy chú ý việc thay root object giữa các lần đánh giá để không vô tình đánh giá biểu thức trên dữ liệu của request khác.

### 1.3. Root object có thể là DTO hoặc view object

Không bắt buộc root object phải là entity hoặc service. Có thể dùng một DTO nhỏ chỉ chứa dữ liệu mà biểu thức cần:

~~~java
public record OrderExpressionView(
        String status,
        BigDecimal total,
        boolean customerActive
) {
}
~~~

Tạo context:

~~~java
OrderExpressionView view =
        new OrderExpressionView("PAID", new BigDecimal("125.50"), true);

StandardEvaluationContext context =
        new StandardEvaluationContext(view);
~~~

Biểu thức:

~~~java
status == 'PAID' && customerActive && total > 100
~~~

Một root object gọn giúp biểu thức dễ hiểu và hạn chế việc vô tình truy cập những phần khác của domain model.

## 2. #root và #this

### 2.1. #root tham chiếu root object

Biến đặc biệt **#root** luôn tham chiếu object gốc được cung cấp cho EvaluationContext:

~~~java
#root.status
#root.total
#root.isPaid()
~~~

Khi biểu thức được đánh giá trực tiếp trên root object Order, **status** và **#root.status** thường cho cùng kết quả.

Viết tường minh **#root** hữu ích khi biểu thức có nhiều cấp truy cập hoặc khi context đang đánh giá một object hiện tại khác root object.

### 2.2. #this là object hiện tại

Biến **#this** đại diện cho object hiện tại tại vị trí đánh giá. Ở cấp ngoài cùng, nó thường là root object. Trong các thao tác như selection và projection, **#this** thay đổi theo phần tử đang được xử lý.

Ví dụ:

~~~java
#this.status
~~~

Ở ngoài selection, nếu root object là Order, biểu thức đọc status của Order.

Trong selection:

~~~java
orders.?[#this.total > 100]
~~~

Ở đây, **#this** là từng order đang được xét, còn **#root** vẫn là object gốc chứa property orders.

### 2.3. So sánh #root và #this trong collection

Giả sử root object là Report:

~~~java
public class Report {

    private final String currentCustomerId;
    private final List<Order> orders;

    public Report(String currentCustomerId, List<Order> orders) {
        this.currentCustomerId = currentCustomerId;
        this.orders = orders;
    }

    public String getCurrentCustomerId() {
        return currentCustomerId;
    }

    public List<Order> getOrders() {
        return orders;
    }
}
~~~

Biểu thức:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
]
~~~

Trong predicate:

- **#this** là Order hiện tại trong danh sách.
- **#root** là Report.
- **#this.customerId** đọc mã khách hàng của order.
- **#root.currentCustomerId** đọc mã khách hàng hiện tại từ report.

Không nên thay **#root** bằng **#this** trong ví dụ này, vì khi selection chạy, #this đã chuyển sang phần tử Order.

### 2.4. #this thay đổi trong projection

Projection dùng toán tử **.![]** để biến đổi từng phần tử. Trong projection, #this là phần tử hiện tại:

~~~java
orders.![#this.id]
~~~

Kết quả là danh sách id của các order.

Có thể dùng root object trong phép biến đổi:

~~~java
orders.![#this.total + #root.adjustment]
~~~

Ví dụ này tính một giá trị cho mỗi order dựa trên total của phần tử hiện tại và adjustment của root object.

Khi lồng selection/projection, hãy xác định object hiện tại ở đúng vị trí của predicate hoặc projection thay vì giả định #this luôn là root object.

## 3. Truy cập property trên root object

### 3.1. Property notation

SpEL cho phép truy cập property bằng tên property:

~~~java
status
total
customer.name
~~~

Trong Java bean thông thường, property notation thường được phân giải qua getter tương ứng, chẳng hạn **getStatus()**, **getTotal()** hoặc **isActive()**. Tùy PropertyAccessor được cấu hình, SpEL cũng có thể truy cập các cấu trúc dữ liệu khác.

Property notation **status** khác với lời gọi method tường minh **getStatus()**:

- **status** yêu cầu truy cập property status.
- **getStatus()** yêu cầu gọi method có tên getStatus.

Nên dùng property notation khi muốn diễn đạt dữ liệu, và method call khi muốn thực hiện một hành vi có tên rõ ràng.

### 3.2. Truy cập property lồng nhau

Có thể nối nhiều property bằng dấu chấm:

~~~java
customer.address.city
~~~

Mỗi bước được phân giải trên object nhận được từ bước trước. Nếu customer hoặc address là null, truy cập tiếp theo có thể gây lỗi evaluate.

Có thể kiểm tra null bằng điều kiện ngắn mạch:

~~~java
customer != null
    && customer.address != null
    && customer.address.city == 'Hanoi'
~~~

Hoặc dùng safe navigation ở những vị trí cần thiết nếu phiên bản Spring đang dùng hỗ trợ:

~~~java
customer?.address?.city
~~~

Safe navigation xử lý receiver null tại vị trí đặt toán tử. Nó không biến property không tồn tại thành null và cũng không bắt mọi exception.

### 3.3. Property trên Map và collection

Với Map, có thể truy cập value bằng key:

~~~java
settings['theme']
settings['timeout']
~~~

Cú pháp indexer thường rõ ràng hơn khi key là chuỗi hoặc chứa ký tự không phù hợp với property notation.

Với List hoặc array, dùng chỉ số:

~~~java
items[0]
scores[2]
~~~

Chỉ số bắt đầu từ 0. Nếu index ngoài phạm vi, evaluation có thể thất bại.

### 3.4. Property chỉ đọc và property có thể ghi

Khi expression chỉ đọc, SpEL cần một PropertyAccessor có thể đọc property. Nếu dùng **setValue**, accessor còn phải hỗ trợ ghi và property phải có khả năng thay đổi:

~~~java
parser.parseExpression("status")
        .setValue(context, "SHIPPED");
~~~

Ví dụ này chỉ thành công nếu root object có property status có thể ghi theo accessor đang dùng. Một record hoặc object bất biến thường không có setter để thực hiện cập nhật.

Không nên giả định mọi property đọc được đều có thể ghi. Hãy kiểm tra hợp đồng của object và PropertyAccessor.

## 4. PropertyAccessor và cơ chế phân giải property

### 4.1. PropertyAccessor làm nhiệm vụ gì?

PropertyAccessor là extension point cho phép SpEL đọc hoặc ghi property của object. Một accessor có thể hỗ trợ một hay nhiều loại target object.

StandardEvaluationContext mặc định có accessor phản chiếu cho Java object. Nó thường đọc JavaBean property qua getter và hỗ trợ truy cập field theo quy tắc của Spring.

Khi biểu thức đọc:

~~~java
customer.name
~~~

SpEL tìm PropertyAccessor có thể xử lý object customer và property name. Nếu accessor đọc được, nó trả về giá trị property cho phần còn lại của biểu thức.

### 4.2. Thêm PropertyAccessor tùy chỉnh

Ứng dụng có thể thêm accessor cho một kiểu dữ liệu đặc biệt:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.addPropertyAccessor(new CustomPropertyAccessor());
~~~

CustomPropertyAccessor cần triển khai các phương thức của PropertyAccessor, bao gồm xác định target class được hỗ trợ, kiểm tra khả năng đọc/ghi và thực hiện thao tác tương ứng.

Chỉ thêm accessor khi có một mô hình dữ liệu cụ thể cần hỗ trợ. Một accessor quá tổng quát có thể làm thay đổi cách phân giải property của nhiều loại object và khiến biểu thức khó dự đoán.

### 4.3. Thứ tự và phạm vi accessor

Khi có nhiều accessor, khả năng hỗ trợ target và thứ tự được đăng ký có thể ảnh hưởng accessor nào được dùng. Nếu accessor tùy chỉnh xử lý một kiểu object, hãy giới hạn **getSpecificTargetClasses()** phù hợp thay vì tuyên bố hỗ trợ mọi object.

Nếu accessor đọc property nhưng không ghi, hãy trả lời chính xác cho **canRead** và **canWrite**. Không khai báo có thể ghi rồi ném lỗi ở bước write nếu kiểu dữ liệu vốn bất biến.

## 5. Method resolution trên root object

### 5.1. Gọi method trực tiếp

Method trên root object có thể được gọi bằng tên và danh sách argument:

~~~java
calculateTotal()
isPaid()
hasItem('P-100')
~~~

Ví dụ:

~~~java
BigDecimal total = parser
        .parseExpression("calculateTotal()")
        .getValue(context, BigDecimal.class);
~~~

SpEL tìm method trên target object bằng MethodResolver. Với StandardEvaluationContext, resolver mặc định sử dụng reflection để tìm method phù hợp.

### 5.2. Method có argument

Argument có thể là literal, property, biến hoặc biểu thức khác:

~~~java
hasItem('P-100')
hasItem(#productCode)
calculateDiscount(total, #customerTier)
~~~

Các argument được đánh giá trước khi method được gọi. Nếu kiểu argument không khớp chữ ký method, TypeConverter có thể được dùng để chuyển đổi khi cấu hình hỗ trợ.

Method không tồn tại, không truy cập được hoặc không có overload phù hợp sẽ gây lỗi khi evaluate, dù biểu thức có thể parse thành công.

### 5.3. Phân biệt property và method

So sánh:

~~~java
active
isActive()
~~~

**active** là truy cập property. Trong Java bean, nó thường được đọc thông qua getter **isActive()**.

**isActive()** là lời gọi method tường minh. Hai cách có thể cùng lấy một thông tin nhưng semantics ở mức SpEL khác nhau.

Khi viết biểu thức, ưu tiên property notation cho dữ liệu trạng thái. Dùng method call cho hành vi hoặc phép tính có tên phù hợp.

### 5.4. Overload và chuyển đổi argument

Một class có thể có nhiều method cùng tên:

~~~java
public String format(String value) {
    return "text:" + value;
}

public String format(Long value) {
    return "number:" + value;
}
~~~

SpEL phải phân giải method phù hợp dựa trên tên, số lượng argument và khả năng tương thích kiểu. Nếu nhiều overload cùng có thể nhận đối số sau chuyển đổi, lựa chọn có thể phụ thuộc resolver và TypeConverter.

Để tránh mơ hồ:

- Giữ số lượng overload vừa phải.
- Dùng tên method riêng cho hành vi khác nhau.
- Truyền dữ liệu có kiểu rõ ràng khi cần chọn overload cụ thể.
- Kiểm thử biểu thức với cấu hình Spring thực tế.
- Không dựa vào thứ tự khai báo method trong source để suy luận overload được chọn.

## 6. MethodResolver và MethodExecutor

### 6.1. MethodResolver

MethodResolver tìm method phù hợp với tên method và argument list trên target object. Interface nhận EvaluationContext, target object, tên method và kiểu các argument, rồi trả về một MethodExecutor phù hợp.

StandardEvaluationContext mặc định sử dụng ReflectiveMethodResolver. Ứng dụng có thể thêm MethodResolver riêng khi cần một chính sách gọi method khác.

### 6.2. MethodExecutor

Sau khi resolver tìm được method phù hợp, MethodExecutor thực thi lời gọi với target và argument đã được chuẩn bị.

Tách hai bước giúp phân biệt:

- Không tìm được method phù hợp: vấn đề ở phân giải.
- Đã tìm được method nhưng lời gọi thất bại: vấn đề có thể ở chuyển đổi argument, quyền truy cập hoặc logic bên trong method.

### 6.3. Đăng ký resolver tùy chỉnh

Có thể thêm resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.addMethodResolver(new CustomMethodResolver());
~~~

Resolver tùy chỉnh nên giới hạn rõ target class, tên method và chữ ký được phép. Không tạo một resolver cho phép gọi mọi method chỉ để xử lý một trường hợp đặc biệt.

Nếu chỉ cần cung cấp một vài hành vi cho expression, thường dễ kiểm soát hơn khi tạo facade có method public rõ ràng và đặt facade vào context dưới dạng biến.

## 7. Root object, biến và bean reference

Ba cách truy cập object thường gặp có mục đích khác nhau:

| Cách truy cập | Cú pháp | Nguồn object |
|---|---|---|
| Root object | **status**, **#root.status** | Object gốc của EvaluationContext |
| Biến context | **#order.status** | Biến được đăng ký bằng setVariable |
| Bean reference | **@pricingService.quote(...)** | BeanResolver của EvaluationContext |

Đăng ký biến:

~~~java
context.setVariable("order", order);
~~~

Truy cập biến:

~~~java
#order.status
~~~

Bean reference chỉ hoạt động khi context có BeanResolver phù hợp:

~~~java
@pricingService.quote('P-100')
~~~

Không nhầm biến context với bean reference. Biến được gán trực tiếp vào context; bean reference cần resolver để tìm bean theo tên.

Khi expression không tin cậy, không cấp bean resolver rộng hoặc root object chứa quá nhiều quyền. Chỉ cung cấp object và method thực sự cần thiết.

## 8. Ví dụ kết hợp root, biến và method

Giả sử root object là Order, còn context có biến customerTier:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("customerTier", "GOLD");
context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Biểu thức:

~~~java
#root.status == 'PAID'
    && total >= #minimumTotal
    && supportsTier(#customerTier)
~~~

Trong đó:

- **#root.status** truy cập property trên root object.
- **total** cũng truy cập property của root object.
- **#minimumTotal** và **#customerTier** là biến context.
- **supportsTier(...)** gọi method trên root object.

Cách viết này tách dữ liệu thuộc Order khỏi tham số bên ngoài được cung cấp qua context.

Nếu biểu thức dài hơn, hãy chia nhóm bằng dấu ngoặc hoặc chuyển một quy tắc có tên sang method riêng để người đọc dễ hiểu.

## 9. Xử lý null và lỗi resolution

### 9.1. Root object null

Một số biểu thức chỉ dùng literal hoặc biến có thể không cần root object. Nhưng nếu biểu thức truy cập property hoặc method trên root object null, evaluation có thể thất bại.

Hãy xác thực root object trước khi đánh giá:

~~~java
if (order == null) {
    throw new IllegalArgumentException("Order is required");
}

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
~~~

Không dùng một root object giả hoặc giá trị mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

### 9.2. Property không tồn tại

Nếu biểu thức tham chiếu property không được accessor hỗ trợ, SpEL có thể ném lỗi evaluate. Kiểm tra tên property, getter, target class và accessor được đăng ký.

Lỗi property không tồn tại khác với property tồn tại nhưng giá trị null. Safe navigation chỉ xử lý receiver null; nó không sửa tên property sai.

### 9.3. Method không tồn tại hoặc không phù hợp

Nếu không có method phù hợp, kiểm tra:

- Tên method và chữ hoa/chữ thường.
- Số lượng argument.
- Kiểu argument thực tế.
- Overload hiện có.
- Khả năng chuyển đổi của TypeConverter.
- MethodResolver đang cấu hình.
- Quyền truy cập method trong runtime.

Không nên bắt mọi lỗi resolution rồi trả về null. Điều đó có thể che giấu lỗi cấu hình hoặc lỗi lập trình.

### 9.4. Phân biệt parse và evaluate

Parse kiểm tra cú pháp và tạo Expression. Property resolution và method invocation thường diễn ra khi evaluate.

Vì vậy:

- Biểu thức sai cú pháp phát sinh ParseException.
- Property không truy cập được hoặc method không phù hợp thường phát sinh EvaluationException hoặc subtype cụ thể.
- Method có thể được tìm thấy nhưng ném exception trong lúc thực thi.
- Chuyển đổi argument có thể thất bại khi lời gọi được đánh giá.

Hãy bắt và phân loại exception ở đúng ranh giới, giữ nguyên cause để phục vụ điều tra.

## 10. Thiết kế context an toàn và dễ kiểm soát

### 10.1. Chỉ cung cấp object cần thiết

Root object có thể mở ra toàn bộ object graph. Nếu expression chỉ cần status và total, không cần truyền một service hoặc entity lớn có nhiều quan hệ.

Dùng DTO/view nhỏ giúp giới hạn property mà expression có thể đọc và giảm nguy cơ gọi nhầm method.

### 10.2. Cân nhắc SimpleEvaluationContext

Nếu chỉ cần đọc property và không cần đầy đủ tính năng SpEL, có thể dùng SimpleEvaluationContext với cấu hình phù hợp:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

SimpleEvaluationContext giới hạn một số khả năng so với StandardEvaluationContext, chẳng hạn type reference, constructor và bean reference. Method invocation cũng cần được bật có chủ đích theo cấu hình builder nếu ứng dụng thực sự cần.

Context giới hạn không thay thế việc kiểm tra dữ liệu, giới hạn tài nguyên hoặc authorization ở tầng service.

### 10.3. Không chia sẻ context có trạng thái giữa request

EvaluationContext có root object, biến và cấu hình accessor/resolver. Nếu thay đổi biến hoặc root object giữa các request, dữ liệu có thể bị dùng nhầm nếu context được chia sẻ không đúng cách.

Nên tạo context theo request hoặc lần đánh giá, hoặc dùng một cấu hình bất biến đã được thiết kế để chia sẻ an toàn. Không lưu dữ liệu người dùng trong biến của context dùng chung.

## 11. Kiểm thử root object và resolution

Nên kiểm thử riêng root property, method call, biến, #root và #this:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        "O-100",
        "PAID",
        new BigDecimal("125.50")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

assertEquals(
        "O-100",
        parser.parseExpression("id")
                .getValue(context, String.class)
);

assertEquals(
        "O-100",
        parser.parseExpression("#root.id")
                .getValue(context, String.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("isPaid()")
                .getValue(context, Boolean.class)
);
~~~

Kiểm thử biến:

~~~java
context.setVariable("minimum", new BigDecimal("100"));

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("total >= #minimum")
                .getValue(context, Boolean.class)
);
~~~

Với selection, kiểm thử rằng #this là phần tử hiện tại còn #root vẫn là object gốc:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
]
~~~

Ngoài ra, nên kiểm thử root null, property null, property không tồn tại, method không tồn tại, overload và converter thất bại. Những trường hợp này xác nhận resolution ở giai đoạn evaluate.

## 12. Tổng kết

Root object là điểm bắt đầu mặc định của một biểu thức SpEL. PropertyAccessor đọc hoặc ghi property; MethodResolver tìm method phù hợp; MethodExecutor thực thi lời gọi; TypeConverter hỗ trợ chuyển đổi argument khi cần.

- **#root** luôn tham chiếu object gốc của EvaluationContext.
- **#this** tham chiếu object hiện tại và có thể thay đổi trong selection/projection.
- Property notation như **status** dùng để đọc dữ liệu; method call như **calculateTotal()** gọi hành vi.
- PropertyAccessor và MethodResolver là các extension point để tùy chỉnh cách truy cập.
- Biến context dùng cú pháp **#name**; bean reference dùng **@beanName** và cần BeanResolver.
- Parse thành công không bảo đảm property hoặc method sẽ được phân giải thành công khi evaluate.

Hãy cung cấp root object nhỏ, có hợp đồng rõ ràng, giới hạn accessor/resolver theo nhu cầu và tạo context theo phạm vi sử dụng. Cách đó giúp biểu thức dễ đọc, dễ kiểm thử và giảm quyền truy cập ngoài dự kiến.