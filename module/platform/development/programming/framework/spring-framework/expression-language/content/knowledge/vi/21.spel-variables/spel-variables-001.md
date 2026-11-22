# Khai báo và đọc biến trong EvaluationContext

Trong Spring Expression Language (SpEL), **variable** là một giá trị được ứng dụng đưa vào môi trường đánh giá biểu thức. Biến cho phép biểu thức sử dụng dữ liệu được chuẩn bị bên ngoài mà không cần ghi cứng giá trị trong chuỗi SpEL hoặc đưa tất cả dữ liệu vào root object.

Trong biểu thức, biến được tham chiếu bằng dấu **#** theo sau là tên biến, ví dụ **#minimumPrice**, **#customer** hoặc **#requestId**. Ứng dụng khai báo biến trên **EvaluationContext**, thường bằng phương thức **setVariable(...)** của StandardEvaluationContext.

Biến có thể chứa số, chuỗi, Boolean, collection hoặc một object Java. Sau khi được cung cấp, biểu thức có thể đọc chính giá trị đó, truy cập property, gọi method nếu context cho phép hoặc kết hợp nó với các toán tử SpEL.

## Khai báo biến bằng setVariable(...)

Ví dụ đơn giản:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumAge", 18);

Expression expression =
        parser.parseExpression("#minimumAge >= 18");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Phương thức **setVariable("minimumAge", 18)** đăng ký một biến tên minimumAge với giá trị Integer 18 trong context. Trong chuỗi SpEL, **#minimumAge** đọc giá trị đó. Kết quả của phép so sánh là true.

Tên truyền vào setVariable không cần có dấu #. Dấu # chỉ xuất hiện khi tham chiếu biến trong biểu thức. Tên biến có phân biệt chữ hoa và chữ thường; cần dùng cùng một cách viết khi khai báo và khi đọc.

Có thể cập nhật giá trị biến trong context:

~~~java
context.setVariable("minimumAge", 21);

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Cùng Expression có thể được đánh giá lại và nhận giá trị mới từ context. Điều này hữu ích khi cú pháp biểu thức cố định nhưng dữ liệu đầu vào thay đổi theo từng lần thực thi.

## Đọc biến bằng #variable

Cú pháp tham chiếu biến là **#variableName**:

~~~java
context.setVariable("greeting", "Hello");
context.setVariable("name", "An");

Expression expression =
        parser.parseExpression("#greeting + ' ' + #name");

String message =
        expression.getValue(context, String.class);
~~~

Kết quả là **Hello An**. Hai biến được lấy từ EvaluationContext và nối với string literal trong biểu thức.

Biến cũng có thể được dùng trong phép tính:

~~~java
context.setVariable("unitPrice", new BigDecimal("12.50"));
context.setVariable("quantity", 4);

Expression expression =
        parser.parseExpression("#unitPrice * #quantity");

BigDecimal total =
        expression.getValue(context, BigDecimal.class);
~~~

Trong ví dụ này, cả hai toán hạng đến từ biến. SpEL đánh giá phép nhân và trả về kết quả số theo kiểu tương ứng. Khi biểu thức xử lý tiền tệ hoặc số thập phân cần độ chính xác, nên cung cấp BigDecimal ngay từ đầu vào thay vì truyền Double.

## Phân biệt variable với root object property

Root object là đối tượng được đặt làm đối tượng gốc của lần đánh giá. Property của root object có thể được truy cập trực tiếp bằng tên property. Biến trong context được tham chiếu bằng dấu #.

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

