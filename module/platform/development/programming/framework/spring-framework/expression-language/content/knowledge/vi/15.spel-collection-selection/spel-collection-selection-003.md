# Biến #this trong ngữ cảnh selection

Trong Spring Expression Language (SpEL), **#this** là biến đặc biệt tham chiếu đến đối tượng đang được đánh giá tại thời điểm hiện tại. Khi dùng collection selection, SpEL đánh giá một biểu thức điều kiện trên từng phần tử của collection. Trong mỗi lần đánh giá điều kiện, **#this trỏ đến phần tử hiện tại**.

Điểm này giúp biểu thức mô tả rõ phần tử nào đang được kiểm tra, nhất là khi collection chứa object có nhiều thuộc tính hoặc khi selection được lồng nhau. Cần phân biệt **#this** với **#root**: #root luôn tham chiếu đến root object ban đầu của toàn bộ lần đánh giá, còn #this thay đổi theo ngữ cảnh đánh giá hiện tại.

## Selection collection hoạt động như thế nào?

SpEL hỗ trợ selection để lọc các phần tử của collection theo một điều kiện. Cú pháp cơ bản là:

~~~text
collection.?[selectionExpression]
~~~

SpEL duyệt các phần tử, đánh giá selectionExpression cho từng phần tử và giữ lại những phần tử có kết quả điều kiện là true. Trong lúc đánh giá predicate, phần tử đang được xét trở thành đối tượng hiện tại và có thể được tham chiếu bằng **#this**.

Ví dụ, lọc các số lớn hơn 10:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable(
        "numbers",
        List.of(4, 12, 7, 18, 25));

Expression expression =
        parser.parseExpression("#numbers.?[#this > 10]");

List<?> result =
        expression.getValue(context, List.class);
~~~

Kết quả chứa các giá trị **12, 18, 25**. Mỗi lần predicate được đánh giá, #this lần lượt là 4, 12, 7, 18 và 25. Chỉ các phần tử làm điều kiện trả về true mới được giữ lại.

Với phần tử đơn giản như số nguyên, có thể viết điều kiện trực tiếp mà không cần #this. Viết rõ **#this > 10** giúp nhận ra rằng toán tử đang so sánh phần tử hiện tại của collection.

## #this trỏ đến phần tử hiện tại trong predicate

