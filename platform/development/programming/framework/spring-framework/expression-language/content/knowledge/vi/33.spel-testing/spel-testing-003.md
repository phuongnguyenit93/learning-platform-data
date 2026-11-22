# Kiểm thử root object và variables trong SpEL

## 1. Hai nguồn dữ liệu trong một expression

Spring Expression Language (SpEL) đánh giá expression trong một EvaluationContext. Context cung cấp root object và các variable mà biểu thức có thể tham chiếu.

Hai nguồn dữ liệu này có cú pháp khác nhau:

- Property trên root object được truy cập trực tiếp bằng tên, ví dụ customer.name hoặc total.
- Variable được tham chiếu bằng tiền tố #, ví dụ #minimumTotal hoặc #currentUser.
- #root tham chiếu root object của lần đánh giá.
- #this tham chiếu object hiện tại; trong expression thông thường nó là root object, còn trong collection selection/projection nó là phần tử đang được xử lý.

Một test tốt nên xác nhận rõ expression lấy dữ liệu từ nguồn nào. Nếu nhầm property root với variable, expression có thể trả về null, dùng nhầm dữ liệu hoặc thất bại khi evaluate.

## 2. Chuẩn bị root object fixture nhỏ

Dùng POJO fixture có getter cho những property mà expression cần đọc. Không cần khởi động toàn bộ Spring ApplicationContext nếu mục tiêu chỉ là kiểm tra SpEL parser và evaluation.

~~~java
public class Customer {
    private final String name;
    private final boolean active;

    public Customer(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
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
~~~

Fixture có dữ liệu xác định giúp test dễ đọc và có thể lặp lại. Nếu expression chỉ đọc code và total, không cần dựng toàn bộ entity graph của ứng dụng. Nếu expression đọc customer.name, fixture phải có customer và getter name tương ứng.

## 3. Kiểm thử root object trực tiếp

Khi chỉ cần property của root object, có thể truyền object trực tiếp vào overload getValue(rootObject, resultType):

~~~java
@Test
void readsPropertyFromRootObject() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("customer.name");

    String name = expression.getValue(order, String.class);

    assertEquals("Lan", name);
}
~~~

Ở đây order là root object. SpEL đọc customer từ order rồi đọc name từ Customer. Không cần tạo StandardEvaluationContext riêng khi expression chỉ cần root object và không cần variables hoặc resolver tùy chỉnh.

Có thể kiểm tra nhiều property bằng các expression riêng:

~~~java
Expression codeExpression = parser.parseExpression("code");
Expression totalExpression = parser.parseExpression("total");

assertEquals("ORD-1001",
        codeExpression.getValue(order, String.class));
assertEquals(Integer.valueOf(150),
        totalExpression.getValue(order, Integer.class));
~~~

Truyền result type vào getValue giúp thể hiện kiểu mà code gọi mong đợi. Nếu expression không trả về giá trị tương thích, SpEL có thể phát sinh lỗi chuyển đổi hoặc evaluation.

## 4. Tạo StandardEvaluationContext với root object

Khi expression cần cả property của root object và variables, hãy đặt root object vào StandardEvaluationContext:

~~~java
@Test
void evaluatesRootPropertiesAndVariablesTogether() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", 100);

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "customer.active and total >= #minimumTotal");

    Boolean eligible = expression.getValue(context, Boolean.class);

    assertTrue(eligible);
}
~~~

Trong expression này:

- customer.active được đọc từ root object.
- total được đọc từ root object.
- #minimumTotal được đọc từ variable trong context.
- Kết quả cuối cùng là Boolean.

Cách viết này giúp test kiểm tra cả hai nguồn dữ liệu trong cùng một lần evaluate. Nó cũng phản ánh cách ứng dụng thường dùng SpEL khi kết hợp object nghiệp vụ với tham số cấu hình hoặc dữ liệu bổ sung.

## 5. Phân biệt property root với variable cùng tên

Property của root object và variable có thể có tên giống nhau, nhưng được tham chiếu theo cú pháp khác nhau. Property dùng tên trực tiếp; variable dùng tiền tố #.

~~~java
public class SearchRequest {
    private final String category;

    public SearchRequest(String category) {
        this.category = category;
    }

    public String getCategory() {
        return category;
    }
}
~~~

Test dưới đây đặt variable category khác với property category của root:

