# Trộn văn bản cố định với biểu thức động trong SpEL

## 1. Template expression là gì?

Spring Expression Language (SpEL) hỗ trợ template expression để ghép văn bản cố định với kết quả của các biểu thức được đánh giá tại runtime. Phần văn bản nằm ngoài cặp dấu phân cách được giữ nguyên; phần nằm trong dấu phân cách được parser xử lý như một biểu thức SpEL.

Với template context mặc định, phần động được đặt trong `#{...}`:

~~~text
Hello #{customer.name}, your order is #{orderCode}.
~~~

Nếu customer.name là Lan và orderCode là ORD-1001, kết quả có dạng:

~~~text
Hello Lan, your order is ORD-1001.
~~~

Template expression hữu ích khi cần tạo nhãn, thông báo, mô tả, nội dung cấu hình hoặc chuỗi hiển thị có cả phần cố định và dữ liệu thay đổi. Thay vì nối nhiều chuỗi trong Java, có thể đặt phần văn bản và biểu thức động cạnh nhau trong một template dễ đọc.

## 2. Dùng TemplateParserContext khi parse template

Khi parse template trực tiếp bằng SpEL, hãy truyền ParserContext để parser biết chuỗi đầu vào là template. Spring cung cấp TemplateParserContext với cặp dấu phân cách mặc định `#{` và `}`:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Hello #{name}!",
        new TemplateParserContext());

String result = template.getValue(customer, String.class);

System.out.println(result); // Hello Lan!
~~~

Trong ví dụ này:

- `Hello ` và `!` là văn bản cố định.
- `name` là biểu thức SpEL được đánh giá trên root object customer.
- TemplateParserContext cho parser biết rằng nội dung giữa `#{` và `}` là phần động.
- Kết quả của toàn bộ template là một String.

Nếu gọi `parseExpression(source)` mà không truyền template ParserContext, parser không tự hiểu các đoạn `#{...}` là phần cần nội suy. Khi dùng template có phần cố định và phần động, hãy chỉ định context phù hợp.

## 3. Trộn nhiều đoạn văn bản và biểu thức

Một template có thể chứa nhiều phần động. Mỗi đoạn `#{...}` được đánh giá và ghép với các đoạn văn bản xung quanh:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Order #{code} | Customer #{customer.name} | Total #{total}",
        new TemplateParserContext());

String description = template.getValue(order, String.class);

System.out.println(description);
// Order ORD-1001 | Customer Lan | Total 150
~~~

Có thể đặt dấu câu, khoảng trắng, dấu phân cách và nhãn ở bên ngoài phần biểu thức. Điều này giúp người đọc nhận ra cấu trúc kết quả ngay từ template.

Mỗi phần động là một biểu thức SpEL độc lập trong cùng template. Có thể dùng property access, phép toán, phép so sánh, method call, variable hoặc điều kiện ba ngôi bên trong từng cặp dấu phân cách.

## 4. Đánh giá template với root object

Khi truyền root object vào getValue, các property trực tiếp bên trong phần động được phân giải từ object đó:

~~~java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

public class Order {
    private final String code;
    private final Customer customer;
    private final int total;