Khi collection chứa object, #this cho phép truy cập các thuộc tính của object đang được kiểm tra:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;
    private final boolean active;

    public Product(String name, BigDecimal price, boolean active) {
        this.name = name;
        this.price = price;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

~~~java
List<Product> products = List.of(
        new Product("Keyboard", new BigDecimal("80.00"), true),
        new Product("Monitor", new BigDecimal("250.00"), true),
        new Product("Mouse", new BigDecimal("25.00"), false));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("products", products);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression(
                "#products.?[#this.active and #this.price >= 50]");

List<?> available =
        expression.getValue(context, List.class);
~~~

Predicate kiểm tra hai điều kiện trên cùng một Product hiện tại:

- **#this.active** yêu cầu sản phẩm đang hoạt động.
- **#this.price >= 50** yêu cầu giá ít nhất bằng 50.

Kết quả giữ lại Keyboard và Monitor. Với Mouse, điều kiện active là false nên phần tử không được chọn, dù giá của nó không ảnh hưởng đến kết quả cuối cùng.

Trong predicate selection, SpEL cũng cho phép truy cập property trực tiếp mà không cần viết #this:

~~~text
#products.?[active and price >= 50]
~~~

Hai cách diễn đạt cùng một ý trong ngữ cảnh predicate. Dùng #this tường minh thường hữu ích khi biểu thức dài, có nhiều tầng truy cập hoặc có nested selection.

## Phân biệt #this và #root

Hai biến đặc biệt này có vai trò khác nhau:

| Biến | Ý nghĩa | Hành vi trong selection |
|---|---|---|
| **#root** | Root object ban đầu của lần đánh giá | Giữ nguyên trong suốt biểu thức |
| **#this** | Đối tượng hiện tại tại vị trí đang đánh giá | Trở thành từng phần tử khi predicate chạy |

Giả sử ứng dụng có Catalog chứa danh sách Product và ngưỡng giá tối thiểu:

~~~java
public class Catalog {
    private final List<Product> products;
    private final BigDecimal minimumPrice;

    public Catalog(
            List<Product> products,
            BigDecimal minimumPrice) {
        this.products = products;
        this.minimumPrice = minimumPrice;
    }

    public List<Product> getProducts() {
        return products;
    }

    public BigDecimal getMinimumPrice() {
        return minimumPrice;
    }
}
~~~

Có thể lọc sản phẩm bằng biểu thức:

~~~java
Catalog catalog =
        new Catalog(products, new BigDecimal("50.00"));

Expression expression = parser.parseExpression(
        "products.?[#this.price >= #root.minimumPrice]");

List<?> selected =
        expression.getValue(catalog, List.class);
~~~

Trong predicate:

- **#this.price** đọc giá của Product đang được kiểm tra.
- **#root.minimumPrice** đọc ngưỡng từ Catalog ban đầu.

Khi selection chuyển sang Product tiếp theo, #this thay đổi theo phần tử đó. #root vẫn là Catalog, không biến thành Product. Nhờ vậy, biểu thức có thể kết hợp dữ liệu của phần tử hiện tại với cấu hình hoặc thuộc tính của đối tượng gốc.

Nếu viết nhầm **#this.minimumPrice** trong ví dụ này, SpEL sẽ tìm property minimumPrice trên Product hiện tại. Đây không phải dữ liệu mà biểu thức cần truy cập.

## #this thay đổi theo từng phần tử

Có thể hình dung selection thực hiện một lượt đánh giá riêng cho từng phần tử:

~~~text
Collection: [P1, P2, P3]
Predicate: #this.active

Lần đánh giá 1: #this = P1 -> true
Lần đánh giá 2: #this = P2 -> false
Lần đánh giá 3: #this = P3 -> true

Kết quả selection: [P1, P3]
~~~

Giá trị #this không phải một biến Java mà ứng dụng tự khai báo bằng setVariable. Đây là biến đặc biệt do SpEL quản lý trong evaluation context và được cập nhật theo đối tượng đang được đánh giá.

Do đó, không cần tự tạo một biến tên this cho từng phần tử. Chỉ cần dùng **#this** trong selection expression để tham chiếu đến phần tử hiện tại.

## Dùng #this với selection trên Map

Selection cũng hỗ trợ Map. Với Map, SpEL đánh giá điều kiện trên từng entry và trả về một Map mới chứa những entry thỏa mãn predicate.

Một entry có key và value. Trong ngữ cảnh selection trên Map, có thể truy cập hai phần này thông qua **#this.key** và **#this.value** khi accessor tương ứng hỗ trợ:

~~~java
Map<String, Integer> inventory = Map.of(
        "keyboard", 12,
        "monitor", 3,
        "mouse", 25);

context.setVariable("inventory", inventory);

Expression expression = parser.parseExpression(
        "#inventory.?[#this.value >= 10]");

Map<?, ?> available =
        expression.getValue(context, Map.class);
~~~

Kết quả giữ lại các entry có value ít nhất bằng 10, gồm keyboard và mouse. Ở đây, #this là entry đang được kiểm tra, không phải toàn bộ Map.

Có thể lọc dựa trên key:

~~~text
#inventory.?[#this.key.startsWith('m')]
~~~

Biểu thức giữ lại những entry có key bắt đầu bằng chữ m, nếu evaluation context cho phép gọi instance method startsWith trên String. Nếu context chỉ đọc không bật method invocation, hãy dùng một context phù hợp hoặc chuẩn bị dữ liệu cần thiết trong Java.

Với Map, cần nhớ rằng selection lọc theo entry. Nó không biến Map thành một List các value. Nếu chỉ cần danh sách value sau khi lọc hoặc muốn chuyển đổi dữ liệu, hãy cân nhắc projection hoặc xử lý trong Java.

## #this trong nested selection

Một collection có thể chứa các object mà mỗi object lại chứa một collection khác. Khi selection được lồng nhau, **#this** được cập nhật theo ngữ cảnh selection hiện tại.

Ví dụ, một Department có nhiều Employee. Ta muốn chọn những phòng ban có ít nhất một nhân viên đang hoạt động:

~~~java
Expression expression = parser.parseExpression(
        "departments.?["
        + "#this.employees.?[#this.active].size() > 0"
        + "]");
~~~

Trong predicate bên ngoài, #this là Department hiện tại. Khi SpEL đi vào selection bên trong **employees.?[...]**, #this của predicate bên trong là Employee hiện tại. Sau khi biểu thức selection bên trong hoàn tất, ngữ cảnh của predicate bên ngoài tiếp tục là Department đang xét.

Trong ví dụ này, **#root** vẫn là root object ban đầu. Nếu cần truy cập dữ liệu cấu hình hoặc thuộc tính của đối tượng gốc từ cả hai tầng, #root là tham chiếu ổn định hơn.

Lời gọi **size()** trong ví dụ yêu cầu EvaluationContext hỗ trợ instance method invocation. Với SimpleEvaluationContext mặc định dành cho read-only data binding, method invocation không được bật sẵn. Nếu không muốn mở khả năng gọi method, có thể tính trước thông tin cần thiết trong Java hoặc dùng một context được cấu hình đúng với use case.

Nested selection dễ trở nên khó đọc nếu có nhiều tầng. Khi biểu thức phải dựa vào nhiều biến #this ở các cấp khác nhau, hãy cân nhắc tách logic thành các method Java có tên rõ ràng.

## #this và các toán tử selection

SpEL có ba dạng selection thường dùng:

| Cú pháp | Ý nghĩa | Kết quả |
|---|---|---|
| **.?[condition]** | Chọn tất cả phần tử phù hợp | Collection hoặc Map chứa các phần tử phù hợp |
| **.^[condition]** | Chọn phần tử phù hợp đầu tiên | Một phần tử |
| **.$[condition]** | Chọn phần tử phù hợp cuối cùng | Một phần tử |

Biến #this có cùng vai trò là phần tử hiện tại trong predicate của các dạng selection này.

Ví dụ, chọn sản phẩm phù hợp đầu tiên:

~~~java
Expression firstMatch = parser.parseExpression(
        "#products.^[#this.active and #this.price >= 50]");

Product first =
        firstMatch.getValue(context, Product.class);
~~~

Chọn sản phẩm phù hợp cuối cùng:

~~~java
Expression lastMatch = parser.parseExpression(
        "#products.$[#this.active and #this.price >= 50]");

Product last =
        lastMatch.getValue(context, Product.class);
~~~

Dùng **.?[...]** khi cần tất cả kết quả; dùng **.^[...]** hoặc **.$[...]** khi chỉ cần một phần tử theo vị trí xuất hiện đầu tiên hoặc cuối cùng trong thứ tự duyệt. Nếu không có phần tử phù hợp, kết quả của first/last selection có thể là null; ứng dụng cần xử lý trường hợp này.

## Phân biệt selection với projection

Selection và projection đều duyệt collection nhưng có mục đích khác nhau:

- **Selection .?[...]** lọc và giữ nguyên các phần tử thỏa điều kiện.
- **Projection .![...]** tạo collection kết quả từ giá trị biểu thức được tính cho từng phần tử.

Ví dụ, lọc sản phẩm có giá từ 50 trở lên:

~~~text
#products.?[#this.price >= 50]
~~~

Ví dụ, lấy tên của tất cả sản phẩm:

~~~text
#products.![#this.name]
~~~

Ví dụ kết hợp hai thao tác:

~~~text
#products.?[#this.active].![#this.name]
~~~

Biểu thức cuối chọn sản phẩm đang hoạt động rồi tạo collection tên từ các sản phẩm đã chọn. Trong selection đầu tiên, #this là Product đang xét; trong projection tiếp theo, #this lại là Product đang được biến đổi. Phần tử hiện tại luôn gắn với ngữ cảnh đánh giá hiện hành.

## EvaluationContext và biến #this

**#this** là biến đặc biệt của SpEL, khác với biến ứng dụng tự đặt như **#minimumPrice**. Ứng dụng có thể dùng **setVariable(...)** để đưa biến nghiệp vụ vào context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable(
        "minimumPrice",
        new BigDecimal("50.00"));

