# Property của root object và object trung gian

Trong SpEL, một biểu thức thường bắt đầu bằng cách đọc thuộc tính của một đối tượng đầu vào. Đối tượng đầu vào mặc định được gọi là root object. Từ root object, biểu thức có thể đi tiếp qua nhiều thuộc tính để đến các đối tượng lồng bên trong. Những đối tượng xuất hiện ở giữa đường dẫn đó được gọi là object trung gian.

Ví dụ, với đường dẫn:

    customer.address.city

SpEL đọc thuộc tính customer trên root object, lấy đối tượng Customer, đọc tiếp address để lấy Address, rồi đọc city trên đối tượng Address. Hiểu rõ root object và các object trung gian giúp xác định biểu thức đang đọc dữ liệu từ đâu, vì sao một đường dẫn có thể lỗi khi gặp null và cách dùng #root hoặc #this trong các phép xử lý collection.

## 1. Root object là gì?

Root object là đối tượng gốc mà SpEL dùng làm điểm bắt đầu khi đánh giá biểu thức. Nó được cung cấp thông qua EvaluationContext hoặc trực tiếp trong lời gọi getValue.

Giả sử ứng dụng có mô hình đơn hàng:

    public class Order {
        private Customer customer;
        private BigDecimal total;

        public Customer getCustomer() {
            return customer;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

    public class Customer {
        private Address address;
        private String name;

        public Address getAddress() {
            return address;
        }

        public String getName() {
            return name;
        }
    }

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }
    }

Nếu Order là root object, biểu thức có thể đọc trực tiếp các thuộc tính của nó:

    customer
    total
    customer.name

Tên thuộc tính không cần viết tiền tố # khi đang truy cập từ root object. Vì vậy, customer.name có nghĩa là lấy thuộc tính customer của root, sau đó lấy name trên đối tượng customer vừa nhận được.

Có thể viết tường minh điểm bắt đầu bằng biến dựng sẵn #root:

    #root.customer.name
    #root.total

Hai cách customer.name và #root.customer.name có cùng điểm bắt đầu khi root object là Order. Cách viết tường minh hữu ích khi biểu thức có nhiều object trung gian hoặc khi đang ở trong selection/projection và cần phân biệt root với đối tượng hiện tại.

## 2. Cung cấp root object cho biểu thức

Có hai cách phổ biến để cung cấp root object.

### Đặt root object trong EvaluationContext

    Order order = orderService.findOrder(orderId);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("customer.address.city");

    String city = expression.getValue(context, String.class);

Khi tạo StandardEvaluationContext với order, đối tượng đó trở thành root object. Biểu thức không cần nhận lại order trong từng lần getValue.

Có thể thay đổi root object của context bằng setRootObject nếu cần, nhưng nên kiểm soát vòng đời context để không vô tình đánh giá nhiều request trên cùng một context có trạng thái thay đổi.

### Truyền root object khi gọi getValue

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("customer.address.city");

    String city = expression.getValue(context, order, String.class);

Ở cách này, order được truyền trực tiếp vào lần đánh giá. SimpleEvaluationContext phù hợp với ví dụ chỉ cần đọc thuộc tính. Việc chọn context phụ thuộc vào khả năng mà biểu thức cần dùng; nếu biểu thức cần type reference, bean reference hoặc những tính năng rộng hơn thì phải cấu hình context tương ứng.

Dù chọn cách nào, điều quan trọng là biết chính xác đối tượng nào đang làm root object tại thời điểm đánh giá. Một biểu thức hợp lệ về cú pháp vẫn có thể lỗi nếu root object không có property mà biểu thức yêu cầu.

## 3. Property của root object và property của object trung gian

Một property path là chuỗi truy cập thuộc tính nối tiếp nhau bằng dấu chấm.

    customer.address.city

Có thể phân tích theo từng bước:

1. customer được đọc trên root object Order.
2. Kết quả của customer là một đối tượng Customer; đối tượng này trở thành mục tiêu cho bước tiếp theo.
3. address được đọc trên Customer.
4. Kết quả của address là một đối tượng Address.
5. city được đọc trên Address và trở thành kết quả cuối cùng.

Như vậy, chỉ property đầu tiên customer được đọc trực tiếp trên root object. address và city thuộc các object trung gian được trả về từ bước trước.