    public Order(String code, Customer customer, int total) {
        this.code = code;
        this.customer = customer;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public Customer getCustomer() {
        return customer;
    }

    public int getTotal() {
        return total;
    }
}

Order order = new Order(
        "ORD-1001",
        new Customer("Lan"),
        150);

Expression template = parser.parseExpression(
        "Order #{code} belongs to #{customer.name}. Total: #{total}",
        new TemplateParserContext());

String message = template.getValue(order, String.class);
~~~

Trong template, `code`, `customer.name` và `total` đều được đọc từ root object order. Không cần tiền tố `#` khi tham chiếu property của root object.

Nếu muốn dùng một variable trong EvaluationContext, cần thêm tiền tố `#` và cung cấp variable trước khi đánh giá.

## 5. Kết hợp root object với variables

Template có thể kết hợp property của root object và variables được truyền qua StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("currency", "VND");
context.setVariable("operator", "Web");

Expression template = parser.parseExpression(
        "Order #{code} | Total: #{total} #{#currency} | Source: #{#operator}",
        new TemplateParserContext());

String result = template.getValue(context, String.class);
~~~

Trong ví dụ này:

- `code` và `total` được đọc từ root object order.
- `#currency` và `#operator` được đọc từ variables trong context.
- Văn bản `Order`, `Total:` và `Source:` được giữ nguyên.

Cách truyền variable giúp tái sử dụng cùng template với dữ liệu khác nhau mà không phải tạo lại expression source.

## 6. Dùng biểu thức điều kiện trong template

Phần động có thể chứa toán tử ba ngôi hoặc các biểu thức Boolean để tạo nội dung thay đổi theo trạng thái:

~~~java
Expression template = parser.parseExpression(
        "Payment: #{paid ? 'received' : 'pending'}",
        new TemplateParserContext());

String message = template.getValue(order, String.class);
~~~

Nếu property paid là true, kết quả có phần văn bản received; nếu false, kết quả có pending.

Có thể kết hợp điều kiện với property và phép toán:

~~~java
Expression template = parser.parseExpression(
        "Shipping: #{total >= 1000 ? 'free' : 'calculated at checkout'}",
        new TemplateParserContext());
~~~

Giữ phần động ngắn và tập trung vào một quyết định. Nếu điều kiện có nhiều cấp hoặc chứa quy tắc nghiệp vụ dài, hãy đưa quy tắc vào method Java có tên rõ ràng rồi gọi method hoặc đọc property kết quả trong template.

## 7. Dùng null-safe navigation và giá trị mặc định

Property lồng nhau có thể null. Có thể dùng null-safe navigation trong phần động để tránh truy cập property trên object null, sau đó dùng Elvis operator để cung cấp giá trị mặc định:

~~~java
Expression template = parser.parseExpression(
        "Customer: #{customer?.name ?: 'Guest'}",
        new TemplateParserContext());

String result = template.getValue(order, String.class);
~~~

Nếu customer hoặc name không có giá trị phù hợp, template sẽ dùng Guest theo quy tắc của Elvis operator. Phần văn bản cố định vẫn được ghép bình thường.

Với nhiều cấp object:

~~~text
Delivery city: #{customer?.address?.city ?: 'Unknown'}
~~~

Đặt null-safe operator ở từng chặng có thể null. Đừng giả định một dấu `?.` ở đầu đường dẫn sẽ bảo vệ mọi property tiếp theo.

Nếu cần phân biệt object null với chuỗi rỗng, hãy chọn biểu thức mặc định phù hợp. Elvis trong SpEL dùng giá trị thay thế cho null và chuỗi rỗng; nếu chỉ muốn thay thế null, dùng điều kiện `== null` rõ ràng.

## 8. Kết quả động có thể là nhiều kiểu dữ liệu

Phần động không bắt buộc phải trả về String. Nó có thể trả về số, Boolean, enum hoặc object. Kết quả của template được ghép thành một chuỗi:

~~~java
Expression template = parser.parseExpression(
        "Quantity: #{quantity}, active: #{enabled}, level: #{level}",
        new TemplateParserContext());

String summary = template.getValue(product, String.class);
~~~

Giá trị của quantity, enabled và level được biểu diễn trong kết quả chuỗi. Với object tùy chỉnh, biểu diễn phụ thuộc vào cách object cung cấp dạng chuỗi, thường là toString.

Để nội dung hiển thị ổn định, nên chọn property cụ thể thay vì chèn toàn bộ object:

~~~text
Customer: #{customer.name}
Address: #{customer.address.city}
~~~

Không nên phụ thuộc vào toString mặc định của một object phức tạp vì kết quả có thể không phù hợp với giao diện người dùng hoặc thay đổi khi class được chỉnh sửa.

## 9. Tạo template một lần và đánh giá nhiều lần

Nếu template source không thay đổi, có thể parse một lần rồi đánh giá với nhiều root object hoặc context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Hello #{customer.name}, order #{code}",
        new TemplateParserContext());

Order firstOrder = TestData.order("Lan", "ORD-1001");
Order secondOrder = TestData.order("Minh", "ORD-1002");

String firstMessage =
        template.getValue(firstOrder, String.class);

String secondMessage =
        template.getValue(secondOrder, String.class);
~~~

Cùng một Expression được tái sử dụng; chỉ dữ liệu root object thay đổi. Cách này tránh parse lại source ở mỗi lần tạo thông báo.