~~~java
@Test
void distinguishesRootPropertyFromVariable() {
    SearchRequest request = new SearchRequest("books");

    StandardEvaluationContext context =
            new StandardEvaluationContext(request);
    context.setVariable("category", "music");

    Expression rootExpression =
            new SpelExpressionParser().parseExpression("category");
    Expression variableExpression =
            new SpelExpressionParser().parseExpression("#category");

    assertEquals("books",
            rootExpression.getValue(context, String.class));
    assertEquals("music",
            variableExpression.getValue(context, String.class));
}
~~~

Test này bảo đảm expression không vô tình đọc nhầm nguồn. Khi tên biến và property dễ gây nhầm lẫn, hãy đặt tên variable có ý nghĩa riêng, chẳng hạn minimumTotal, currentUser hoặc allowedRegions.

## 6. Kiểm thử #root và #this

Ở cấp cao nhất, #root và #this cùng tham chiếu root object:

~~~java
@Test
void rootAndThisReferToRootOutsideCollectionOperations() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    ExpressionParser parser = new SpelExpressionParser();

    Expression rootExpression =
            parser.parseExpression("#root.customer.name");
    Expression thisExpression =
            parser.parseExpression("#this.customer.name");

    assertEquals("Lan",
            rootExpression.getValue(order, String.class));
    assertEquals("Lan",
            thisExpression.getValue(order, String.class));
}
~~~

Trong collection operation, #this thay đổi theo phần tử hiện tại. #root vẫn tham chiếu object ban đầu của lần đánh giá.

~~~java
public class Item {
    private final String name;
    private final int price;

    public Item(String name, int price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public int getPrice() {
        return price;
    }
}

public class Catalog {
    private final String owner;
    private final List<Item> items;

    public Catalog(String owner, List<Item> items) {
        this.owner = owner;
        this.items = items;
    }

    public String getOwner() {
        return owner;
    }

    public List<Item> getItems() {
        return items;
    }
}
~~~

Ví dụ test selection dùng cả hai phạm vi:

~~~java
@Test
void distinguishesRootAndCurrentItemInSelection() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", 50),
                    new Item("B", 150),
                    new Item("C", 250)));

    StandardEvaluationContext context =
            new StandardEvaluationContext(catalog);
    context.setVariable("ownerFilter", "Lan");
    context.setVariable("minimumPrice", 100);

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "items.?[#root.owner == #ownerFilter "
                    + "and #this.price >= #minimumPrice]");

    List<?> selected = expression.getValue(context, List.class);

    assertEquals(2, selected.size());
    assertEquals("B", ((Item) selected.get(0)).getName());
    assertEquals("C", ((Item) selected.get(1)).getName());
}
~~~

Trong predicate, #root.owner luôn đọc owner của Catalog. #this.price đọc price của Item đang được xét. #ownerFilter và #minimumPrice là variables của context.

## 7. Dùng variable làm điều kiện selection

Variables thường đại diện cho tham số tìm kiếm, ngưỡng hoặc cờ cấu hình. Có thể dùng chúng trong selection để tái sử dụng cùng expression với nhiều đầu vào:

~~~java
Expression expression =
        new SpelExpressionParser()
                .parseExpression("items.?[price >= #minimumPrice]");

Catalog catalog = new Catalog(
        "Lan",
        List.of(
                new Item("A", 50),
                new Item("B", 150),
                new Item("C", 250)));

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("minimumPrice", 100);
List<?> firstResult = expression.getValue(context, List.class);

context.setVariable("minimumPrice", 200);
List<?> secondResult = expression.getValue(context, List.class);

assertEquals(2, firstResult.size());
assertEquals(1, secondResult.size());
assertEquals("C", ((Item) secondResult.get(0)).getName());
~~~

Expression source không thay đổi. Giá trị minimumPrice được lấy từ context tại thời điểm evaluate. Điều này giúp test cùng một quy tắc với nhiều bộ dữ liệu mà không phải nối giá trị vào chuỗi expression.

Nếu cần xác nhận chính xác phần tử được chọn, hãy assert cả nội dung và thứ tự thay vì chỉ kiểm tra size.

## 8. Variable có thể là object hoặc collection

Variable không chỉ chứa String hoặc số. Nó có thể tham chiếu object, collection hoặc một kiểu miền nghiệp vụ khác.

~~~java
@Test
void readsPropertiesFromObjectVariable() {
    Customer customer = new Customer("Minh", true);

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("currentCustomer", customer);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#currentCustomer.name");

    String name = expression.getValue(context, String.class);

    assertEquals("Minh", name);
}
~~~

