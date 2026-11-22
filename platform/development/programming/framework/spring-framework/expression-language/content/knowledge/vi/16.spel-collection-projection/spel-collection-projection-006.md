# Projection trên map và hình dạng kết quả

Trong Spring Expression Language (SpEL), **projection** dùng toán tử **.![]** để áp dụng một biểu thức lên từng phần tử của collection và thu thập các giá trị được tạo ra. Khi projection chạy trên **Map**, SpEL đánh giá biểu thức projection trên từng entry của Map. Mỗi entry cung cấp hai thành phần quan trọng là **key** và **value**.

Điểm cần nhớ là kết quả projection trên Map có hình dạng là **List** các giá trị được tính từ từng entry. Projection không tạo một Map mới và không tự giữ lại key ban đầu. Nếu cần một Map mới với key-value được biến đổi, ứng dụng cần xây dựng Map đó trong Java hoặc dùng một cơ chế chuyển đổi dữ liệu phù hợp.

## Cú pháp projection trên Map

Cú pháp tổng quát:

~~~text
map.![projectionExpression]
~~~

SpEL duyệt các entry của Map. Với mỗi entry, nó đánh giá **projectionExpression** trong ngữ cảnh của entry hiện tại rồi thêm kết quả vào List.

Trong predicate hoặc projection trên Map, **#this** tham chiếu đến **Map.Entry** hiện tại. Có thể truy cập:

- **#this.key**: key của entry hiện tại.
- **#this.value**: value của entry hiện tại.

Ví dụ, lấy toàn bộ value của một Map:

~~~java
Map<String, Integer> inventory = new LinkedHashMap<>();
inventory.put("keyboard", 12);
inventory.put("monitor", 3);
inventory.put("mouse", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("inventory", inventory);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("#inventory.![#this.value]");

List<?> quantities =
        expression.getValue(context, List.class);
~~~

Kết quả là List chứa các số **12, 3, 25** theo thứ tự duyệt entry của Map. Mỗi lần projection đánh giá, #this lần lượt là entry keyboard, monitor và mouse.

Vì kết quả là List, kiểu trả về ở đây là **List<?>**, không phải Map<String, Integer>. Các key gốc không được giữ lại trong cấu trúc kết quả.

## Lấy key từ từng entry

Nếu biểu thức projection trả về **#this.key**, kết quả là danh sách các key:

~~~java
Expression expression =
        parser.parseExpression("#inventory.![#this.key]");

List<?> keys =
        expression.getValue(context, List.class);
~~~

Với Map ở trên, kết quả là danh sách **keyboard**, **monitor**, **mouse**. Đây là một cách tạo danh sách key theo thứ tự duyệt hiện tại của Map.

Có thể viết ngắn hơn bằng property **key** trong ngữ cảnh entry:

~~~text
#inventory.![key]
~~~

Tuy nhiên, viết **#this.key** giúp thể hiện rõ rằng property key thuộc entry đang được projection xử lý. Cách viết tường minh đặc biệt hữu ích khi biểu thức có nhiều tầng hoặc khi đọc cùng lúc cả key và value.

## Chiếu value thành một thuộc tính khác

Trường hợp phổ biến hơn là Map chứa object. Projection có thể lấy một thuộc tính từ value của mỗi entry.

Giả sử Map ánh xạ mã SKU sang Product:

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
Map<String, Product> productsBySku = new LinkedHashMap<>();
productsBySku.put(
        "KB-01",
        new Product("Keyboard", new BigDecimal("80.00")));
productsBySku.put(
        "MN-02",
        new Product("Monitor", new BigDecimal("250.00")));
productsBySku.put(
        "MS-03",
        new Product("Mouse", new BigDecimal("25.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("productsBySku", productsBySku);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression(
                "#productsBySku.![#this.value.name]");

List<?> productNames =
        expression.getValue(context, List.class);
~~~

Kết quả là List chứa **Keyboard**, **Monitor**, **Mouse**. Mỗi lượt projection lấy entry hiện tại, truy cập value để nhận Product, sau đó đọc property name của Product đó.

Có thể chiếu giá:

~~~text
#productsBySku.![#this.value.price]
~~~

Kết quả là một List các giá trị BigDecimal. Kiểu phần tử của List phụ thuộc vào kiểu kết quả của projection expression.

## Kết hợp key và value thành một giá trị mới

Projection expression có thể tính toán hoặc kết hợp dữ liệu của entry. Ví dụ, tạo một chuỗi mô tả từ SKU và tên sản phẩm:

~~~java
Expression expression = parser.parseExpression(
        "#productsBySku.![#this.key + ': ' + #this.value.name]");

List<?> descriptions =
        expression.getValue(context, List.class);
~~~

Kết quả có dạng:

~~~text
[
  "KB-01: Keyboard",
  "MN-02: Monitor",
  "MS-03: Mouse"
]
~~~

Mỗi entry tạo ra một String mới. List kết quả chứa các String đó, còn Map ban đầu vẫn giữ nguyên key và value.

Tương tự, có thể tạo một danh sách giá sau thuế, nhãn hiển thị hoặc một giá trị tổng hợp từ mỗi entry. Tuy nhiên, nếu phép biến đổi cần nhiều bước, gọi service hoặc xử lý lỗi phức tạp, nên chuyển phần logic sang Java để biểu thức không trở nên khó đọc.

## Hình dạng kết quả: List thay vì Map

Đây là điểm quan trọng nhất khi dùng projection trên Map:

| Projection expression | Kiểu hình dạng kết quả | Nội dung |
|---|---|---|
| **#map.![#this.key]** | List | Danh sách key |
| **#map.![#this.value]** | List | Danh sách value |
| **#map.![#this.value.name]** | List | Danh sách tên lấy từ value |
| **#map.![#this.key + ':' + #this.value]** | List | Danh sách chuỗi kết hợp key và value |

Ngay cả khi Map đầu vào có kiểu **Map<K, V>**, kết quả projection vẫn là một List của các giá trị được tính. Projection không tự tạo cặp key-value mới và cũng không bảo đảm mỗi kết quả có thể được ánh xạ ngược về key ban đầu nếu biểu thức không đưa key vào kết quả.

Nếu cần giữ liên kết giữa key và giá trị đã biến đổi, có thể chiếu ra một object kết quả có chứa cả hai trường, hoặc xử lý Map bằng Java:

~~~java
Map<String, String> namesBySku = new LinkedHashMap<>();

productsBySku.forEach((sku, product) ->
        namesBySku.put(sku, product.getName()));
~~~

Cách này giữ nguyên key SKU và tạo Map mới ánh xạ SKU sang tên sản phẩm. Nó thể hiện rõ hình dạng dữ liệu mong muốn mà projection trên Map không cung cấp trực tiếp.

## Thứ tự phần tử trong List kết quả

Projection giữ thứ tự duyệt entry của Map đầu vào. Vì vậy, thứ tự List kết quả phụ thuộc vào implementation và trạng thái của Map:

- **LinkedHashMap** thường duy trì thứ tự chèn, nên List projection có thứ tự tương ứng.
- **TreeMap** duyệt entry theo thứ tự sắp xếp của key, nên List kết quả đi theo thứ tự đó.
- **HashMap** không bảo đảm thứ tự duyệt ổn định; không nên dựa vào một thứ tự cụ thể trong List projection.

Nếu thứ tự là yêu cầu nghiệp vụ, hãy chọn Map có thứ tự phù hợp hoặc sắp xếp dữ liệu trước khi đánh giá biểu thức. Không nên viết test dựa vào thứ tự tình cờ của HashMap.

Ví dụ với LinkedHashMap:

~~~java
Map<String, Integer> values = new LinkedHashMap<>();
values.put("first", 10);
values.put("second", 20);
values.put("third", 30);

context.setVariable("values", values);

List<?> result =
        parser.parseExpression("#values.![#this.value]")
                .getValue(context, List.class);
~~~

List kết quả có thứ tự **10, 20, 30**, tương ứng với thứ tự entry của LinkedHashMap.

## Projection trên Map rỗng

Nếu Map đầu vào rỗng, không có entry nào để đánh giá projection expression. Kết quả là một List rỗng:

~~~java
context.setVariable("emptyMap", Collections.emptyMap());

List<?> result =
        parser.parseExpression("#emptyMap.![#this.value]")
                .getValue(context, List.class);
~~~

Kết quả không chứa phần tử. Đây là kết quả khác với trường hợp Map là null. Khi đối tượng đầu vào null, không có Map để duyệt và evaluation có thể phát sinh lỗi nếu dùng projection thông thường.

Nếu Map có thể null, hãy xác định chính sách xử lý trước khi đánh giá: kiểm tra null trong Java, cung cấp một Map rỗng thay thế khi phù hợp hoặc dùng cơ chế null-safe được phiên bản Spring hỗ trợ. Không nên coi null và Map rỗng là cùng một trạng thái nếu nghiệp vụ cần phân biệt chúng.

## Giá trị null bên trong Map

Map có thể chứa entry mà value là null. Khi projection truy cập trực tiếp **#this.value**, kết quả tương ứng có thể là null. Nhưng nếu biểu thức tiếp tục truy cập property của value, ví dụ **#this.value.name**, việc truy cập trên null có thể gây lỗi evaluation.

Ví dụ, nếu có một entry với value null:

~~~text
#productsBySku.![#this.value.name]
~~~

Biểu thức không thể đọc property name từ value null. Nếu dữ liệu cho phép null, hãy kiểm tra value trước khi truy cập sâu:

~~~text
#productsBySku.![#this.value == null ? 'Unknown' : #this.value.name]
~~~

Biểu thức trên tạo một List tên hiển thị; entry có value null tạo ra chuỗi **Unknown**. Đây là một chính sách thay thế được thể hiện rõ trong biểu thức. Chỉ dùng giá trị mặc định nếu nó đúng với quy tắc nghiệp vụ.

Nếu cần bỏ qua các entry có value null thay vì tạo nhãn mặc định, có thể selection Map trước rồi projection trên kết quả:

~~~text
#productsBySku.?[#this.value != null].![#this.value.name]
~~~

Selection giữ lại các entry phù hợp; projection tiếp theo lấy tên từ value. Kết quả cuối cùng vẫn là List.

## Phân biệt selection và projection trên Map

Selection và projection có thể dùng chung #this nhưng tạo ra hình dạng kết quả khác nhau:

- **Selection .?[condition]** lọc các entry của Map và giữ lại những entry thỏa điều kiện. Kết quả là Map chứa các cặp key-value được chọn.
- **Projection .![expression]** đánh giá biểu thức trên từng entry và thu thập kết quả vào một List.

Ví dụ, chỉ giữ sản phẩm có giá ít nhất 50:

~~~text
#productsBySku.?[#this.value.price >= 50]
~~~

Kết quả là Map vẫn giữ SKU làm key và Product làm value.

Nếu muốn lấy tên của các sản phẩm có giá ít nhất 50:

~~~text
#productsBySku.?[#this.value.price >= 50].![#this.value.name]
~~~

Kết quả là List tên sản phẩm. Sau selection, Map còn giữ các entry phù hợp; projection chuyển các entry đó thành những giá trị tên.

Nếu muốn lấy các SKU của sản phẩm đang hoạt động:

~~~text
#productsBySku.?[#this.value.active].![#this.key]
~~~

Kết quả là List key của các entry đã được chọn. Cần nhớ selection và projection là hai bước: bước đầu lọc Map, bước sau tạo List.

## #this trong projection trên Map

Trong projection trên Map, **#this** đại diện cho entry hiện tại. Điều này khác với projection trên List, nơi #this là phần tử List hiện tại.

Với Map<String, Product>:

- **#this.key** là String SKU.
- **#this.value** là Product.
- **#this.value.name** là tên Product.
- **#root** vẫn là root object ban đầu của lần đánh giá.

Nếu biểu thức được đánh giá với một root object là Catalog có property productsBySku, có thể viết:

~~~text
productsBySku.![#this.key + ':' + #this.value.name]
~~~

Trong đó root object là Catalog, còn #this trong projection là từng Map.Entry. Nếu cần truy cập thuộc tính của Catalog bên trong projection, dùng #root để tham chiếu rõ ràng đến object ban đầu.

## EvaluationContext và quyền truy cập property

Để projection đọc được key, value và property lồng nhau, EvaluationContext phải cung cấp các cơ chế truy cập tương ứng. **StandardEvaluationContext** hỗ trợ nhiều khả năng truy cập và gọi method. **SimpleEvaluationContext** có thể phù hợp nếu chỉ cần data binding với tập khả năng giới hạn, nhưng việc gọi instance method không được bật mặc định trong builder read-only thông thường.

Ví dụ **#this.value.name** chủ yếu cần đọc property. Nếu projection expression gọi method như **#this.value.name.toUpperCase()**, context phải cho phép instance method invocation. Hãy chỉ bật khả năng này khi use case yêu cầu.

Nếu Map hoặc value có cấu trúc phức tạp, property accessor tùy chỉnh có thể được dùng để expose những dữ liệu cần thiết. Khi biểu thức đến từ nguồn bên ngoài, nên giới hạn root object, accessor và biến được cung cấp thay vì expose toàn bộ ứng dụng.

## Lỗi thường gặp

- **Kỳ vọng projection trả về Map:** projection trên Map tạo List các giá trị được tính, không giữ key gốc.
- **Dùng nhầm key và value:** Map.Entry có hai phần; dùng #this.key để lấy key và #this.value để lấy value.
- **Quên thứ tự duyệt Map:** List kết quả theo thứ tự iteration của Map, không phải lúc nào cũng là thứ tự chèn hoặc thứ tự sắp xếp.
- **Truy cập property trên value null:** cần kiểm tra null hoặc áp dụng chính sách mặc định.
- **Nhầm selection với projection:** selection giữ entry phù hợp và kết quả là Map; projection tạo List giá trị.
- **Dùng method không được context hỗ trợ:** gọi method trên value cần EvaluationContext cho phép instance method invocation.
- **Không xử lý Map null hoặc rỗng:** Map rỗng tạo List rỗng; Map null cần chính sách xử lý riêng.

Một chuỗi biểu thức có thể parse thành công nhưng lỗi trong lúc evaluate nếu property không tồn tại, value null hoặc context không hỗ trợ thao tác được yêu cầu. Nên tách lỗi parse và evaluation khi xử lý ngoại lệ, đồng thời ghi nhận mã biểu thức và ngữ cảnh cần thiết để chẩn đoán.

## Khi nào nên dùng projection trên Map?

Projection trên Map phù hợp khi cần tạo danh sách giá trị từ các entry, chẳng hạn:

- Lấy toàn bộ key hoặc value.
- Lấy một thuộc tính từ object được lưu trong value.
- Tạo nhãn hiển thị kết hợp key và value.
- Lọc Map trước rồi chiếu các entry còn lại thành List.
- Dùng một biểu thức ngắn tại điểm tích hợp Spring hỗ trợ SpEL.

Nếu cần giữ key, tạo Map mới, sắp xếp phức tạp, gom nhóm hoặc xử lý nhiều bước, nên dùng Java Stream hoặc vòng lặp rõ ràng. Cấu trúc Java thường thể hiện tốt hơn khi hình dạng đầu ra cần được kiểm soát chính xác.

## Kết luận

Projection trên Map dùng cú pháp **map.![projectionExpression]**. Trong mỗi lượt, **#this** là Map.Entry hiện tại; có thể đọc key qua **#this.key** và value qua **#this.value**. SpEL đánh giá biểu thức trên từng entry rồi thu thập các giá trị vào một **List**, vì vậy key ban đầu không được tự động giữ lại.

Thứ tự List phụ thuộc vào thứ tự duyệt của Map. Nếu cần giữ key-value, hãy chiếu ra một object chứa cả hai hoặc tạo Map mới trong Java. Phân biệt projection với selection, xử lý value null và chọn Map có thứ tự phù hợp sẽ giúp hình dạng kết quả dễ dự đoán và dễ bảo trì.
