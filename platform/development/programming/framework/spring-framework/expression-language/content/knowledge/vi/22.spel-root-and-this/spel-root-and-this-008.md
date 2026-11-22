# Thiết kế root object nhỏ theo mục tiêu biểu thức trong Spring Expression Language

Trong Spring Expression Language (SpEL), root object là đối tượng mặc định mà biểu thức đọc property và gọi method khi tên được viết mà không có tiền tố biến. Vì vậy, object được chọn làm root quyết định phần dữ liệu và hành vi mà expression có thể nhìn thấy ngay từ đầu.

Khi thiết kế ứng dụng dùng SpEL, nên tạo một root object có phạm vi vừa đủ cho mục tiêu của biểu thức. Nếu expression chỉ cần lọc đơn hàng theo tổng tiền và trạng thái, root object nên cung cấp danh sách đơn hàng cùng ngưỡng cần so sánh. Không cần đưa toàn bộ ApplicationContext, repository, entity graph hoặc các dịch vụ không liên quan vào môi trường đánh giá.

Một root object nhỏ giúp biểu thức dễ đọc, dữ liệu đầu vào rõ ràng, giảm phụ thuộc vào cấu trúc nội bộ của ứng dụng và giới hạn những property hoặc method mà expression có thể truy cập.

## 1. Root object là điểm bắt đầu của expression

Khi tạo StandardEvaluationContext với một object, object đó trở thành root object:

~~~java
Order order = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

Với context này, expression có thể đọc property trực tiếp:

~~~spel
total
status
orderNumber
~~~

Tên property không có tiền tố # được tra cứu trên object hiện tại. Ở cấp ngoài cùng, object hiện tại ban đầu chính là root object.

Có thể tham chiếu tường minh root object bằng #root:

~~~spel
#root.total
#root.status
~~~

Vì vậy, nếu root object là Order, hai cách viết total và #root.total đều chỉ property total của root object trong ngữ cảnh đơn giản này.

## 2. Root object khác với biến trong EvaluationContext

Root object là object chính của lần đánh giá. Biến là dữ liệu bổ sung được đăng ký riêng trong EvaluationContext.

Ví dụ:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Expression:

~~~spel
total >= #minimum
~~~

đọc total từ root object và minimum từ biến trong context.

Có thể dùng #root để làm rõ nguồn dữ liệu:

~~~spel
#root.total >= #minimum
~~~

Cách phân chia này hữu ích khi thiết kế input cho expression:

- Root object chứa dữ liệu chính mà biểu thức thao tác.
- Variables chứa giá trị phụ trợ, tham số hoặc ngưỡng được cung cấp riêng.
- Không cần biến mọi property thành variable nếu chúng đã thuộc object chính.

Nếu expression có nhiều giá trị liên quan chặt chẽ và luôn được truyền cùng nhau, có thể gom chúng vào một root object chuyên biệt thay vì đăng ký quá nhiều biến rời rạc.

## 3. Vì sao nên thiết kế root object nhỏ?

Một root object lớn có thể khiến expression phụ thuộc vào nhiều phần của mô hình ứng dụng. Khi entity hoặc service thay đổi, expression cũng có thể phải thay đổi theo.

Một root object nhỏ mang lại các lợi ích:

1. **Làm rõ đầu vào:** nhìn vào lớp root có thể biết expression được phép sử dụng dữ liệu nào.
2. **Giảm phụ thuộc:** biểu thức không cần biết toàn bộ cấu trúc domain hoặc service layer.
3. **Dễ kiểm thử:** có thể tạo object đầu vào nhỏ với dữ liệu xác định cho từng trường hợp.
4. **Giảm tác dụng phụ ngoài ý muốn:** expression ít có cơ hội truy cập các method cập nhật trạng thái hoặc gọi những thành phần không liên quan.
5. **Ổn định hợp đồng:** thay đổi nội bộ của entity không nhất thiết làm thay đổi lớp input dành cho SpEL.
6. **Dễ tái sử dụng:** cùng một kiểu input có thể phục vụ nhiều expression có mục tiêu tương tự.