~~~java
Product product =
        new Product("Keyboard", new BigDecimal("80.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable(
        "minimumPrice",
        new BigDecimal("50.00"));

Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean eligible =
        expression.getValue(context, Boolean.class);
~~~

Trong biểu thức:

- **price** là property của root object product.
- **#minimumPrice** là biến được ứng dụng đưa vào EvaluationContext.
- Kết quả là true vì giá sản phẩm lớn hơn hoặc bằng ngưỡng.

Có thể viết rõ root object bằng **#root.price**:

~~~text
#root.price >= #minimumPrice
~~~

Cách viết tường minh hữu ích khi biểu thức có nhiều object hoặc khi đang ở trong collection selection/projection và #this thay đổi theo phần tử hiện tại.

## Biến có thể chứa object

Biến không chỉ lưu giá trị nguyên thủy hoặc chuỗi. Nó có thể tham chiếu đến một object Java, sau đó biểu thức truy cập property của object đó:

~~~java
Customer customer =
        new Customer("An", "an@example.com");

context.setVariable("customer", customer);

Expression expression =
        parser.parseExpression("#customer.email");

String email =
        expression.getValue(context, String.class);
~~~

Ở đây, **#customer** là biến chứa reference đến object Customer. **#customer.email** đọc property email của object đó thông qua cơ chế truy cập property trong EvaluationContext.

Nếu context cho phép gọi instance method, biểu thức cũng có thể gọi method trên object:

~~~java
Expression expression =
        parser.parseExpression("#customer.getEmail()");
~~~

Khả năng gọi method phụ thuộc vào method resolver và cấu hình context. Với SimpleEvaluationContext được tạo bằng builder data binding chỉ đọc, instance method invocation không được bật mặc định. Không nên mở quyền gọi method nếu use case chỉ cần đọc property.

## Biến có thể chứa collection hoặc Map

Ứng dụng có thể đưa một collection vào context rồi sử dụng biến đó trong các collection operation của SpEL:

~~~java
List<Integer> scores = List.of(65, 82, 91, 74);

context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores.?[#this >= 80]");

List<?> passed =
        expression.getValue(context, List.class);
~~~

Kết quả chứa 82 và 91. Trong selection predicate, **#scores** tham chiếu collection được khai báo; **#this** là phần tử hiện tại đang được kiểm tra.

Với Map, biến cũng có thể được truy cập theo key:

~~~java
Map<String, String> settings = Map.of(
        "theme", "dark",
        "language", "vi");

context.setVariable("settings", settings);

Expression expression =
        parser.parseExpression("#settings['theme']");

String theme =
        expression.getValue(context, String.class);
~~~

Kết quả là **dark**. Biến #settings chứa Map, còn chuỗi theme là key được dùng để tra cứu.

## Đọc biến bằng lookupVariable(...)

API **lookupVariable(String name)** của EvaluationContext cho phép ứng dụng đọc giá trị biến từ Java thay vì từ biểu thức:

~~~java
context.setVariable("requestId", "REQ-1024");

Object requestId =
        context.lookupVariable("requestId");
~~~

Tên truyền vào lookupVariable không có dấu #. Đây là thao tác đọc biến ở phía Java; nó khác với việc viết **#requestId** bên trong chuỗi SpEL.

Ví dụ, ứng dụng có thể lấy biến từ context để ghi log hoặc truyền vào một bước xử lý khác. Nếu biến chưa được khai báo hoặc có giá trị null, kết quả lookup có thể là null. Khi cần phân biệt hai trường hợp đó, hãy quản lý trạng thái khai báo biến rõ ràng trong mã ứng dụng thay vì dựa vào giá trị trả về null để suy luận.

## Biến null và biến chưa được khai báo

Một biến có thể được khai báo với giá trị null:

~~~java
context.setVariable("middleName", null);

Expression expression =
        parser.parseExpression("#middleName == null");

Boolean isMissing =
        expression.getValue(context, Boolean.class);
~~~

Biểu thức kiểm tra biến có giá trị null. Tuy nhiên, khi một biến không được khai báo, việc tham chiếu nó cũng không cung cấp được giá trị cho biểu thức và có thể dẫn đến lỗi evaluation tùy ngữ cảnh sử dụng.

Nếu biến là đầu vào tùy chọn, hãy quyết định rõ cách biểu diễn trạng thái thiếu: đặt biến thành null, cung cấp một giá trị mặc định hoặc chỉ tạo biểu thức sau khi đã xác thực dữ liệu. Không nên để việc thiếu biến trở thành lỗi khó hiểu ở giữa luồng nghiệp vụ.

Có thể dùng toán tử null-safe khi truy cập property của một biến có thể null:

~~~java
context.setVariable("customer", null);

Expression expression =
        parser.parseExpression("#customer?.email");

String email =
        expression.getValue(context, String.class);
~~~

Khi customer null, truy cập null-safe trả về null thay vì cố đọc email trên một object không tồn tại. Cú pháp null-safe cần được hỗ trợ bởi phiên bản Spring đang dùng.

## Biến và các biến đặc biệt #root, #this

**#root** và **#this** là những biến đặc biệt do SpEL quản lý:

- **#root** tham chiếu đến root object ban đầu của lần đánh giá.
- **#this** tham chiếu đến đối tượng hiện tại tại vị trí đang đánh giá; nó có thể thay đổi trong selection hoặc projection.
- **#myVariable** tham chiếu đến biến do ứng dụng cung cấp trong EvaluationContext.

Ví dụ trong selection:

~~~java
Expression expression = parser.parseExpression(
        "#products.?[#this.price >= #root.minimumPrice]");
~~~

Ở đây, #this là Product hiện tại đang được xét, còn #root là object ban đầu chứa collection và ngưỡng giá. Nếu ứng dụng có biến **#minimumPrice**, biểu thức cũng có thể dùng biến đó thay cho property của root object.

Không nên nhầm biến nghiệp vụ do ứng dụng đặt với hai biến đặc biệt này. Dùng tên rõ ràng như #minimumPrice, #currentUser hoặc #featureEnabled giúp biểu thức dễ hiểu hơn.

## Truyền biến vào từng lần đánh giá

Có thể đặt root object khi tạo StandardEvaluationContext và đưa các biến vào cùng context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(product);

context.setVariable("minimumPrice", new BigDecimal("50.00"));

Expression expression =
        parser.parseExpression("price >= #minimumPrice");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Cũng có thể truyền root object ở thời điểm gọi getValue:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumPrice", new BigDecimal("50.00"));

Boolean result =
        expression.getValue(context, product, Boolean.class);
~~~

Cách thứ hai phù hợp khi cùng context chứa biến hoặc cấu hình được tái sử dụng với nhiều root object khác nhau. Nếu context chứa dữ liệu riêng của từng request, hãy quản lý vòng đời của nó để không dùng nhầm giá trị từ request trước.

## Biến trong các tích hợp Spring

SpEL được sử dụng trong nhiều điểm tích hợp của Spring, nhưng các biến có sẵn phụ thuộc vào từng integration. Không phải mọi tên biến đều tự động tồn tại trong mọi EvaluationContext.

Ví dụ, trong Spring Cache, biểu thức có thể truy cập các tham số phương thức bằng những tên như **#isbn**, **#p0** hoặc **#a0** tùy cấu hình và khả năng phát hiện tên tham số. Trong các biểu thức khác, framework có thể cung cấp root object và biến theo ngữ cảnh riêng.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(String isbn) {
    // Load book
}
~~~

Ở đây, #isbn tham chiếu tham số của phương thức trong evaluation context do Spring Cache chuẩn bị. Ứng dụng không cần tự gọi setVariable trong phương thức này.

Khi viết SpEL cho annotation, hãy tham khảo danh sách biến mà integration cụ thể cung cấp. Không nên giả định một biến của Spring Cache cũng có mặt trong @Value hoặc trong một EvaluationContext tự tạo.

## Đăng ký function và mối liên hệ với variable

StandardEvaluationContext cũng hỗ trợ đăng ký function để biểu thức có thể gọi bằng cú pháp **#functionName(...)**. Function được đăng ký dưới tên trong context và được biểu thức tham chiếu bằng dấu #, tương tự variable.

Ví dụ khái quát:

~~~java
Method normalizeMethod =
        TextFunctions.class.getDeclaredMethod(
                "normalize", String.class);

context.registerFunction("normalize", normalizeMethod);

Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String normalized =
        expression.getValue(context, String.class);
~~~

Function cần là method phù hợp với cách đăng ký của SpEL, thường là static method. Phần này khác với một variable chứa String hoặc object: variable cung cấp một giá trị, còn function cung cấp hành vi có thể gọi. Chỉ đăng ký function mà biểu thức thực sự cần và có hợp đồng rõ ràng.

## Vòng đời và chia sẻ EvaluationContext

EvaluationContext có thể chứa biến, root object và các cấu hình truy cập. Vì vậy, cần xác định rõ context được tạo một lần để tái sử dụng hay được tạo riêng cho từng lần đánh giá.

Nếu ứng dụng cập nhật biến cho mỗi request nhưng dùng chung một StandardEvaluationContext mutable giữa nhiều luồng, dữ liệu của các request có thể ghi đè lẫn nhau. Một biểu thức có thể đọc biến vừa được request khác thay đổi, dẫn đến kết quả không ổn định.

Một số cách tổ chức an toàn hơn:

- Tạo context riêng cho từng request hoặc lần đánh giá khi biến chứa dữ liệu theo request.
- Chỉ chia sẻ context được cấu hình ổn định và không thay đổi biến trong lúc nhiều luồng đang dùng.
- Đưa dữ liệu riêng của từng lần đánh giá vào root object hoặc context mới.
- Tránh giữ object nhạy cảm hoặc object có vòng đời ngắn trong một context dùng chung lâu dài.

Expression đã parse có thể được tái sử dụng, còn EvaluationContext và giá trị biến cần phù hợp với từng lần đánh giá. Không nên nhầm việc tái sử dụng Expression với việc mọi context đều an toàn để chia sẻ đồng thời.

## Kiểm soát dữ liệu được đưa vào biến

Biến có thể chứa bất kỳ object nào ứng dụng đưa vào context. Nếu biểu thức đến từ nguồn không đáng tin cậy, việc cung cấp một object có nhiều method hoặc tham chiếu đến service có thể mở rộng đáng kể những gì biểu thức có thể làm.

Nếu chỉ cần đọc dữ liệu, hãy đưa vào context DTO nhỏ với các property cần thiết. Tránh cung cấp repository, service, connection hoặc object có khả năng thao tác tài nguyên. Chọn context có bề mặt truy cập giới hạn và chỉ bật method invocation khi có yêu cầu cụ thể.

Biến không tự tạo ra ranh giới bảo mật. Quyền thực tế của biểu thức phụ thuộc root object, property accessor, method resolver, type locator, bean resolver và các khả năng mà EvaluationContext cung cấp.

## Xử lý lỗi khi đọc biến

Lỗi có thể xảy ra khi biểu thức tham chiếu đến biến chưa được cung cấp, truy cập property không tồn tại trên object được lưu trong biến hoặc gọi method không được context hỗ trợ.

Nên tách lỗi parse và lỗi evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#customer.email");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String email =
            expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate expression with current variables", ex);
}
~~~