Có thể truyền collection làm variable:

~~~java
@Test
void selectsFromCollectionVariable() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable(
            "items",
            List.of(
                    new Item("A", 50),
                    new Item("B", 150)));

    context.setVariable("minimumPrice", 100);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#items.?[price >= #minimumPrice]");

    List<?> result = expression.getValue(context, List.class);

    assertEquals(1, result.size());
    assertEquals("B", ((Item) result.get(0)).getName());
}
~~~

Trong trường hợp này #items là collection variable. Bên trong selection, #this là từng Item; #minimumPrice vẫn là variable của context.

## 9. Kiểm thử method arguments và variables

Khi expression được gọi từ code Java, có thể đưa các tham số đầu vào vào context bằng setVariable. Nên dùng tên mô tả ý nghĩa thay vì ghép giá trị trực tiếp vào expression source.

~~~java
@Test
void usesVariablesAsExpressionInputs() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("subtotal", 120);
    context.setVariable("discountRate", 0.10);

    Expression expression = new SpelExpressionParser()
            .parseExpression("#subtotal * (1 - #discountRate)");

    Double finalAmount = expression.getValue(context, Double.class);

    assertEquals(108.0, finalAmount);
}
~~~

Trong một method service, có thể tạo context cho từng lần xử lý:

~~~java
public boolean isAllowed(Order order, int minimumTotal) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    Expression expression =
            parser.parseExpression("total >= #minimumTotal");

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class));
}
~~~

Test nên xác nhận variable được truyền đúng và kết quả thay đổi theo giá trị đầu vào. Với logic đơn giản, Java condition có thể dễ đọc hơn SpEL; ví dụ này phù hợp khi expression là một phần của cấu hình hoặc được lưu để đánh giá nhiều lần.

## 10. Kiểm thử nhiều bộ variables

Có thể dùng parameterized test để xác nhận cùng một expression hoạt động với nhiều bộ variables:

~~~java
@ParameterizedTest
@CsvSource({
        "100, true",
        "150, true",
        "151, false"
})
void checksOrderTotalAgainstVariable(
        int minimumTotal,
        boolean expected) {

    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);

    Expression expression = new SpelExpressionParser()
            .parseExpression("total >= #minimumTotal");

    Boolean actual = expression.getValue(context, Boolean.class);

    assertEquals(expected, actual);
}
~~~

Mỗi test case tạo context riêng và đặt giá trị variable tương ứng. Cách này giúp kết quả không phụ thuộc vào lần chạy trước và làm rõ ranh giới giữa expression source với dữ liệu đầu vào.

Nếu test có nhiều variables, dùng MethodSource với một object test case có tên field rõ ràng thay vì một danh sách tham số dài khó đọc.

## 11. Kiểm thử variable null hoặc không được cung cấp

Một variable có thể không có giá trị tại thời điểm evaluate. Nếu expression sử dụng variable đó, hãy kiểm tra rõ hành vi mong đợi: trả về null, chọn default, hoặc phát sinh lỗi khi thao tác tiếp theo không thể thực hiện.

Ví dụ dùng Elvis để chọn giá trị mặc định:

~~~java
@Test
void usesDefaultWhenVariableHasNoValue() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression = new SpelExpressionParser()
            .parseExpression("#displayName ?: 'Guest'");

    String result = expression.getValue(context, String.class);

    assertEquals("Guest", result);
}
~~~

Có thể kiểm tra variable có giá trị bình thường:

~~~java
context.setVariable("displayName", "Lan");

assertEquals(
        "Lan",
        expression.getValue(context, String.class));
~~~

Elvis trong SpEL dùng giá trị mặc định khi vế trái là null hoặc chuỗi rỗng. Nếu nghiệp vụ chỉ muốn thay thế null, hãy dùng điều kiện tường minh. Với variable bắt buộc, có thể tốt hơn nếu test xác nhận lỗi cấu hình thay vì âm thầm dùng default.

Không suy luận nguồn gốc của null chỉ từ kết quả expression. Nếu cần phân biệt “không truyền variable” với “người gọi chủ động truyền trạng thái không có dữ liệu”, hãy thêm một variable presence hoặc dùng một request object có trạng thái rõ ràng.

## 12. Kiểm thử property lồng nhau và null-safe access