Mục tiêu không phải là tạo một lớp cho mọi expression. Hãy gom các dữ liệu thực sự thuộc cùng một mục tiêu đánh giá vào một kiểu input rõ ràng.

## 4. Thiết kế một root object theo mục tiêu cụ thể

Giả sử ứng dụng cần chọn những đơn hàng có tổng tiền đạt ngưỡng tối thiểu. Expression cần:

- Danh sách đơn hàng.
- Tổng tiền của từng đơn hàng.
- Ngưỡng tối thiểu.

Có thể tạo các lớp input nhỏ:

~~~java
public class OrderSummary {
    private final String orderNumber;
    private final BigDecimal total;

    public OrderSummary(
            String orderNumber,
            BigDecimal total) {
        this.orderNumber = orderNumber;
        this.total = total;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

public class OrderSelectionInput {
    private final List<OrderSummary> orders;
    private final BigDecimal minimum;

    public OrderSelectionInput(
            List<OrderSummary> orders,
            BigDecimal minimum) {
        this.orders = orders;
        this.minimum = minimum;
    }

    public List<OrderSummary> getOrders() {
        return orders;
    }

    public BigDecimal getMinimum() {
        return minimum;
    }
}
~~~

Root object chỉ chứa những dữ liệu cần cho mục tiêu lọc đơn hàng. Nó không cần giữ toàn bộ Order entity, Customer, PaymentService hoặc Repository nếu expression không sử dụng chúng.

Tạo dữ liệu và đánh giá:

~~~java
List<OrderSummary> orders = Arrays.asList(
    new OrderSummary("ORD-100", new BigDecimal("750000")),
    new OrderSummary("ORD-101", new BigDecimal("250000")),
    new OrderSummary("ORD-102", new BigDecimal("1200000"))
);

OrderSelectionInput input =
    new OrderSelectionInput(
        orders,
        new BigDecimal("500000")
    );

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "orders.?[#this.total >= #root.minimum]"
);

Object result = expression.getValue(context);
~~~

Kết quả là collection chứa ORD-100 và ORD-102.

Trong ví dụ này:

- orders được đọc trên root object.
- #root.minimum lấy ngưỡng từ root object ban đầu.
- #this.total lấy tổng tiền của phần tử đang được selection kiểm tra.
- Kết quả là các đơn hàng đáp ứng điều kiện.

## 5. Phân biệt #root và #this khi xử lý collection

Hai tham chiếu này đặc biệt quan trọng khi expression đi vào selection hoặc projection.

- **#root:** luôn tham chiếu root object của toàn bộ lần đánh giá.
- **#this:** tham chiếu object đang được đánh giá tại vị trí hiện tại; trong selection hoặc projection, nó thường là phần tử collection đang được xử lý.

Với expression:

~~~spel
orders.?[#this.total >= #root.minimum]
~~~

có thể hình dung:

~~~text
Root: OrderSelectionInput
  |
  +-- minimum = 500000
  |
  +-- orders
        |
        +-- OrderSummary 1  <-- #this ở lượt 1
        +-- OrderSummary 2  <-- #this ở lượt 2
        +-- OrderSummary 3  <-- #this ở lượt 3
~~~

Trong mỗi lượt:

- #this thay đổi theo OrderSummary đang được xét.
- #root vẫn là OrderSelectionInput ban đầu.
- #root.minimum luôn đọc cùng ngưỡng tối thiểu.

Nếu viết nhầm #this.minimum trong predicate, SpEL sẽ tìm minimum trên OrderSummary hiện tại. Nếu OrderSummary không có property đó, expression sẽ không hoạt động như mong đợi.

## 6. Đặt dữ liệu chính ở root, dữ liệu phụ ở variable

Không phải lúc nào cũng cần tạo một lớp mới để chứa mọi giá trị. Nếu expression có một object chính và chỉ một vài tham số độc lập, có thể giữ object đó làm root và đăng ký phần còn lại thành variable.

~~~java
Order order = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

context.setVariable("requiredStatus", "PAID");
~~~

Expression:

~~~spel
total >= #minimum && status == #requiredStatus
~~~

Cách thiết kế này phù hợp khi:

- Order là object chính của quy tắc.
- minimum và requiredStatus là tham số của lần đánh giá.
- Các tham số không cần trở thành một phần của mô hình Order.

Nếu một nhóm tham số luôn đi cùng nhau và có ý nghĩa nghiệp vụ riêng, hãy cân nhắc gom chúng vào một input object để biểu thức có hợp đồng rõ ràng hơn.

## 7. Dùng root object chuyên biệt thay vì truyền toàn bộ entity

Một entity trong ứng dụng có thể chứa nhiều liên kết và hành vi:

~~~text
Order
  |
  +-- Customer
  |     +-- Address
  |     +-- Preferences
  |     +-- Contacts
  |
  +-- Payments
  +-- Shipments
  +-- Audit history
  +-- Internal operations
~~~

Nếu expression chỉ cần mã đơn hàng, tổng tiền và trạng thái, việc đưa toàn bộ entity graph làm root object có thể mở ra nhiều đường truy cập không cần thiết.

Thay vào đó, tạo một projection/input object:

~~~java
public class OrderRuleInput {
    private final String orderNumber;
    private final BigDecimal total;
    private final String status;

    public OrderRuleInput(
            String orderNumber,
            BigDecimal total,
            String status) {
        this.orderNumber = orderNumber;
        this.total = total;
        this.status = status;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Ứng dụng chuyển dữ liệu cần thiết từ entity sang input object trước khi đánh giá.

Expression chỉ nhìn thấy ba property được cung cấp. Thay đổi ở Customer, Payments hoặc Audit history không ảnh hưởng đến expression nếu các property đầu vào vẫn giữ nguyên.

## 8. Giữ root object có bề mặt truy cập ổn định

Expression thường truy cập property qua getter và có thể gọi method nếu EvaluationContext cho phép. Vì vậy, lớp root nên có một bề mặt truy cập dễ dự đoán.

Nên ưu tiên:

- Getter rõ nghĩa, tên ổn định.
- Property có kiểu dữ liệu xác định.
- Object con chỉ chứa các property cần thiết.
- Các phương thức thuần đọc nếu expression cần gọi method.
- Dữ liệu đầu vào bất biến trong suốt một lần đánh giá nếu có thể.

Hạn chế đưa vào root các method có tác dụng phụ như cập nhật trạng thái, ghi database, gửi thông báo hoặc thay đổi cấu hình. Nếu expression chỉ cần dữ liệu, một DTO chỉ đọc thường là lựa chọn phù hợp.

Getter cũng nên tránh thay đổi trạng thái. Về kỹ thuật getter có thể thực hiện logic tùy ý, nhưng getter có tác dụng phụ làm kết quả expression khó dự đoán hơn khi được đánh giá nhiều lần.

## 9. Root object không cần chứa service hoặc ApplicationContext

Một cách thiết kế dễ gây phụ thuộc là truyền một object có thể truy cập gần như toàn bộ ứng dụng làm root, ví dụ một facade lớn hoặc ApplicationContext.

Khi đó, expression có thể vô tình phụ thuộc vào:

- Service không liên quan đến mục tiêu.
- Repository và dữ liệu persistence.
- Bean có khả năng thay đổi trạng thái.
- Cấu hình hoặc thành phần hạ tầng.
- Các object con có bề mặt API rộng.

Nếu expression cần một phép tính cụ thể, hãy cân nhắc tính trước trong Java rồi truyền kết quả vào root hoặc variable. Nếu thực sự cần một hành vi, cung cấp một helper nhỏ với đúng method cần dùng và cấu hình MethodResolver phù hợp.

Bean reference qua @ cũng là một cơ chế riêng. Không nên đưa ApplicationContext vào root chỉ để expression có thể tìm mọi bean.

## 10. Root object và EvaluationContext có thể được cấu hình riêng

Có thể đặt root object ngay khi tạo context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(input);
~~~

Hoặc cập nhật root object sau đó:

~~~java
context.setRootObject(input);
~~~

Ngoài ra, một số overload của Expression cho phép truyền root object trực tiếp khi đánh giá:

~~~java
String result =
    expression.getValue(
        context,
        input,
        String.class
    );
~~~

Cách truyền root trực tiếp hữu ích khi cùng một Expression được dùng với nhiều object đầu vào.

Cần chọn một cách nhất quán trong từng luồng xử lý. Nếu context đã chứa root object nhưng lần gọi getValue truyền một root object khác, root được truyền vào overload đó sẽ là object dùng cho lần đánh giá tương ứng.

## 11. Tái sử dụng Expression với nhiều root object

Một Expression đã parse có thể được tái sử dụng với các root object khác nhau nếu chúng đáp ứng cùng hợp đồng property mà expression yêu cầu.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

Order firstOrder = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

Order secondOrder = new Order(
    "ORD-101",
    new BigDecimal("250000"),
    "PENDING"
);

Boolean firstResult =
    expression.getValue(
        context,
        firstOrder,
        Boolean.class
    );

Boolean secondResult =
    expression.getValue(
        context,
        secondOrder,
        Boolean.class
    );
~~~

Kết quả lần lượt là true và false.

Cả hai root object đều cần cung cấp property total. Nếu một object không đáp ứng hợp đồng này, evaluation có thể thất bại.

Trong xử lý đồng thời, nên tránh chia sẻ context có biến thay đổi giữa nhiều request độc lập. Expression có thể được tái sử dụng, còn context và dữ liệu đầu vào nên được quản lý theo phạm vi công việc phù hợp.

## 12. Thiết kế root object theo từng dạng expression

Một số ví dụ giúp xác định dữ liệu nên đặt ở root:

| Mục tiêu expression | Root object nên cung cấp | Variable có thể dùng |
|---|---|---|
| Kiểm tra một đơn hàng | total, status, orderNumber | minimum, requiredStatus |
| Lọc danh sách đơn hàng | orders và các tham số lọc | khoảng thời gian hoặc ngưỡng |
| Tính phí vận chuyển | weight, destination, serviceLevel | rate hoặc cấu hình áp dụng |
| Tạo nhãn sản phẩm | name, price, availability | locale hoặc currency |
| Kiểm tra điều kiện thành viên | membershipLevel, points, active | requiredLevel, minimumPoints |

Không có một cấu trúc root object đúng cho mọi ứng dụng. Hãy bắt đầu từ các property mà expression thực sự cần, rồi tạo một input object có tên và kiểu thể hiện đúng mục tiêu đó.

## 13. Kiểm soát phạm vi truy cập khi đánh giá expression

Root object là một phần của bề mặt truy cập mà expression có thể nhìn thấy. Vì vậy, thiết kế root nhỏ cũng giúp giới hạn những gì biểu thức có thể thao tác.

Một số lựa chọn:

- Chỉ truyền DTO chứa dữ liệu cần đọc.
- Tránh đưa entity có liên kết rộng nếu expression không cần.
- Tránh truyền service hoặc container làm root.
- Đăng ký variables có kiểu và phạm vi rõ ràng.
- Dùng context có giới hạn nếu chỉ cần data binding.
- Cấu hình PropertyAccessor và MethodResolver theo khả năng cần thiết.
- Không để expression không đáng tin cậy có thể gọi tùy ý method gây tác dụng phụ.

Một root object nhỏ không tự nó tạo thành sandbox bảo mật. Expression vẫn có thể truy cập những biến, bean hoặc method khác nếu context cung cấp các cơ chế đó. Phạm vi an toàn phụ thuộc vào toàn bộ EvaluationContext và các object được đưa vào.

## 14. Ví dụ hoàn chỉnh: root object nhỏ cho quy tắc lựa chọn

Giả sử ứng dụng cần kiểm tra một sản phẩm có đủ điều kiện hiển thị hay không. Quy tắc chỉ cần tên, giá, trạng thái còn hàng và ngưỡng giá.

~~~java
public class ProductRuleInput {
    private final String name;
    private final BigDecimal price;
    private final boolean available;

    public ProductRuleInput(
            String name,
            BigDecimal price,
            boolean available) {
        this.name = name;
        this.price = price;
        this.available = available;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

Tạo root object và đánh giá:

~~~java
ProductRuleInput input =
    new ProductRuleInput(
        "Keyboard",
        new BigDecimal("750000"),
        true
    );

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

context.setVariable(
    "maximumPrice",
    new BigDecimal("1000000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "available && price <= #maximumPrice"
);

Boolean visible =
    expression.getValue(context, Boolean.class);

Expression labelExpression =
    parser.parseExpression("name.toUpperCase()");

String label =
    labelExpression.getValue(context, String.class);
~~~

Kết quả:

~~~text
visible = true
label = KEYBOARD
~~~

Root object chỉ cung cấp ba property cần cho quy tắc. Ngưỡng maximumPrice được truyền riêng dưới dạng variable. Expression không cần truy cập Product entity, repository hoặc service.

## 15. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Root object phải là entity chính của ứng dụng.**  
Root object chỉ cần là object phù hợp với mục tiêu expression. Một DTO hoặc input object nhỏ thường đủ.

**Nhầm lẫn 2: Mọi dữ liệu đều phải đăng ký thành variable.**  
Property của root object có thể được truy cập trực tiếp. Variable phù hợp với tham số bổ sung hoặc giá trị độc lập.

**Nhầm lẫn 3: #this luôn giống #root.**  
Ở cấp ngoài cùng chúng thường cùng chỉ root object. Trong selection và projection, #this chuyển sang phần tử đang được xử lý, còn #root vẫn giữ object ban đầu.

**Nhầm lẫn 4: Truyền một object lớn sẽ làm expression linh hoạt hơn mà không có chi phí.**  
Object lớn có thể làm expression phụ thuộc vào nhiều property và method không liên quan, khiến hợp đồng khó hiểu và phạm vi truy cập rộng.

**Nhầm lẫn 5: Root object nhỏ tự động bảo đảm an toàn.**  
Variables, BeanResolver, MethodResolver và PropertyAccessor vẫn ảnh hưởng đến những gì expression có thể truy cập.

**Nhầm lẫn 6: Mỗi lần đánh giá cần parse lại expression.**  
Có thể tái sử dụng Expression đã parse với nhiều root object đáp ứng cùng hợp đồng dữ liệu.

## 16. Ghi nhớ

- Root object là object mặc định để SpEL tra cứu property và gọi method không có tiền tố biến.
- Có thể đặt root bằng constructor StandardEvaluationContext, setRootObject hoặc overload getValue nhận root object.
- #root giữ tham chiếu đến root object của lần đánh giá.
- #this là object hiện tại và có thể thay đổi trong selection hoặc projection.
- Property của root object thường được viết trực tiếp; variable được đăng ký bằng setVariable và tham chiếu bằng #name.
- Nên thiết kế một input object nhỏ, rõ property và kiểu dữ liệu theo mục tiêu expression.
- DTO hoặc projection object giúp tách expression khỏi entity graph và service layer không cần thiết.
- Giữ getter đơn giản, ổn định và ưu tiên dữ liệu chỉ đọc nếu expression chỉ cần truy vấn.
- Root object nhỏ giúp giới hạn bề mặt dữ liệu, nhưng cần cấu hình toàn bộ EvaluationContext để kiểm soát truy cập.
- Một Expression có thể được tái sử dụng với nhiều root object đáp ứng cùng hợp đồng property.

Khi thiết kế root object cho SpEL, hãy bắt đầu từ câu hỏi biểu thức cần đọc hoặc tính toán điều gì. Sau đó chỉ đưa những property và dữ liệu liên quan vào input object, đặt các tham số bổ sung thành variables khi phù hợp, và giữ #root cùng #this rõ ràng trong các biểu thức xử lý collection.