Nếu template cần variables, tạo context cho mỗi lần đánh giá hoặc cập nhật variables theo vòng đời rõ ràng. Tránh chia sẻ một context có mutable variables giữa các request đồng thời nếu việc thay đổi có thể gây ảnh hưởng chéo.

## 10. Dùng template trong @Value của Spring

Trong ứng dụng Spring được quản lý bởi BeanFactory, Spring hỗ trợ SpEL template trong các điểm tích hợp như annotation @Value. Có thể trộn văn bản cố định với biểu thức động:

~~~java
@Component
public class ApplicationDescription {

    @Value("Service: #{T(java.lang.Math).max(2, 5)}")
    private String description;

    public String getDescription() {
        return description;
    }
}
~~~

Spring xử lý phần template và đánh giá biểu thức trong context do BeanFactory cung cấp. Các biểu thức có thể truy cập những đối tượng và khả năng mà expression resolver được cấu hình cho phép.

Một ví dụ khác dùng system property:

~~~java
@Component
public class GreetingConfiguration {

    @Value("Running as #{systemProperties['user.name']}")
    private String greeting;

    public String getGreeting() {
        return greeting;
    }
}
~~~

Với @Value, Spring đã cung cấp cơ chế xử lý expression template. Khi tự tạo SpelExpressionParser trong Java, hãy truyền TemplateParserContext như các ví dụ trước.

## 11. Dùng dấu phân cách tùy chỉnh

TemplateParserContext cho phép chỉ định cặp dấu phân cách khác nếu ứng dụng cần một cú pháp template riêng:

~~~java
ParserContext context = new TemplateParserContext("%{", "}");

Expression template = parser.parseExpression(
        "Order %{code} | Total %{total}",
        context);

String result = template.getValue(order, String.class);
~~~

Trong ví dụ này, phần động được đặt giữa `%{` và `}` thay vì `#{` và `}`.

Dấu phân cách tùy chỉnh hữu ích khi chuỗi template có nhiều ký tự trùng với delimiter mặc định hoặc khi một hệ thống cấu hình đã quy định cú pháp khác. Hãy dùng một cặp delimiter nhất quán trong cùng một loại template và ghi rõ quy ước cho người bảo trì.

Việc thay delimiter chỉ thay đổi cách parser nhận diện đoạn template. Nội dung bên trong vẫn phải là biểu thức SpEL hợp lệ.

## 12. Template expression và nối chuỗi SpEL thông thường

Có hai cách phổ biến để tạo chuỗi có phần động.

Template expression:

~~~java
Expression template = parser.parseExpression(
        "Order #{code} for #{customer.name}",
        new TemplateParserContext());
~~~

Nối chuỗi bằng một expression SpEL thông thường:

~~~java
Expression expression = parser.parseExpression(
        "'Order ' + code + ' for ' + customer.name");
~~~

Template phù hợp khi phần văn bản cố định chiếm phần lớn nội dung và các đoạn động có thể nhìn thấy rõ. Nối chuỗi phù hợp khi toàn bộ kết quả là một biểu thức tính toán hoặc khi phép toán chuỗi là một phần của logic.

Không cần ép mọi trường hợp về một cách viết. Hãy chọn cách làm cho ranh giới giữa nội dung cố định và dữ liệu động dễ hiểu nhất.

## 13. Tránh nối dữ liệu không tin cậy vào template source

Không nên lấy dữ liệu do người dùng nhập rồi ghép trực tiếp vào source của template. Dữ liệu có thể chứa delimiter, dấu nháy hoặc nội dung làm thay đổi cú pháp SpEL.

Hãy giữ template cố định và truyền dữ liệu qua variable:

~~~java
Expression template = parser.parseExpression(
        "Hello #{#displayName}!",
        new TemplateParserContext());

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("displayName", userSuppliedName);

String greeting = template.getValue(context, String.class);
~~~

Ở đây userSuppliedName chỉ là giá trị của variable. Nó không được parse lại như một phần của expression source.

Điều này giúp dữ liệu hiển thị không vô tình trở thành cú pháp SpEL. Tuy nhiên, nếu template source do người dùng không tin cậy cung cấp, bản thân template vẫn có thể thực hiện những thao tác mà EvaluationContext cho phép. Hãy giới hạn nguồn template và khả năng của context theo đúng nhu cầu.

## 14. Lỗi thường gặp

**Quên truyền TemplateParserContext**