Root object có thể chứa object trung gian null. Khi expression cần hỗ trợ trường hợp này, dùng null-safe navigation và kiểm tra cả dữ liệu có đủ lẫn dữ liệu thiếu:

~~~java
@Test
void handlesNullableNestedRootProperty() {
    Expression expression = new SpelExpressionParser()
            .parseExpression("customer?.name ?: 'Guest'");

    Order withoutCustomer =
            new Order("ORD-1", null, 100);

    Order withCustomer =
            new Order("ORD-2", new Customer("Lan", true), 100);

    assertEquals(
            "Guest",
            expression.getValue(withoutCustomer, String.class));

    assertEquals(
            "Lan",
            expression.getValue(withCustomer, String.class));
}
~~~

Nếu expression đi qua nhiều cấp object, bảo vệ từng chặng có thể null:

~~~text
customer?.address?.city ?: 'Unknown'
~~~

Null-safe operator chỉ bảo vệ thao tác ngay sau nó. Test nên tạo fixture có null ở từng cấp có thể null để xác nhận expression hoạt động đúng theo contract.

## 13. Phân biệt lỗi parse với lỗi evaluate

Parser tạo Expression từ source. Evaluation sử dụng root object và variables để thực hiện expression. Hai giai đoạn có thể thất bại vì những nguyên nhân khác nhau.

Parse error xảy ra khi source không đúng cú pháp:

~~~java
@Test
void rejectsInvalidExpressionSyntax() {
    ExpressionParser parser = new SpelExpressionParser();

    assertThrows(
            ParseException.class,
            () -> parser.parseExpression("customer."));
}
~~~

Evaluation error xảy ra khi expression hợp lệ nhưng root object hoặc context không cung cấp property, method hay kiểu dữ liệu cần thiết:

~~~java
@Test
void reportsMissingRootPropertyDuringEvaluation() {
    Order order = new Order(
            "ORD-1",
            new Customer("Lan", true),
            100);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("unknownProperty");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(order));
}
~~~

Trong test thực tế, có thể kiểm tra exception cụ thể hơn nếu ứng dụng phụ thuộc vào loại lỗi. Tránh phụ thuộc vào toàn bộ message text vì nội dung message có thể thay đổi theo phiên bản hoặc locale.

## 14. Kiểm tra kiểu kết quả

Nếu expression được kỳ vọng trả về Boolean, String hoặc một kiểu cụ thể, dùng overload getValue với result type để contract được thể hiện rõ:

~~~java
Expression expression =
        new SpelExpressionParser()
                .parseExpression("total >= #minimumTotal");

Boolean result = expression.getValue(context, Boolean.class);
~~~

Test không chỉ nên kiểm tra kết quả true/false mà còn nên xác nhận kiểu trả về phù hợp với code sử dụng expression. Nếu expression có thể trả về null, đừng unbox Boolean trực tiếp thành boolean mà chưa xử lý null.

Với expression trả về collection, có thể yêu cầu List.class rồi kiểm tra phần tử:

~~~java
List<?> selected = expression.getValue(context, List.class);
~~~

Nếu ứng dụng cần generic element type cụ thể, hãy kiểm tra nội dung và kiểu phần tử trong test vì Class<List> không biểu diễn đầy đủ kiểu generic của các phần tử.

## 15. Tái sử dụng Expression nhưng tạo context phù hợp

Có thể parse một expression một lần và đánh giá nó với nhiều context khác nhau:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("total >= #minimumTotal");

Order smallOrder = new Order(
        "ORD-1",
        new Customer("Lan", true),
        80);

Order largeOrder = new Order(
        "ORD-2",
        new Customer("Minh", true),
        180);

StandardEvaluationContext firstContext =
        new StandardEvaluationContext(smallOrder);
firstContext.setVariable("minimumTotal", 100);

StandardEvaluationContext secondContext =
        new StandardEvaluationContext(largeOrder);
secondContext.setVariable("minimumTotal", 100);

assertFalse(expression.getValue(firstContext, Boolean.class));
assertTrue(expression.getValue(secondContext, Boolean.class));
~~~

Expression source không thay đổi, nhưng mỗi context có root object và variables riêng. Cách này làm test độc lập và tránh việc một test case vô tình sử dụng dữ liệu của case trước.

Nếu thay root object trong cùng một context bằng setRootObject, hãy cập nhật rõ ràng trước khi evaluate. Với test suite, tạo context mới cho mỗi case thường dễ hiểu hơn.

