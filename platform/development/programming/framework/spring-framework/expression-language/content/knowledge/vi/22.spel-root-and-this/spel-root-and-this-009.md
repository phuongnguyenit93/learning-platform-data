# Kiểm thử expression với root object giả lập trong SpEL

## 1. Mục tiêu của việc giả lập root object

Spring Expression Language (SpEL) thường đánh giá property và method dựa trên một root object. Trong ứng dụng, root object có thể là entity, DTO, request model hoặc object nghiệp vụ có nhiều property lồng nhau.

Khi kiểm thử expression, không nhất thiết phải khởi động toàn bộ Spring context hoặc truy cập database để có object thật. Có thể tạo một object giả lập nhỏ, có dữ liệu xác định, rồi truyền object đó trực tiếp vào phương thức Expression.getValue(...).

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.active");

Order order = new Order(new Customer("Lan", true), 150);

Boolean active = expression.getValue(order, Boolean.class);

assertTrue(active);
~~~

Order là root object của lần đánh giá. SpEL đọc property customer, sau đó đọc active trên object Customer được trả về. Bài kiểm thử chỉ cần một object có đúng cấu trúc và dữ liệu mà expression sử dụng.

Giả lập root object giúp kiểm thử tập trung vào hành vi của expression: property nào được đọc, điều kiện nào đúng, collection nào được chọn và kiểu kết quả có đúng hay không.

## 2. Truyền root object trực tiếp vào getValue

Overload getValue(rootObject, expectedResultType) là cách đơn giản để đánh giá expression với một root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.name");

Order order = TestData.orderWithCustomer("Lan");

String name = expression.getValue(order, String.class);

assertEquals("Lan", name);
~~~

Tên property trong expression được phân giải từ root object. Không cần tiền tố # khi đọc property trực tiếp trên root object. Tiền tố # dành cho variable trong evaluation context.

Có thể dùng cùng một Expression với nhiều root object:

~~~java
Expression expression =
        parser.parseExpression("customer.name");

Order firstOrder = TestData.orderWithCustomer("Lan");
Order secondOrder = TestData.orderWithCustomer("Minh");

assertEquals("Lan", expression.getValue(firstOrder, String.class));
assertEquals("Minh", expression.getValue(secondOrder, String.class));
~~~

Cách này hữu ích khi một expression được dùng cho nhiều đối tượng cùng cấu trúc. Parser chỉ cần parse source một lần; mỗi lần getValue nhận root object tương ứng.

## 3. Tạo POJO fixture nhỏ, có dữ liệu xác định

Với phần lớn bài kiểm thử property access, một POJO đơn giản là lựa chọn dễ đọc và ít phụ thuộc nhất. Fixture chỉ cần expose getter cho những property mà expression truy cập.

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
    private final Customer customer;
    private final int total;

    public Order(Customer customer, int total) {
        this.customer = customer;
        this.total = total;
    }

    public Customer getCustomer() {
        return customer;
    }

    public int getTotal() {
        return total;
    }
}
~~~

Có thể tạo factory method để test không phải lặp lại constructor dài:

~~~java
final class TestData {
    private TestData() {
    }

    static Order orderWithCustomer(String name) {
        return new Order(new Customer(name, true), 150);
    }

    static Order inactiveOrder() {
        return new Order(new Customer("Lan", false), 150);
    }
}
~~~

Fixture nên có dữ liệu vừa đủ để thể hiện điều kiện đang kiểm tra. Không cần dựng toàn bộ domain model nếu expression chỉ sử dụng một vài property. Nếu expression truy cập thêm property, hãy bổ sung property đó vào fixture với kiểu và getter tương ứng.

## 4. Kiểm thử property lồng nhau

Khi expression đi qua nhiều cấp object, fixture cần mô phỏng đúng cấu trúc đường dẫn:

~~~java
public class Address {
    private final String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private final Address address;

    public Customer(Address address) {
        this.address = address;
    }

    public Address getAddress() {
        return address;
    }
}

public class Order {
    private final Customer customer;