Khi parse chuỗi có văn bản cố định và delimiter `#{...}`, cần cung cấp ParserContext dạng template. Nếu không, parser không xử lý các đoạn động theo quy tắc template.

**Nhầm văn bản cố định với biểu thức**

Nội dung bên ngoài delimiter được giữ nguyên. Chỉ nội dung bên trong cặp delimiter mới được parse như SpEL.

**Thiếu dấu đóng hoặc viết sai delimiter**

Một template thiếu dấu `}` hoặc dùng không nhất quán delimiter có thể phát sinh lỗi parse. Kiểm tra cặp prefix/suffix đã cấu hình.

**Dùng sai nguồn dữ liệu**

Property root object được viết trực tiếp như `customer.name`. Variable trong EvaluationContext phải có tiền tố `#`, ví dụ `#displayName`.

**Giả định mọi giá trị động đều đã là String**

Phần động có thể trả về số, Boolean hoặc object. Khi ghép vào template, giá trị được biểu diễn thành chuỗi; hãy chọn property cụ thể để có nội dung ổn định.

**Không xử lý null trong property lồng nhau**

Dùng `?.` tại những chặng có thể null và cung cấp mặc định bằng Elvis hoặc điều kiện tường minh khi cần.

**Nối dữ liệu đầu vào vào template source**

Truyền dữ liệu qua variables hoặc root object. Không để nội dung người dùng trở thành một phần của cú pháp SpEL.

**Đánh giá template không tin cậy bằng context quá rộng**

SpEL có thể truy cập property và method theo cấu hình context. Hạn chế template source và quyền của evaluation context khi dữ liệu không hoàn toàn do ứng dụng kiểm soát.

## 15. Kiểm thử template expression

Có thể kiểm thử template như một Expression bình thường. Test nên xác nhận văn bản cố định, giá trị động và trường hợp dữ liệu thay đổi:

~~~java
@Test
void combinesLiteralTextAndDynamicProperties() {
    Order order = TestData.order("Lan", "ORD-1001");

    Expression template = new SpelExpressionParser().parseExpression(
            "Hello #{customer.name}, order #{code}!",
            new TemplateParserContext());

    String result = template.getValue(order, String.class);

    assertEquals("Hello Lan, order ORD-1001!", result);
}
~~~

Kiểm thử nhiều root object để xác nhận cùng template có thể tái sử dụng:

~~~java
@Test
void reusesTemplateWithDifferentRootObjects() {
    Expression template = new SpelExpressionParser().parseExpression(
            "Order #{code} for #{customer.name}",
            new TemplateParserContext());

    assertEquals(
            "Order ORD-1001 for Lan",
            template.getValue(TestData.order("Lan", "ORD-1001"), String.class));

    assertEquals(
            "Order ORD-1002 for Minh",
            template.getValue(TestData.order("Minh", "ORD-1002"), String.class));
}
~~~

Nếu template dùng variables, tạo StandardEvaluationContext và kiểm tra cả giá trị variable lẫn property của root object. Nếu có property null, kiểm tra kết quả mặc định. Nếu template source được lấy từ cấu hình, kiểm tra parse error riêng với evaluation error để xác định lỗi nằm ở delimiter/cú pháp hay dữ liệu runtime.

## 16. Ghi nhớ

- Template expression trộn văn bản cố định với các biểu thức SpEL động.
- Với delimiter mặc định, phần động nằm trong `#{...}`.
- Khi parse template thủ công, dùng `new TemplateParserContext()`.
- Văn bản ngoài delimiter được giữ nguyên; nội dung bên trong được đánh giá như SpEL.
- Có thể đặt nhiều đoạn động trong cùng một template.
- Property của root object dùng tên trực tiếp; variables dùng tiền tố `#`.
- Phần động có thể dùng property, method, phép toán, điều kiện và null-safe navigation.
- Kết quả template là chuỗi; nên chọn property cụ thể thay vì phụ thuộc vào biểu diễn mặc định của object.
- Có thể dùng delimiter tùy chỉnh với TemplateParserContext(prefix, suffix).
- Spring hỗ trợ template expression trong các điểm tích hợp như @Value; parser tự tạo cần ParserContext rõ ràng.
- Truyền dữ liệu đầu vào qua root object hoặc variables, không nối dữ liệu không tin cậy vào template source.
- Parse một lần và đánh giá nhiều lần khi template source không thay đổi.
