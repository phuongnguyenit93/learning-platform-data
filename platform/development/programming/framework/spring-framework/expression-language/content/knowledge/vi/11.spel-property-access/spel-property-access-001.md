# Truy cập property qua getter theo JavaBean convention trong Spring Expression Language

Spring Expression Language (SpEL) cho phép đọc thuộc tính của object Java bằng cú pháp property như name hoặc customer.address.city. Khi đánh giá một property trên JavaBean thông thường, SpEL sử dụng cơ chế PropertyAccessor để tìm cách đọc giá trị; accessor reflection mặc định có thể giải quyết property thông qua getter theo JavaBean convention.

Điểm quan trọng là biểu thức SpEL viết tên property, còn getter là phương thức Java thực sự được gọi để lấy dữ liệu. Ví dụ, biểu thức name thường được ánh xạ đến phương thức getName() của object hiện tại.

## 1. Property trong JavaBean là gì?

JavaBean thường biểu diễn dữ liệu bằng các thuộc tính (property) và cung cấp phương thức truy cập theo quy ước đặt tên.

Một property có thể có:

- **Getter:** đọc giá trị hiện tại.
- **Setter:** ghi giá trị mới.
- **Cả getter và setter:** hỗ trợ đọc và ghi.
- **Chỉ getter:** hỗ trợ đọc, thường dùng cho property chỉ đọc.

Ví dụ:

~~~java
public class Customer {
    private String name;
    private boolean active;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Trong ví dụ:

- Property name được đọc qua getName().
- Property active được đọc qua isActive().
- Setter tương ứng cho phép cập nhật giá trị.

SpEL dùng tên property trong biểu thức, không cần viết đầy đủ tên getter khi chỉ muốn đọc property.

## 2. Quy ước đặt tên getter theo JavaBean

Quy ước phổ biến cho getter là:

| Loại property | Getter | Tên property trong SpEL |
|---|---|---|
| Property thông thường | getName() | name |
| Property nhiều từ | getFirstName() | firstName |
| Property số lượng | getItemCount() | itemCount |
| Boolean primitive | isActive() | active |
| Boolean với get | getEnabled() | enabled |

Với getter dạng getXxx(), phần Xxx được chuyển thành tên property theo quy tắc JavaBeans. Ví dụ getFirstName() tương ứng property firstName.

Với tên bắt đầu bằng hai chữ cái viết hoa, quy tắc JavaBeans giữ nguyên phần đầu viết hoa. Vì vậy getURL() tương ứng property URL, không phải uRL.

Đối với boolean primitive, dạng isXxx() là quy ước thông dụng, ví dụ isActive(). Với kiểu Boolean wrapper, dùng getActive() thường rõ ràng và tương thích với quy ước getter rộng hơn.

Getter thông thường là phương thức không có tham số và trả về một giá trị. Nên cung cấp getter public với tên nhất quán để property được truy cập rõ ràng qua các công cụ JavaBean.

## 3. SpEL ánh xạ tên property sang getter như thế nào?

Giả sử root object là một Customer:

~~~java
Customer customer = new Customer();
customer.setName("Linh");
customer.setActive(true);
~~~

Có thể phân tích và đánh giá property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression nameExpression =
    parser.parseExpression("name");

Expression activeExpression =
    parser.parseExpression("active");

String name =
    nameExpression.getValue(customer, String.class);

Boolean active =
    activeExpression.getValue(customer, Boolean.class);
~~~

Kết quả:

~~~text
name = Linh
active = true
~~~

Trong lần đánh giá này:

1. customer được dùng làm root object.
2. SpEL nhận property name và tìm cách đọc property trên object hiện tại.
3. ReflectivePropertyAccessor mặc định có thể tìm getter JavaBean tương ứng là getName().
4. Getter được gọi và giá trị Linh được trả về cho expression.
5. Với active, getter isActive() được sử dụng theo quy ước boolean.
6. Giá trị thu được được trả về cho mã Java.

Vì vậy, tên property trong SpEL là một tên logic được accessor giải quyết thành cơ chế đọc thực tế trên object.

## 4. Dùng StandardEvaluationContext để đọc property

Khi cần đăng ký biến hoặc cấu hình thêm cơ chế truy cập, có thể tạo StandardEvaluationContext:

~~~java
Customer customer = new Customer();
customer.setName("Linh");
customer.setActive(true);

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("prefix", "Customer: ");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#prefix + name");

String result =
    expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Customer: Linh
~~~

Trong ví dụ:

- name được đọc từ root object customer thông qua property accessor.
- #prefix được đọc từ biến đã đăng ký trong EvaluationContext.
- Toán tử + kết hợp hai giá trị thành chuỗi mới.

Cú pháp property vẫn hoạt động cùng các biến và toán tử trong một biểu thức.

## 5. Truy cập property lồng nhau

Một property có thể trả về object khác. SpEL cho phép nối nhiều property bằng dấu chấm để đi theo một đường dẫn đối tượng.

Giả sử có cấu trúc:

~~~java
public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class Customer {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Có thể đọc thành phố qua biểu thức:

~~~spel
address.city
~~~

Quá trình truy cập diễn ra như sau:

1. SpEL đọc property address trên root object Customer bằng getter getAddress().
2. Giá trị trả về là object Address.
3. SpEL đọc property city trên Address bằng getter getCity().
4. Giá trị city được trả về làm kết quả expression.

Một đường dẫn dài hơn cũng hoạt động theo cùng nguyên tắc:

~~~spel
order.customer.address.city
~~~

Mỗi đoạn property được giải quyết trên object mà đoạn trước trả về.

## 6. Xử lý property có thể null

Nếu một property trung gian trả về null, việc truy cập tiếp có thể gây lỗi evaluation. Ví dụ, nếu customer.getAddress() trả về null thì biểu thức address.city không thể đọc city trên một object Address không tồn tại.

SpEL hỗ trợ null-safe navigation bằng toán tử ?.:

~~~spel
address?.city
customer?.address?.city
~~~

Khi object ở bên trái ?. là null, biểu thức trả về null tại bước truy cập đó thay vì tiếp tục dereference.

Cần phân biệt:

- Property có tồn tại và getter trả về null: đó có thể là kết quả hợp lệ.
- Property không thể được giải quyết: có thể phát sinh lỗi truy cập.
- Object trung gian null rồi bị truy cập theo cách thông thường: có thể phát sinh lỗi evaluation.

Null-safe navigation giúp biểu thức xử lý dữ liệu tùy chọn rõ ràng hơn.

## 7. Getter có thể được kế thừa

Một lớp Java có thể kế thừa getter từ lớp cha hoặc nhận getter thông qua interface và cơ chế triển khai phù hợp.

Ví dụ:

~~~java
public class BaseEntity {
    private String code;

    public String getCode() {
        return code;
    }
}

public class Product extends BaseEntity {
}
~~~

Nếu root object là Product, biểu thức:

~~~spel
code
~~~

có thể đọc property code thông qua getter được kế thừa getCode().

Điều này hữu ích khi các lớp domain chia sẻ thuộc tính chung như id, code, createdAt hoặc audit metadata trong lớp cơ sở.

## 8. Property access khác với gọi phương thức trực tiếp

Hai cú pháp dưới đây có thể trả về cùng một giá trị:

~~~spel
name
getName()
~~~

Nhưng chúng thể hiện hai cơ chế truy cập khác nhau:

- name là property access. SpEL yêu cầu PropertyAccessor giải quyết property và accessor reflection mặc định thường gọi getter JavaBean tương ứng.
- getName() là method invocation. SpEL yêu cầu MethodResolver tìm và gọi phương thức có tên getName.

Khi ý định là đọc dữ liệu theo mô hình JavaBean, dùng cú pháp property như name giúp biểu thức tập trung vào ý nghĩa của dữ liệu thay vì chi tiết tên phương thức.

Khi ý định thực sự là gọi một hành vi hoặc phương thức nghiệp vụ, dùng cú pháp lời gọi phương thức với ngoặc.

## 9. PropertyAccessor chịu trách nhiệm truy cập property

EvaluationContext có thể chứa một hoặc nhiều PropertyAccessor. Accessor xác định cách đọc hoặc ghi property trên object.

Trong StandardEvaluationContext, ReflectivePropertyAccessor mặc định hỗ trợ truy cập nhiều property Java thông qua reflection. Với JavaBean thông thường, accessor có thể tìm getter phù hợp và gọi getter để đọc giá trị.

Ứng dụng cũng có thể đăng ký accessor tùy chỉnh để ánh xạ property sang nguồn dữ liệu khác. Ví dụ, một accessor có thể đọc dữ liệu từ object proxy, cấu trúc dữ liệu riêng hoặc một mô hình domain đặc biệt.

Do đó, kết quả truy cập property không chỉ phụ thuộc vào tên trong biểu thức mà còn phụ thuộc vào accessor được cấu hình và object runtime.

## 10. Đọc property và ghi property là hai thao tác khác nhau

Getter hỗ trợ đọc giá trị. Nếu ứng dụng muốn ghi property, cần có cơ chế ghi tương ứng.

Ví dụ:

~~~java
Expression property =
    parser.parseExpression("name");

Object currentName =
    property.getValue(context);

if (property.isWritable(context)) {
    property.setValue(context, "Minh");
}
~~~

Trong trường hợp thông thường, accessor reflection có thể dùng setter setName() để ghi property name. Một property chỉ có getter có thể đọc được nhưng không nhất thiết ghi được.

Khả năng ghi còn phụ thuộc vào context và PropertyAccessor. Context chỉ đọc có thể cho phép getValue nhưng từ chối setValue.

## 11. Kiểu dữ liệu của giá trị getter trả về

Kiểu runtime của giá trị property thường tương ứng với kiểu trả về của getter.

Ví dụ:

~~~java
public BigDecimal getPrice() {
    return price;
}

public boolean isActive() {
    return active;
}
~~~

Khi SpEL đọc:

~~~spel
price
active
~~~

giá trị nhận được lần lượt là BigDecimal và Boolean (giá trị boolean được đóng gói khi trả qua API Java tổng quát).

Có thể yêu cầu kiểu kết quả khi gọi getValue:

~~~java
BigDecimal price =
    expression.getValue(context, BigDecimal.class);
~~~

Nếu kiểu runtime không trùng với kiểu đích, TypeConverter của EvaluationContext có thể thực hiện chuyển đổi khi được hỗ trợ. Nếu không thể chuyển đổi, lời gọi có thể phát sinh lỗi.

## 12. Getter không nên tạo tác dụng phụ

Theo quy ước JavaBean, getter chủ yếu dùng để cung cấp dữ liệu. Một getter lý tưởng không thay đổi trạng thái object và không thực hiện hành động nghiệp vụ gây tác dụng phụ.

Tuy nhiên, về mặt kỹ thuật, getter vẫn là một phương thức Java. Nó có thể chứa logic tính toán, truy cập dữ liệu hoặc thậm chí thay đổi trạng thái nếu người viết triển khai như vậy.

Ví dụ getter có tác dụng phụ:

~~~java
public String getStatus() {
    accessCount++;
    return status;
}
~~~

Khi SpEL đánh giá property status, getter có thể làm accessCount tăng lên.

Vì vậy, nếu expression được đánh giá nhiều lần, không nên giả định việc đọc property luôn hoàn toàn không có tác dụng phụ. Thiết kế getter đơn giản và ổn định giúp biểu thức dễ dự đoán hơn.

## 13. Lỗi thường gặp khi truy cập property

Một số tình huống có thể khiến property access thất bại:

- Tên property viết sai hoặc không tồn tại trên object hiện tại.
- Getter không phù hợp và accessor đang dùng không có cơ chế truy cập thay thế.
- Object trung gian trên đường dẫn là null.
- Getter phát sinh exception trong lúc thực thi.
- Context không có PropertyAccessor phù hợp.
- Kiểu trả về không thể chuyển đổi sang kiểu mà ứng dụng yêu cầu.

Khi điều tra, hãy kiểm tra theo thứ tự:

1. Root object có đúng kiểu không?
2. Tên property có khớp với JavaBean property không?
3. Getter có thể được accessor tìm thấy và gọi không?
4. Các object trung gian có null không?
5. Getter có tự phát sinh lỗi không?
6. Kiểu kết quả có tương thích với kiểu đích không?

## 14. Ví dụ hoàn chỉnh: property getter kết hợp biến và điều kiện

Giả sử Product có getter getName(), getPrice() và isAvailable(). Ứng dụng muốn tạo nhãn hiển thị dựa trên giá và tình trạng còn hàng.

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;
    private final boolean available;

    public Product(String name, BigDecimal price, boolean available) {
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

Đánh giá biểu thức:

~~~java
Product product = new Product(
    "Keyboard",
    new BigDecimal("750000"),
    true
);

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "maximumPrice",
    new BigDecimal("1000000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "available && price <= #maximumPrice ? name.toUpperCase() : 'NOT ELIGIBLE'"
);

String label =
    expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
KEYBOARD
~~~

SpEL đọc available qua isAvailable(), đọc price qua getPrice(), lấy maximumPrice từ biến trong context và đọc name qua getName() ở nhánh được chọn. Toán tử logic và điều kiện kết hợp những giá trị đó để tạo chuỗi cuối cùng.

## 15. Ghi nhớ

- Property access dùng tên property trong biểu thức; accessor giải quyết cách đọc giá trị từ object.
- JavaBean getter thông dụng là getXxx() và isXxx() cho boolean primitive.
- Tên property được suy ra từ tên getter theo quy tắc JavaBeans, ví dụ getFirstName() tương ứng firstName.
- Root object là điểm bắt đầu khi đọc property không có tiền tố biến.
- #root và #this giúp xác định đối tượng gốc và đối tượng hiện tại trong các biểu thức phức tạp.
- PropertyAccessor quyết định cách đọc hoặc ghi property; accessor tùy chỉnh có thể thay đổi cách truy cập.
- Getter trả về giá trị runtime, và giá trị đó có thể được kết hợp với biến, toán tử hoặc lời gọi phương thức.
- getValue có thể trả Object hoặc yêu cầu kiểu đích; chuyển đổi phụ thuộc TypeConverter.
- Getter nên tránh tác dụng phụ để kết quả đánh giá dễ dự đoán.
- Lỗi property access có thể đến từ tên property, getter, object null, accessor hoặc kiểu kết quả.

Khi đọc một biểu thức SpEL có property, hãy lần theo tên property đến getter tương ứng, xác định object mà getter được gọi trên đó, rồi theo dõi giá trị trả về được sử dụng như thế nào trong phần còn lại của biểu thức.