    public Order(Customer customer) {
        this.customer = customer;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Expression customer.address.city yêu cầu root object có property customer, Customer có property address, và Address có property city.

~~~java
@Test
void readsNestedPropertyFromRootObject() {
    Order order = new Order(
            new Customer(new Address("Da Nang")));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer.address.city");

    String city = expression.getValue(order, String.class);

    assertEquals("Da Nang", city);
}
~~~

Nếu thiếu getter hoặc tên property không khớp, SpEL không thể phân giải đường dẫn. Fixture nên phản ánh đúng API property mà object thật expose, thay vì thêm property giả chỉ để làm expression chạy.

## 5. Dùng StandardEvaluationContext khi cần variables

Một số expression kết hợp property của root object với variables. Khi đó, tạo StandardEvaluationContext và đặt root object vào context:

~~~java
Order order = TestData.orderWithCustomer("Lan");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimumTotal", 100);

Expression expression =
        new SpelExpressionParser().parseExpression(
                "customer.active and total >= #minimumTotal");

Boolean eligible =
        expression.getValue(context, Boolean.class);

assertTrue(eligible);
~~~

Trong expression này:

- customer.active và total được đọc từ root object.
- #minimumTotal được đọc từ variable trong context.
- Kết quả là Boolean.

Có thể thay root object mà không thay expression source bằng cách tạo context mới:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(inactiveOrder);

context.setVariable("minimumTotal", 100);

Boolean eligible = expression.getValue(context, Boolean.class);

assertFalse(eligible);
~~~

Khi test, hãy truyền dữ liệu biến qua setVariable thay vì nối giá trị trực tiếp vào expression source. Điều này làm rõ phần nào là cú pháp và phần nào là dữ liệu đầu vào.

## 6. Phân biệt #root và #this

Trong expression cấp cao nhất, #root tham chiếu root object của lần đánh giá và #this tham chiếu object hiện tại. Khi chưa đi vào collection operation, object hiện tại chính là root object.

~~~java
Order order = TestData.orderWithCustomer("Lan");

Expression rootExpression =
        parser.parseExpression("#root.customer.name");

Expression thisExpression =
        parser.parseExpression("#this.customer.name");

assertEquals("Lan", rootExpression.getValue(order, String.class));
assertEquals("Lan", thisExpression.getValue(order, String.class));
~~~

Trong collection selection hoặc projection, #this thay đổi theo phần tử đang được xử lý, còn #root vẫn là root object ban đầu.

~~~java
public class Item {
    private final String name;
    private final boolean enabled;

    public Item(String name, boolean enabled) {
        this.name = name;
        this.enabled = enabled;
    }

    public String getName() {
        return name;
    }

    public boolean isEnabled() {
        return enabled;
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

Có thể kiểm tra cả root và phần tử hiện tại trong cùng một predicate:

~~~java
Catalog catalog = new Catalog(
        "Lan",
        List.of(new Item("A", true), new Item("B", false)));

Expression expression = parser.parseExpression(
        "items.?[#root.owner == 'Lan' and #this.enabled]");

List<?> enabledItems = expression.getValue(catalog, List.class);

assertEquals(1, enabledItems.size());
assertEquals("A", ((Item) enabledItems.get(0)).getName());
~~~

Ví dụ này làm rõ hai phạm vi: #root.owner luôn đọc owner của Catalog; #this.enabled đọc property enabled của Item hiện tại.

## 7. Kiểm thử selection với root object giả lập

Selection lọc collection được expose từ root object. Fixture nên có cả phần tử khớp và không khớp để kết quả thể hiện rõ predicate:

~~~java
@Test
void selectsEnabledItemsFromRootObject() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", true),
                    new Item("B", false),
                    new Item("C", true)));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("items.?[enabled]");

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(2, result.size());
    assertEquals("A", ((Item) result.get(0)).getName());
    assertEquals("C", ((Item) result.get(1)).getName());
}
~~~

Có thể viết predicate tường minh bằng #this:

~~~java
Expression expression =
        parser.parseExpression("items.?[#this.enabled]");
~~~

Hai cách diễn đạt này đều xét property enabled của phần tử hiện tại. Dùng cách ngắn khi không có khả năng nhầm lẫn; dùng #this khi nó giúp làm rõ ngữ cảnh hoặc khi predicate có thêm tham chiếu #root.

## 8. Kiểm thử projection với root object giả lập

Projection tạo collection mới từ kết quả của một expression áp dụng trên từng phần tử:

~~~java
@Test
void projectsItemNamesFromRootObject() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", true),
                    new Item("B", false)));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("items.![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(List.of("A", "B"), names);
}
~~~

Projection không lọc phần tử. Nó tạo một giá trị kết quả cho từng phần tử của collection đầu vào. Nếu cần vừa lọc vừa chuyển đổi, có thể nối selection với projection:

~~~java
Expression expression =
        parser.parseExpression("items.?[enabled].![name]");
~~~

Trong bài kiểm thử, nên xác nhận cả nội dung và thứ tự kết quả nếu thứ tự là một phần của contract collection. Dùng fixture nhỏ giúp nhìn ngay phần tử nào được giữ lại và property nào được projection.

## 9. Dùng Mockito khi cần mô phỏng collaborator

POJO fixture phù hợp với dữ liệu đơn giản. Mockito hữu ích khi root object là interface hoặc collaborator có hành vi cần được điều khiển, hoặc khi tạo object thật đòi hỏi nhiều dependency không liên quan đến expression.