ParseException chỉ ra chuỗi SpEL không hợp lệ về cú pháp. EvaluationException chỉ ra biểu thức không thể được đánh giá với biến, root object hoặc context hiện tại. Khi log, nên ghi mã biểu thức và tên biến liên quan, tránh ghi toàn bộ giá trị nếu biến chứa dữ liệu cá nhân hoặc bí mật.

## Khi nào nên dùng variable?

Variable phù hợp khi:

- Giá trị thay đổi theo từng request hoặc lần đánh giá.
- Biểu thức cần dùng dữ liệu không thuộc root object.
- Muốn tái sử dụng cùng Expression với các tham số khác nhau.
- Cần đưa một collection, Map hoặc object nhỏ vào biểu thức.
- Muốn tách cấu hình và tham số khỏi chuỗi SpEL cố định.

Nếu dữ liệu đã thuộc về một object nghiệp vụ rõ ràng, truy cập property của root object có thể tự nhiên hơn. Nếu logic cần nhiều thao tác hoặc nhiều bước nghiệp vụ, nên chuyển phần xử lý sang Java thay vì đưa quá nhiều biến vào một biểu thức dài.

## Kết luận

Biến trong SpEL được khai báo trên EvaluationContext, thường bằng **setVariable(name, value)**, và được đọc trong biểu thức bằng cú pháp **#name**. Biến có thể chứa giá trị đơn giản, collection hoặc object; biểu thức có thể dùng chúng trong phép tính, so sánh, property access và collection operation.

Hãy phân biệt variable với property của #root, biến đặc biệt #this và bean reference. Quản lý vòng đời EvaluationContext cẩn thận khi biến chứa dữ liệu theo request, không chia sẻ context mutable giữa các luồng nếu các biến có thể thay đổi và chỉ expose dữ liệu cần thiết cho biểu thức. Cách này giúp biểu thức linh hoạt mà vẫn giữ được nguồn dữ liệu và hành vi đánh giá rõ ràng.