## 16. Tránh chia sẻ mutable EvaluationContext giữa test hoặc request

StandardEvaluationContext chứa root object và variables có thể thay đổi. Nếu nhiều test hoặc request cùng sửa một context, dữ liệu có thể ảnh hưởng chéo.

Các nguyên tắc thực tế:

- Tạo context mới cho mỗi test case khi root object hoặc variables khác nhau.
- Không giữ variable theo trạng thái của request trước.
- Không chia sẻ context mutable giữa các request đồng thời nếu không có thiết kế đồng bộ phù hợp.
- Có thể tái sử dụng Expression đã parse nếu source không đổi, nhưng truyền context phù hợp cho từng lần evaluate.
- Dùng tên variable có ý nghĩa và đặt tất cả input cần thiết trước khi evaluate.

Việc tách Expression khỏi EvaluationContext giúp test rõ ràng: expression mô tả quy tắc, context chứa dữ liệu của một lần đánh giá.

## 17. Khi nào dùng POJO và khi nào dùng Mockito?

POJO fixture thường phù hợp khi root object chỉ là DTO hoặc domain object có constructor đơn giản. Nó cung cấp getter thật và giúp test gần với cách SpEL đọc property trong ứng dụng.

Mockito hữu ích khi root object là interface hoặc collaborator có nhiều dependency, và test cần điều khiển giá trị getter:

~~~java
OrderView order = mock(OrderView.class);
CustomerView customer = mock(CustomerView.class);

when(order.getCustomer()).thenReturn(customer);
when(customer.getName()).thenReturn("Lan");

Expression expression =
        new SpelExpressionParser()
                .parseExpression("customer.name");

assertEquals("Lan", expression.getValue(order, String.class));
~~~

Hãy stub mọi getter mà expression truy cập. Getter chưa được stub thường trả về giá trị mặc định của mock và có thể làm test phản ánh dữ liệu sai.

Không cần mock DTO đơn giản chỉ để kiểm tra property access. Object thật thường dễ đọc hơn và tránh phụ thuộc vào hành vi mặc định của mock.

## 18. Kiểm thử context tùy chỉnh khi cần

Nếu ứng dụng sử dụng PropertyAccessor, BeanResolver hoặc TypeConverter riêng, test phải cấu hình đúng thành phần đó. Chỉ tạo StandardEvaluationContext với root object và variables sẽ không tự cung cấp resolver tùy chỉnh của ứng dụng.

Ví dụ gắn TypeConverter:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

Nếu expression tham chiếu bean bằng cú pháp @beanName, context cần BeanResolver phù hợp. Nếu expression truy cập property theo quy tắc riêng, context cần PropertyAccessor tương ứng.

Hãy kiểm thử context theo đúng cấu hình mà ứng dụng sử dụng. Một unit test chỉ kiểm tra root object và variables không chứng minh custom resolver hoặc conversion service đã được nối đúng.

## 19. Ví dụ tổng hợp với JUnit 5

Ví dụ sau kiểm tra root property, variable, #root và #this trong collection selection:

~~~java
class SpelRootAndVariablesTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void evaluatesRootAndVariablesTogether() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", 50),
                        new Item("B", 150),
                        new Item("C", 250)));

        StandardEvaluationContext context =
                new StandardEvaluationContext(catalog);
        context.setVariable("ownerFilter", "Lan");
        context.setVariable("minimumPrice", 100);

        Expression expression = parser.parseExpression(
                "items.?[#root.owner == #ownerFilter "
                + "and #this.price >= #minimumPrice].![name]");

        List<?> names = expression.getValue(context, List.class);

        assertEquals(List.of("B", "C"), names);
    }

    @Test
    void evaluatesSameExpressionWithDifferentVariableValues() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", 50),
                        new Item("B", 150),
                        new Item("C", 250)));

        Expression expression =
                parser.parseExpression("items.?[price >= #minimumPrice]");

        StandardEvaluationContext firstContext =
                new StandardEvaluationContext(catalog);
        firstContext.setVariable("minimumPrice", 100);

        StandardEvaluationContext secondContext =
                new StandardEvaluationContext(catalog);
        secondContext.setVariable("minimumPrice", 200);

        assertEquals(
                2,
                expression.getValue(firstContext, List.class).size());
        assertEquals(
                1,
                expression.getValue(secondContext, List.class).size());
    }
}
~~~