Ví dụ với interface:

~~~java
public interface OrderView {
    CustomerView getCustomer();
    int getTotal();
}

public interface CustomerView {
    String getName();
    boolean isActive();
}
~~~

Có thể tạo mock và stub getter:

~~~java
@Test
void evaluatesExpressionAgainstMockRoot() {
    OrderView order = mock(OrderView.class);
    CustomerView customer = mock(CustomerView.class);

    when(order.getCustomer()).thenReturn(customer);
    when(order.getTotal()).thenReturn(150);
    when(customer.getName()).thenReturn("Lan");
    when(customer.isActive()).thenReturn(true);

    Expression expression = new SpelExpressionParser()
            .parseExpression("customer.active and total >= 100");

    Boolean result = expression.getValue(order, Boolean.class);

    assertTrue(result);
}
~~~

SpEL đọc property thông qua accessor; với mock Java interface, getter được stub cung cấp giá trị cho property tương ứng. Hãy stub đúng getter mà expression cần đọc.

Không cần dùng Mockito chỉ để thay một DTO đơn giản có constructor rõ ràng. Object thật hoặc fixture nhỏ thường khiến test dễ hiểu hơn vì hành vi property giống object ứng dụng đang sử dụng.

## 10. Kiểm thử null và property tùy chọn

Root object giả lập nên bao gồm các trường hợp property lồng nhau có thể null nếu expression cần hỗ trợ chúng.

~~~java
@Test
void returnsDefaultWhenNestedPropertyIsNull() {
    Order order = new Order(null);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer?.name ?: 'Guest'");

    String name = expression.getValue(order, String.class);

    assertEquals("Guest", name);
}
~~~

Ở đây customer?.name trả về null khi customer null; Elvis operator cung cấp Guest. Nếu ứng dụng cần phân biệt object null với property rỗng, hãy tạo các fixture riêng cho từng trạng thái.

Ví dụ kiểm tra cả hai trường hợp:

~~~java
@Test
void distinguishesNullAndEmptyName() {
    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer?.name ?: 'Guest'");

    Order missingCustomer = new Order(null);
    Order emptyName = new Order(new Customer("", true));

    assertEquals("Guest",
            expression.getValue(missingCustomer, String.class));
    assertEquals("Guest",
            expression.getValue(emptyName, String.class));
}
~~~

Elvis trong SpEL xử lý null và chuỗi rỗng. Nếu nghiệp vụ cần giữ chuỗi rỗng hoặc chỉ thay thế null, hãy dùng điều kiện == null thay vì Elvis.

## 11. Kiểm thử kiểu kết quả và lỗi evaluation

Khi có thể, yêu cầu kiểu kết quả rõ ràng bằng overload getValue(rootObject, TargetType.class):

~~~java
Expression expression =
        new SpelExpressionParser().parseExpression("total >= 100");

Boolean result = expression.getValue(order, Boolean.class);
~~~

Điều này giúp thể hiện contract mà code ứng dụng mong đợi. Nếu expression không thể tạo ra giá trị chuyển đổi được sang kiểu đích, SpEL sẽ phát sinh lỗi evaluation.

Parse expression và evaluate expression là hai thao tác riêng:

~~~java
ExpressionParser parser = new SpelExpressionParser();

// Parse: kiểm tra cú pháp và tạo Expression.
Expression expression = parser.parseExpression("customer.active");

// Evaluate: đọc property từ root object.
Boolean active = expression.getValue(order, Boolean.class);
~~~

Có thể kiểm tra parse error riêng với expression source không hợp lệ:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("customer."));
~~~

Và kiểm tra evaluation error với root object không cung cấp property mà expression yêu cầu:

~~~java
Expression expression = parser.parseExpression("unknownProperty");

assertThrows(
        EvaluationException.class,
        () -> expression.getValue(order));
~~~

Trong test thực tế, hãy dùng loại exception phù hợp với API và phiên bản Spring đang chạy. Mục tiêu là xác định rõ lỗi phát sinh khi parse hay khi truy cập dữ liệu lúc evaluate.

## 12. Kiểm thử cùng expression với nhiều root object

Nếu expression được tái sử dụng cho nhiều đối tượng, hãy kiểm tra nhiều root object khác nhau thay vì chỉ test một trường hợp:

~~~java
@ParameterizedTest
@MethodSource("orders")
void evaluatesEachOrder(Order order, boolean expected) {
    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer.active and total >= 100");

    Boolean actual = expression.getValue(order, Boolean.class);

    assertEquals(expected, actual);
}