Expression expression = parser.parseExpression(
        "products.?[#this.price >= #minimumPrice]");
~~~

Trong biểu thức này, #this do SpEL cập nhật theo từng Product. #minimumPrice do ứng dụng cung cấp và giữ giá trị được gán trong context.

Không nên cố ghi đè #this bằng setVariable để điều khiển phần tử hiện tại. Vòng đời của #this thuộc về quá trình đánh giá expression. Nếu muốn truyền một ngưỡng, trạng thái hoặc tham số nghiệp vụ, hãy dùng tên biến riêng.

## Những lỗi dễ gặp khi dùng #this

- **Nhầm #this với #root:** trong selection, #this là phần tử hiện tại; #root vẫn là object gốc.
- **Dùng #this bên ngoài predicate như thể nó luôn là phần tử collection:** ngoài ngữ cảnh selection hoặc projection, #this phản ánh đối tượng hiện tại của lần đánh giá tại vị trí đó.
- **Nhầm Map với List:** khi selection trên Map, #this đại diện cho entry đang được xét; có thể cần truy cập key và value.
- **Quên nested selection thay đổi #this:** bên trong selection lồng nhau, #this trỏ đến phần tử của collection bên trong.
- **Dùng method không được context cho phép:** gọi size(), startsWith() hoặc method khác cần EvaluationContext hỗ trợ instance method invocation.
- **Nhầm selection với projection:** selection giữ các phần tử thỏa điều kiện; projection tạo giá trị mới từ từng phần tử.
- **Không xử lý collection null hoặc rỗng:** cần xác định chính sách null và trường hợp không có phần tử phù hợp.