Một đường dẫn dài hơn cũng hoạt động theo cùng nguyên tắc:

    customer.address.country.region.code

Mỗi dấu chấm chuyển việc truy cập sang đối tượng được trả về bởi property ngay trước nó. Nếu một bước trả về kiểu không có property tiếp theo, SpEL không thể tiếp tục đường dẫn và sẽ phát sinh lỗi đánh giá.

Cách phân biệt này hữu ích khi đọc lỗi. Nếu thông báo cho biết không tìm thấy property city, hãy kiểm tra kiểu của đối tượng đang đứng ngay trước .city, thay vì chỉ kiểm tra kiểu root object ban đầu.

## 4. SpEL truy cập JavaBean property như thế nào?

Trong biểu thức, tên property thường tương ứng với getter của JavaBean. Ví dụ:

    order.customer
    order.total

thường được phân giải thông qua getCustomer() và getTotal(). Với thuộc tính Boolean có getter dạng isActive(), tên property là active:

    customer.active

Không cần gọi getter như một phương thức:

    customer.getName()

Đây là cách viết truy cập property, còn cú pháp gọi phương thức là một thao tác khác:

    customer.getName()

Cả hai có thể cho cùng giá trị trong một JavaBean thông thường, nhưng khi mục tiêu là đọc property, nên dùng tên property ngắn gọn:

    customer.name

Việc truy cập thực tế phụ thuộc vào PropertyAccessor của EvaluationContext. Các context mặc định của Spring cung cấp accessor cho những kiểu đối tượng phổ biến. Nếu ứng dụng có kiểu dữ liệu đặc biệt, có thể cần một PropertyAccessor tùy chỉnh.

Một getter có thể thực thi mã Java. Vì vậy, property access không nhất thiết là đọc một trường bộ nhớ đơn giản. Khi đưa đối tượng vào context, hãy cân nhắc các getter có side effect, truy vấn dữ liệu, chi phí cao hoặc để lộ thông tin nhạy cảm.

## 5. Root object không giống biến trong context

Ngoài root object, EvaluationContext còn có thể chứa các biến được đặt tên. Biến được tham chiếu bằng tiền tố #.

Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", new BigDecimal("500000"));

    Expression expression = parser.parseExpression(
            "total >= #minimumTotal");

Trong biểu thức:

- total là property của root object order.
- #minimumTotal là biến được đăng ký trong context.

Có thể tham chiếu root object một cách tường minh:

    #root.total >= #minimumTotal

Điều này làm rõ hai nguồn dữ liệu khác nhau: property thuộc đối tượng đầu vào và biến được truyền riêng cho biểu thức. Đừng nhầm #root với một biến do ứng dụng tự đặt; đây là biến dựng sẵn của SpEL đại diện cho root object.

## 6. #this và sự thay đổi đối tượng hiện tại

#root luôn đại diện cho root object của lần đánh giá. #this đại diện cho đối tượng đang là mục tiêu hiện tại của biểu thức tại vị trí được đánh giá.

Ở đầu một biểu thức thông thường, #this thường cùng trỏ đến root object. Nhưng trong các thao tác trên collection như selection và projection, #this được đặt thành phần tử đang được xử lý.

Giả sử root object là Order và có collection lines:

    lines.?[quantity > 0]