static Stream<Arguments> orders() {
    return Stream.of(
            Arguments.of(
                    new Order(new Customer("Lan", true), 150),
                    true),
            Arguments.of(
                    new Order(new Customer("Minh", false), 150),
                    false),
            Arguments.of(
                    new Order(new Customer("An", true), 50),
                    false));
}
~~~

Mỗi case thể hiện một lý do khác nhau khiến điều kiện đúng hoặc sai. Khi expression source giống nhau, có thể parse một lần ở field hoặc trong setup của test rồi evaluate trên từng root object.

Test nhiều root object giúp xác nhận expression không phụ thuộc nhầm vào một fixture cụ thể và kết quả thay đổi theo dữ liệu đầu vào.

## 13. Các lỗi thường gặp khi giả lập root object

**Thiếu getter hoặc sai tên property**

Expression customer.name cần root object expose customer và object Customer expose name. Field tồn tại nhưng không được accessor cho phép đọc không bảo đảm expression sẽ truy cập được.

**Nhầm root property với variable**

customer.name là property path từ root object. #customer.name là variable customer trong evaluation context. Nếu test chỉ truyền root object mà không tạo variable, expression thứ hai sẽ không đọc property root như mong muốn.

**Nhầm #this với #root trong collection operation**

Trong selection/projection, #this là phần tử hiện tại; #root vẫn là root object ban đầu. Dùng sai một trong hai có thể khiến predicate đọc nhầm cấp object.

**Mock không stub getter cần thiết**

Một mock thường trả về giá trị mặc định nếu getter chưa được stub. Điều đó có thể khiến expression cho kết quả null, false hoặc zero và làm test không phản ánh dữ liệu dự kiến.

**Fixture quá lớn**

Dựng toàn bộ object graph của ứng dụng làm test khó đọc và khó sửa. Chỉ tạo các property expression thực sự sử dụng.

**Chỉ kiểm tra số lượng collection**

Nếu selection trả về đúng số phần tử nhưng sai phần tử, assertion chỉ kiểm tra size() có thể bỏ sót. Khi thứ tự và nội dung quan trọng, hãy xác nhận các giá trị cụ thể.

**Trộn lỗi parse với lỗi evaluate**

Parse expression một lần ở bước riêng và evaluate trên root object sau đó. Điều này giúp biết lỗi do cú pháp hay do fixture không đáp ứng property path.

## 14. Ví dụ tổng hợp với JUnit 5

Ví dụ sau tạo root object giả lập, đánh giá property, dùng #root trong selection và kiểm tra kết quả:

~~~java
class SpelRootObjectTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsRootPropertiesAndFiltersNestedItems() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", true),
                        new Item("B", false),
                        new Item("C", true)));

        Expression ownerExpression =
                parser.parseExpression("#root.owner");

        Expression enabledExpression =
                parser.parseExpression(
                        "items.?[#root.owner == 'Lan' and #this.enabled]");

        String owner =
                ownerExpression.getValue(catalog, String.class);

        List<?> enabledItems =
                enabledExpression.getValue(catalog, List.class);

        assertEquals("Lan", owner);
        assertEquals(2, enabledItems.size());
        assertEquals("A", ((Item) enabledItems.get(0)).getName());
        assertEquals("C", ((Item) enabledItems.get(1)).getName());
    }
}
~~~

Các fixture Catalog và Item là những class đơn giản có getter cho property mà expression sử dụng. Test không cần Spring application context vì parser và root object đã đủ để đánh giá biểu thức.

Nếu expression cần variables, tạo StandardEvaluationContext từ Catalog, đặt variables bằng setVariable, rồi gọi getValue(context, ResultType.class). Cách này kiểm tra cả hai nguồn dữ liệu mà không làm thay đổi expression source.

## 15. Ghi nhớ

- Truyền root object trực tiếp bằng expression.getValue(rootObject, ResultType.class) khi chỉ cần property của root.
- Dùng StandardEvaluationContext(rootObject) khi expression còn cần variables hoặc cấu hình evaluation context.
- Tạo POJO fixture nhỏ với getter và dữ liệu xác định cho các property expression sử dụng.
- Dùng Mockito khi cần mô phỏng interface/collaborator; không mock DTO đơn giản nếu object thật dễ tạo.
- #root tham chiếu root object ban đầu; #this là object hiện tại và thay đổi bên trong collection operation.
- Kiểm thử property lồng nhau, collection selection/projection, null và kiểu kết quả theo contract.
- Parse và evaluate riêng để phân biệt lỗi cú pháp với lỗi dữ liệu lúc chạy.
- Dùng cùng một Expression với nhiều root object để kiểm tra các nhánh dữ liệu khác nhau.
- Assertion nên xác nhận nội dung và thứ tự khi chúng là một phần kết quả mong đợi, không chỉ xác nhận số lượng.