Khi biểu thức parse thành công nhưng không truy cập được property hoặc method trên phần tử hiện tại, lỗi xuất hiện trong giai đoạn evaluation. Hãy kiểm tra kiểu phần tử thực tế, property accessor và cấu hình EvaluationContext.

## Khi nào nên dùng #this?

#this hữu ích khi:

- Predicate selection cần truy cập nhiều property của phần tử hiện tại.
- Muốn kết hợp dữ liệu của phần tử với cấu hình trên #root.
- Selection được lồng nhau và cần phân biệt phần tử ở từng cấp.
- Muốn biểu thức thể hiện rõ đối tượng đang được kiểm tra.
- Lọc Map theo key hoặc value thông qua entry hiện tại.

Với điều kiện đơn giản, có thể dùng trực tiếp tên property trong predicate. Khi biểu thức có nhiều cấp hoặc dễ nhầm root object với phần tử, viết rõ #this và #root sẽ giúp người đọc hiểu phạm vi dữ liệu.

Nếu predicate có nhiều bước nghiệp vụ, gọi dịch vụ hoặc cần xử lý lỗi phức tạp, hãy chuyển phần lọc sang Java Stream hoặc một method chuyên biệt. SpEL phù hợp với biểu thức khai báo ngắn, nơi ngữ cảnh hiện tại có thể hiểu rõ.

## Kết luận

Trong collection selection, **#this đại diện cho phần tử hiện tại đang được kiểm tra**. Mỗi lần predicate được đánh giá, SpEL cập nhật #this theo phần tử tương ứng. Ngược lại, **#root luôn giữ tham chiếu đến root object ban đầu** trong toàn bộ lần đánh giá.

Hiểu đúng hai biến này giúp viết selection trên List, array và Map, đồng thời tránh nhầm lẫn trong nested selection. Dùng #this để truy cập property của phần tử, #root để lấy dữ liệu từ object gốc và biến có tên riêng để truyền tham số nghiệp vụ. Khi biểu thức trở nên nhiều tầng hoặc khó đọc, chuyển logic sang Java sẽ giúp kiểm soát và kiểm thử dễ hơn.