Trong điều kiện selection, quantity được đọc trên từng phần tử của lines. Có thể viết rõ:

    lines.?[#this.quantity > 0]

Nếu cần so sánh thuộc tính của từng dòng với property của root object, hãy dùng cả hai:

    lines.?[#this.quantity > #root.minimumQuantity]

Ở đây:

- #this.quantity là quantity của dòng đơn hàng hiện tại.
- #root.minimumQuantity là minimumQuantity của Order ban đầu.

Sự khác biệt này rất quan trọng. Nếu viết nhầm #this.minimumQuantity, SpEL sẽ tìm property đó trên từng dòng đơn hàng. Nếu LineItem không có property này, biểu thức sẽ lỗi dù Order có property minimumQuantity.

## 7. Truy cập object trung gian có thể null

Một property path thông thường giả định rằng đối tượng ở mỗi bước tồn tại. Ví dụ:

    customer.address.city

sẽ gặp vấn đề nếu customer hoặc address là null. Khi SpEL cố truy cập property tiếp theo trên một giá trị null, quá trình đánh giá có thể phát sinh lỗi.

Có thể dùng toán tử null-safe navigation ?. tại từng đoạn có khả năng null:

    customer?.address?.city

Nếu customer là null, kết quả của phần truy cập an toàn là null. Nếu customer có giá trị nhưng address là null, toán tử an toàn ở đoạn address?.city ngăn lỗi khi đọc city.

Chỉ đặt ?. ở bước đầu chưa đủ nếu các object trung gian sau đó cũng có thể null:

    customer?.address.city

Trong biểu thức này, đoạn address.city vẫn là truy cập thông thường. Nếu address null, việc đọc city có thể lỗi. Hãy đặt ?. ở mỗi ranh giới mà đối tượng phía trước có thể null:

    customer?.address?.city

Null-safe navigation chỉ trả về null cho thao tác được bảo vệ. Nó không biến toàn bộ object graph thành an toàn một cách tự động. Khi biểu thức tiếp tục truy cập các property khác, hãy xem xét từng mắt xích.

## 8. Kết hợp null-safe navigation với Elvis

Sau khi truy cập an toàn một property, có thể dùng Elvis để cung cấp giá trị mặc định:

    customer?.address?.city ?: 'Chưa cập nhật'

Nếu customer hoặc address là null, kết quả của property path là null và Elvis trả về Chưa cập nhật. Nếu city là chuỗi rỗng, Elvis cũng dùng giá trị mặc định. Nếu city có nội dung, giá trị đó được giữ lại.

Hai toán tử có trách nhiệm riêng:

- ?. bảo vệ một lần truy cập property hoặc method khi đối tượng có thể null.
- ?: chọn giá trị mặc định khi kết quả là null hoặc chuỗi rỗng.

Nếu bỏ null-safe navigation, Elvis không thể bắt lỗi phát sinh trong lúc truy cập một property trung gian. Ví dụ:

    customer.address.city ?: 'Unknown'

vẫn có thể lỗi trước khi Elvis được đánh giá nếu customer hoặc address là null.

Có thể kết hợp với điều kiện ba ngôi khi quy tắc mặc định phức tạp hơn:

    customer?.address?.city != null
        ? customer.address.city
        : 'Unknown'

Tuy nhiên, với mục tiêu chỉ cung cấp fallback, null-safe navigation cùng Elvis thường ngắn gọn và ít lặp lại đường dẫn hơn.

## 9. Truy cập Map, List và mảng trong object graph

Không phải mọi object trung gian đều là JavaBean. Nếu property trả về Map, List hoặc mảng, biểu thức có thể tiếp tục bằng cú pháp truy cập phần tử.

Ví dụ với Map:

    metadata['region']
    metadata['owner']['name']

Với List hoặc mảng:

    lines[0]
    lines[0].product.name

Có thể kết hợp nhiều kiểu object trong cùng một đường dẫn:

    order.attributes['shipping'].address.city

Trong ví dụ này, attributes là Map; khóa shipping trả về một đối tượng có property address; address lại có property city.

Nếu collection có thể rỗng hoặc chỉ số có thể vượt phạm vi, cần kiểm tra điều kiện trước khi truy cập phần tử. Null-safe navigation xử lý đối tượng null, nhưng không tự đảm bảo một chỉ số tồn tại hoặc một khóa Map có mặt.

## 10. Ví dụ hoàn chỉnh: lấy thành phố giao hàng

Giả sử ứng dụng nhận một OrderView có customer và shippingAddress. Mục tiêu là lấy thành phố giao hàng; nếu thiếu địa chỉ hoặc thành phố thì trả về nhãn mặc định.

Mô hình rút gọn:

    public class OrderView {
        private CustomerView customer;
        private AddressView shippingAddress;

        public CustomerView getCustomer() {
            return customer;
        }

        public AddressView getShippingAddress() {
            return shippingAddress;
        }
    }

    public class AddressView {
        private String city;

        public String getCity() {
            return city;
        }
    }

Biểu thức có thể được viết:

    shippingAddress?.city ?: 'Chưa có thành phố'

Đánh giá bằng Java:

    OrderView order = orderService.getOrder(orderId);

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "shippingAddress?.city ?: 'Chưa có thành phố'");

    String city = expression.getValue(context, order, String.class);

Trong biểu thức này, shippingAddress là property trên root object OrderView. city là property trên object trung gian AddressView. Nếu shippingAddress null, null-safe navigation trả về null và Elvis chọn nhãn mặc định.

Nếu quy tắc cần đọc thành phố của khách hàng khi không có địa chỉ giao hàng riêng, có thể viết:

    shippingAddress?.city
        ?: customer?.address?.city
        ?: 'Chưa có thành phố'

SpEL đánh giá lần lượt các biểu thức Elvis từ trái sang phải. Giá trị đầu tiên khác null và khác chuỗi rỗng sẽ được chọn. Vì vậy, thành phố giao hàng được ưu tiên; nếu thiếu thì dùng địa chỉ của khách hàng; nếu cả hai đều thiếu thì dùng nhãn mặc định.

## 11. Những lỗi thường gặp khi đọc property path

| Cách viết hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| customer.name nhưng root không có customer | Bắt đầu từ sai root object | Kiểm tra root được truyền vào getValue hoặc context |
| customer.address.city lỗi khi address null | Object trung gian không tồn tại | Dùng customer?.address?.city nếu các bước có thể null |
| #this.minimumQuantity trong selection | #this là phần tử collection hiện tại | Dùng #root.minimumQuantity nếu property thuộc root |
| metadata.region nhưng metadata là Map | Truy cập như JavaBean property thay vì khóa | Dùng metadata['region'] |
| lines[0] lỗi | Collection rỗng hoặc chỉ số không hợp lệ | Kiểm tra kích thước trước khi truy cập |
| Không tìm thấy property | Property accessor không hỗ trợ kiểu dữ liệu hoặc tên property sai | Kiểm tra getter, kiểu runtime và PropertyAccessor |

Khi gặp lỗi, hãy phân rã đường dẫn theo từng dấu chấm. Xác định giá trị và kiểu runtime sau mỗi bước. Cách này thường tìm ra chính xác object trung gian nào bị null hoặc không có property mong đợi.

## 12. Giới hạn truy cập và thiết kế dữ liệu đầu vào

Một biểu thức có thể đọc bất kỳ property nào mà PropertyAccessor được cấu hình cho phép. Vì vậy, đối tượng đưa vào làm root cần được lựa chọn có chủ đích.

Một số nguyên tắc thực tế:

- Dùng DTO hoặc object view chỉ chứa dữ liệu mà rule cần đọc.
- Tránh đưa entity có nhiều quan hệ lazy hoặc getter có thể kích hoạt truy vấn ngoài ý muốn.
- Không cung cấp object graph chứa thông tin bí mật nếu biểu thức không cần đến.
- Dùng context chỉ đọc khi rule chỉ có nhiệm vụ đánh giá.
- Nếu biểu thức đến từ nguồn bên ngoài, giới hạn property accessor và các khả năng khác của context; không cho phép truy cập rộng tùy ý.
- Kiểm thử đường dẫn với object trung gian null, collection rỗng và property không tồn tại.

Tách root object và các object trung gian rõ ràng cũng giúp hợp đồng của rule ổn định hơn. Nếu cấu trúc entity thay đổi, một DTO chuyên dụng có thể giữ nguyên property path mà rule đang sử dụng.

## Kết luận

Root object là điểm bắt đầu của một lần đánh giá SpEL. Property đầu tiên được đọc trên root; mỗi property tiếp theo được đọc trên object trung gian mà bước trước trả về. Có thể dùng #root để tham chiếu tường minh đối tượng gốc, còn #this đại diện cho đối tượng hiện tại và thay đổi trong selection/projection.

Khi một property path đi qua những đối tượng có thể null, hãy dùng null-safe navigation tại từng mắt xích cần bảo vệ. Với Map, List hoặc mảng, dùng cú pháp truy cập phần tử tương ứng và kiểm tra khóa/chỉ số trước khi đọc. Cung cấp root object và object graph phù hợp, có giới hạn quyền truy cập, sẽ giúp biểu thức dễ hiểu, ổn định và an toàn hơn khi chạy trong ứng dụng Spring.