Fixture Catalog và Item cần có getter owner, items, name và price như các ví dụ trước. Hai test xác nhận context cung cấp dữ liệu cho expression và cùng một expression có thể được đánh giá với các variable khác nhau.

## 20. Ma trận kiểm thử đề xuất

| Trường hợp | Root object | Variables | Điều cần xác nhận |
|---|---|---|---|
| Root property | Có | Không | Property được đọc từ đúng root |
| Variable đơn | Không bắt buộc | Có | #name trả về đúng giá trị |
| Root và variable | Có | Có | Hai nguồn dữ liệu được phân biệt |
| Cùng tên property/variable | Có | Có | Tên trực tiếp và #name không bị nhầm |
| #root và #this | Có collection | Có thể có | Phạm vi object đúng ở từng cấp |
| Variable là object | Không bắt buộc | Object variable | Property của variable được đọc đúng |
| Variable là collection | Không bắt buộc | Collection variable | Selection/projection dùng đúng phần tử |
| Variable thiếu hoặc null | Có thể có | Thiếu/null | Default hoặc lỗi theo contract |
| Root property lồng nhau null | Có | Không bắt buộc | Null-safe navigation đúng |
| Root object khác nhau | Nhiều object | Có thể khác | Expression không phụ thuộc fixture cụ thể |
| Context khác nhau | Có | Nhiều bộ variable | Không có dữ liệu rò rỉ giữa test |
| Context có resolver riêng | Có | Có thể có | Accessor, resolver và converter được cấu hình đúng |

Không phải mọi expression đều cần toàn bộ ma trận. Chọn các trường hợp phù hợp với property, variables và khả năng của context mà ứng dụng thực sự sử dụng.

## 21. Lỗi thường gặp

**Dùng # cho property của root object**

customer.name là property path từ root. #customer.name là variable customer trong context.

**Quên đặt root object vào context**

Nếu dùng getValue(context), hãy tạo context với root object hoặc gọi setRootObject trước khi evaluate.

**Không đặt variable cần thiết**

Expression tham chiếu #minimumTotal nhưng test không gọi setVariable. Hãy cung cấp variable hoặc kiểm tra rõ hành vi khi nó thiếu.

**Nhầm #root với #this**

Trong collection operation, #this là phần tử hiện tại; #root vẫn là root object ban đầu.

**Dùng chung context giữa test case**

Variables và root object mutable có thể làm kết quả phụ thuộc thứ tự chạy. Tạo context riêng cho từng case.

**Chỉ kiểm tra size của selection**

Collection có đúng số lượng nhưng sai phần tử vẫn có thể làm test pass. Kiểm tra nội dung và thứ tự khi chúng thuộc contract.

**Mock không stub getter**

Property chưa được stub có thể trả về null, false hoặc zero. Stub đầy đủ các getter mà expression sử dụng.

**Cho rằng parser test chứng minh annotation context**

Parser test xác nhận SpEL expression cơ bản. Nếu expression được dùng trong @Value, cache, security hoặc module khác, cần integration test tại đúng điểm tích hợp để xác nhận root object và variables mà module cung cấp.

## 22. Ghi nhớ

- Root object cung cấp property được truy cập trực tiếp bằng tên.
- Variables được tham chiếu bằng tiền tố # và được đặt trong EvaluationContext.
- Dùng getValue(rootObject, resultType) cho expression chỉ cần root object.
- Dùng StandardEvaluationContext(rootObject) khi expression cần cả root object và variables.
- #root giữ tham chiếu root object; #this là object hiện tại và thay đổi trong collection operation.
- Kiểm tra riêng property root và variable, kể cả khi chúng có tên giống nhau.
- Dùng POJO fixture nhỏ cho object đơn giản; dùng Mockito khi cần mô phỏng interface/collaborator.
- Parse và evaluate là hai bước riêng; test riêng lỗi cú pháp và lỗi dữ liệu runtime.
- Tạo context riêng cho từng test case hoặc lần đánh giá có dữ liệu khác nhau.
- Tái sử dụng Expression đã parse được, nhưng không chia sẻ context mutable thiếu kiểm soát.
- Cấu hình PropertyAccessor, BeanResolver và TypeConverter khi expression phụ thuộc chúng.
- Kiểm thử qua annotation/module thật nếu cần xác nhận context do Spring integration cung cấp.
