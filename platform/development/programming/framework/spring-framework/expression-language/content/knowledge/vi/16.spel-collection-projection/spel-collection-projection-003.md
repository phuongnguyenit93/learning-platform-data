# Chuyển collection object thành collection giá trị

Spring Expression Language (SpEL) cung cấp **collection projection** để áp dụng một biểu thức lên từng phần tử của collection và tạo ra một collection kết quả mới. Projection đặc biệt hữu ích khi dữ liệu đầu vào là danh sách object, nhưng phần xử lý chỉ cần một thuộc tính hoặc một giá trị được tính từ mỗi object.

Ví dụ, từ danh sách Order, có thể tạo danh sách mã đơn hàng hoặc tổng tiền:

~~~text
#orders.![id]
#orders.![total]
~~~

Mỗi phần tử đầu vào được đọc một lần theo biểu thức projection. Kết quả là một tập giá trị được trích xuất hoặc biến đổi, giúp cấu hình ngắn gọn khi cần chuyển object thành dữ liệu đơn giản.

## 1. Cú pháp projection

Cú pháp tổng quát:

~~~text
collection.![projectionExpression]
~~~

Dấu **.!** là projection operator. Phần nằm trong ngoặc vuông là biểu thức được đánh giá cho từng phần tử.

Ví dụ:

~~~text
#orders.![customer.name]
~~~

Với mỗi Order trong orders, SpEL đọc customer.name rồi đưa kết quả vào collection mới.

Giả sử dữ liệu đầu vào:

~~~java
List<Order> orders = List.of(
    new Order("ORD-001", "An", new BigDecimal("120.00")),
    new Order("ORD-002", "Binh", new BigDecimal("85.00")),
    new Order("ORD-003", "Chi", new BigDecimal("240.00"))
);
~~~

Projection:

~~~text
#orders.![id]
~~~

tạo danh sách mã:

~~~text
["ORD-001", "ORD-002", "ORD-003"]
~~~

Projection:

~~~text
#orders.![total]
~~~

tạo danh sách tổng tiền:

~~~text
[120.00, 85.00, 240.00]
~~~

Projection:

~~~text
#orders.![customerName.toUpperCase()]
~~~

tạo danh sách tên đã chuyển thành chữ hoa, nếu model Order có property customerName và method được phép trong EvaluationContext.

Điểm quan trọng: projection không chỉ lấy property. Projection expression có thể là một phép tính, phép nối chuỗi, lời gọi method được phép hoặc một đường dẫn property lồng nhau.

## 2. SpEL đánh giá từng phần tử như thế nào?

Khi projection chạy, SpEL lặp qua các phần tử của nguồn. Trong mỗi lần lặp, expression được đánh giá trên phần tử hiện tại.

Có thể hình dung:

1. Lấy phần tử đầu tiên.
2. Đặt phần tử đó làm evaluation object hiện tại.
3. Đánh giá projection expression.
4. Thêm kết quả vào collection đầu ra.
5. Tiếp tục với các phần tử còn lại.

Vì vậy, trong projection trên List<Order>, biểu thức:

~~~text
#orders.![customer.name]
~~~

được hiểu như đang đọc customer.name trên từng Order.

### 2.1. Dùng property không cần #this

Vì evaluation object hiện tại là phần tử đang được xử lý, có thể tham chiếu property trực tiếp:

~~~text
#orders.![id]
#orders.![customer.name]
#orders.![total.multiply(1.1)]
~~~

Trong ví dụ cuối, SpEL gọi method multiply trên property total của từng Order. Hãy bảo đảm method có sẵn và phù hợp với context.

### 2.2. Dùng #this để chỉ rõ phần tử hiện tại

Biến **#this** luôn đại diện cho evaluation object hiện tại. Trong projection, #this là phần tử hiện đang được xử lý:

~~~text
#orders.![#this.customer.name]
#orders.![#this.total]
~~~

Hai cách viết có cùng ý nghĩa trong ví dụ trên. Dùng #this giúp biểu thức rõ ràng hơn khi có nhiều property cùng tên hoặc khi kết hợp với biểu thức phức tạp.

### 2.3. Phân biệt #this và #root

- **#this** thay đổi theo evaluation object hiện tại; trong projection nó trỏ đến phần tử đang được xử lý.
- **#root** luôn trỏ đến root context object ban đầu.

Ví dụ, giả sử root object là một ReportRequest có property orders và reportName:

~~~text
#root.reportName + ': ' + #this.id
~~~

Nếu expression này được dùng trong projection trên orders, #this.id là ID của Order hiện tại, còn #root.reportName vẫn là tên báo cáo gốc.

Có thể dùng cả hai để tạo nhãn:

~~~text
#root.reportName + ' / ' + #this.customer.name
~~~

## 3. Các kiểu dữ liệu hỗ trợ projection

SpEL hỗ trợ projection trên:

- Array.
- Các kiểu triển khai java.lang.Iterable, bao gồm List và Set.
- Map.

Kết quả projection là collection mới. Khi projection chạy trên Map, SpEL đánh giá projection expression trên từng entry của Map, được biểu diễn bởi java.util.Map.Entry. Kết quả của projection trên Map là một List gồm các giá trị được tính từ từng entry.

Điều này quan trọng: projection trên Map không giữ nguyên cấu trúc key-value của Map. Nếu cần một Map mới với key và value được chọn hoặc biến đổi, hãy cân nhắc cách tạo Map trong Java hoặc một thao tác phù hợp khác.

### 3.1. Projection trên List

~~~java
context.setVariable("names", List.of("An", "Binh", "Chi"));
~~~

Expression:

~~~text
#names.![#this.toUpperCase()]
~~~

Kết quả:

~~~text
["AN", "BINH", "CHI"]
~~~

### 3.2. Projection trên array

~~~java
context.setVariable("scores", new int[] {70, 85, 92});
~~~

Expression:

~~~text
#scores.![#this + 5]
~~~

Kết quả là collection các giá trị đã cộng thêm 5:

~~~text
[75, 90, 97]
~~~

### 3.3. Projection trên Map

~~~java
Map<String, Integer> stock = Map.of(
    "PEN", 12,
    "BOOK", 8,
    "BAG", 3
);
context.setVariable("stock", stock);
~~~

Với Map, #this là một Map.Entry. Có thể lấy key:

~~~text
#stock.![#this.key]
~~~

Hoặc lấy value:

~~~text
#stock.![#this.value]
~~~

Hoặc tạo chuỗi mô tả cho mỗi entry:

~~~text
#stock.![#this.key + ':' + #this.value]
~~~

Kết quả là List, theo thứ tự duyệt của Map nguồn. Nếu thứ tự có ý nghĩa, hãy dùng Map có iteration order được xác định, chẳng hạn LinkedHashMap.

## 4. Chuyển object thành giá trị đơn giản

Một trường hợp phổ biến là tạo danh sách ID, tên, trạng thái hoặc số liệu từ collection object.

Giả sử có model:

~~~java
class Product {
    private String sku;
    private String name;
    private BigDecimal price;

    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
~~~

Đăng ký collection vào EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("products", products);

ExpressionParser parser = new SpelExpressionParser();
~~~

Lấy danh sách SKU:

~~~java
List<?> skus = parser
        .parseExpression("#products.![sku]")
        .getValue(context, List.class);
~~~

Lấy danh sách tên:

~~~java
List<?> names = parser
        .parseExpression("#products.![name]")
        .getValue(context, List.class);
~~~

Lấy danh sách giá:

~~~java
List<?> prices = parser
        .parseExpression("#products.![price]")
        .getValue(context, List.class);
~~~

Có thể tạo giá trị tính toán thay vì lấy nguyên property:

~~~text
#products.![price * 1.08]
~~~

Hoặc tạo chuỗi hiển thị:

~~~text
#products.![sku + ' - ' + name]
~~~

Mỗi phần tử của collection kết quả là kết quả của expression tương ứng với một Product đầu vào.

## 5. Projection trên property lồng nhau

Projection có thể đọc sâu vào object graph:

~~~text
#orders.![customer.address.city]
~~~

Từ List<Order>, biểu thức tạo List chứa city của từng khách hàng.

Ví dụ khác:

~~~text
#employees.![department.manager.name]
#invoices.![customer.billingAddress.postalCode]
#books.![publisher.name]
~~~

Có thể tính giá trị từ nhiều property:

~~~text
#orders.![customer.name + ' - ' + total]
~~~

Hoặc trả về một cấu trúc dữ liệu đơn giản cho từng object bằng inline map:

~~~text
#products.![{sku: sku, label: name, amount: price}]
~~~

Projection expression trong ví dụ cuối tạo một Map cho mỗi Product. Kết quả là một List các Map, mỗi Map chứa các giá trị được lấy từ một object đầu vào.

Dùng cách này khi cần chuyển domain object thành cấu trúc nhỏ gọn phục vụ hiển thị hoặc truyền dữ liệu. Nếu mapping có nhiều trường, quy tắc định dạng phức tạp hoặc cần validation, DTO mapper trong Java thường dễ bảo trì và kiểm thử hơn.

## 6. Kết hợp selection và projection

Projection và selection có mục đích khác nhau:

- **Selection** dùng để lọc phần tử theo điều kiện.
- **Projection** dùng để biến đổi mỗi phần tử thành một giá trị khác.

Ví dụ, lấy ID của các đơn hàng có tổng tiền từ 100 trở lên:

~~~text
#orders.?[total >= 100].![id]
~~~

Có thể đọc theo thứ tự:

1. #orders.?[total >= 100] giữ lại các Order thỏa điều kiện.
2. .![id] lấy ID từ mỗi Order còn lại.
3. Kết quả cuối cùng là List ID.

Ví dụ lấy tên khách hàng của các đơn hàng đã thanh toán:

~~~text
#orders.?[status == 'PAID'].![customer.name]
~~~

So sánh các expression:

| Expression | Tác dụng | Kết quả |
| --- | --- | --- |
| **#orders[0]** | Lấy phần tử theo index | Một Order |
| **#orders.?[total > 100]** | Lọc Order theo điều kiện | Collection Order |
| **#orders.![id]** | Chuyển mỗi Order thành ID | Collection ID |
| **#orders.?[total > 100].![id]** | Lọc rồi chuyển thành ID | Collection ID |

Không nên dùng projection để lọc dữ liệu. Nếu projection expression trả về true/false, kết quả sẽ là danh sách boolean tương ứng với từng phần tử, chứ không phải danh sách các phần tử thỏa điều kiện. Muốn loại bỏ phần tử, hãy dùng selection.

## 7. Xử lý collection hoặc phần tử có thể null

### 7.1. Collection nguồn là null

Projection thông thường yêu cầu nguồn collection tồn tại:

~~~text
#orders.![id]
~~~

Nếu orders là null, expression có thể thất bại khi đánh giá. SpEL hỗ trợ null-safe projection bằng toán tử **?.!**:

~~~text
#orders?.![id]
~~~

Nếu orders là null, biểu thức null-safe projection trả về null thay vì cố duyệt collection.

Điều này khác với collection rỗng. Nếu orders là một List rỗng, projection thông thường trả về một collection kết quả rỗng.

### 7.2. Phần tử bên trong collection là null

Null-safe projection bảo vệ collection nguồn. Nó không tự động bảo vệ mọi property access bên trong projection expression.

Ví dụ:

~~~text
#orders?.![customer.name]
~~~

Nếu collection orders tồn tại nhưng một phần tử là null, hoặc customer của một Order là null, truy cập property có thể gây lỗi.

Hãy dùng safe navigation bên trong projection expression tại các bước có thể null:

~~~text
#orders?.![#this?.customer?.name]
~~~

Trong ví dụ này:

- **?.!** bảo vệ trường hợp collection orders là null.
- **#this?.** bảo vệ phần tử hiện tại nếu phần tử đó null.
- **customer?.name** bảo vệ customer nếu property này null.

Kết quả ở vị trí tương ứng có thể là null. Projection vẫn tạo một kết quả cho mỗi phần tử được duyệt; nó không tự loại bỏ các kết quả null.

### 7.3. Muốn bỏ qua phần tử null hoặc thiếu dữ liệu

Nếu mục tiêu là chỉ lấy tên khách hàng có giá trị, hãy kết hợp selection và projection:

~~~text
#orders.?[customer != null].![customer.name]
~~~

Nếu chính phần tử collection cũng có thể null, điều kiện cần kiểm tra phần tử trước:

~~~text
#orders.?[#this != null and customer != null].![customer.name]
~~~

Selection loại bỏ các phần tử không thỏa điều kiện, sau đó projection mới lấy name từ các phần tử còn lại.

Nếu cần xử lý nhiều trạng thái null hoặc quy tắc lọc phức tạp, hãy cân nhắc chuyển logic sang Java service để biểu đạt rõ ràng hơn.

## 8. Projection có thay đổi collection gốc không?

Projection tạo collection kết quả mới; nó không thay đổi cấu trúc collection nguồn chỉ vì thực hiện phép chuyển đổi.

Ví dụ:

~~~text
#products.![name]
~~~

tạo một List tên mới. Nó không xóa Product khỏi products và cũng không thay đổi thứ tự dữ liệu gốc.

Tuy nhiên, cần phân biệt collection mới với deep copy:

- Nếu projection trả về một giá trị bất biến như String hoặc một số, kết quả chứa các giá trị đó.
- Nếu projection trả về một property là object, ví dụ **#orders.![customer]**, collection đầu ra mới chứa các reference đến Customer hiện có.
- Projection không tự sao chép toàn bộ object graph và không tự clone các object được trả về.

Vì vậy, projection phù hợp cho việc trích xuất và biến đổi dữ liệu theo cách không thay đổi collection nguồn. Nếu expression gọi method có side effect hoặc thay đổi object, side effect đó vẫn có thể xảy ra; nên giữ projection expression đơn giản và chủ yếu mang tính đọc.

## 9. Chạy projection bằng SpEL API trong Java

Có thể parse và evaluate projection bằng các API của SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("orders", orders);

List<?> orderIds = parser
        .parseExpression("#orders.![id]")
        .getValue(context, List.class);
~~~

Ở đây:

- ExpressionParser phân tích chuỗi expression.
- EvaluationContext cung cấp biến orders và các quy tắc truy cập dữ liệu.
- getValue() đánh giá projection và trả về List kết quả.

Nếu muốn nhận một kiểu cụ thể, có thể ép kiểu phần tử sau khi lấy kết quả hoặc chuyển đổi sang DTO trong Java. Do generic type bị xóa ở runtime, getValue(context, List.class) chỉ yêu cầu kết quả là List, không xác nhận kiểu generic của từng phần tử.

Một ví dụ tạo danh sách tên từ collection Product:

~~~java
context.setVariable("products", products);

List<?> names = parser
        .parseExpression("#products.![name]")
        .getValue(context, List.class);
~~~

Với expression có thể chạy nhiều lần, có thể parse một lần rồi tái sử dụng đối tượng Expression:

~~~java
Expression productNames =
        parser.parseExpression("#products.![name]");

List<?> firstResult = productNames.getValue(context, List.class);
List<?> nextResult = productNames.getValue(context, List.class);
~~~

Expression đã parse có thể được dùng lại với context hoặc root object phù hợp. Dữ liệu đầu vào vẫn được lấy tại thời điểm evaluate.

## 10. Ứng dụng projection trong Spring Integration

Một số điểm tích hợp của Spring cung cấp collection làm root object hoặc biến trong expression. Projection có thể chuyển collection message thành collection payload.

Ví dụ, nếu root object là List các Message và cần lấy payload của từng message:

~~~text
#this.![payload]
~~~

Trong một flow xử lý message, biểu thức này tạo collection payload từ danh sách Message đầu vào. Đây là cách ngắn gọn để lấy dữ liệu chính của từng message khi endpoint cung cấp đúng context.

Cần xác định rõ root object và kiểu phần tử tại integration point. Một expression đúng khi root là List<Message> có thể không đúng nếu endpoint cung cấp một Message đơn lẻ hoặc một payload khác.

Tương tự, có thể dùng projection trong các expression của những module khác khi context chứa collection phù hợp. Không nên giả định mọi annotation đều có cùng root object hoặc cùng biến.

## 11. Giới hạn và lưu ý về hiệu năng

Projection tiện cho các phép chuyển đổi ngắn, nhưng vẫn có một số giới hạn cần cân nhắc:

1. **Kết quả là collection mới:** nếu nguồn có N phần tử, projection thường tạo N kết quả. Với dữ liệu lớn, cần lưu ý bộ nhớ của collection đầu ra.
2. **Map projection trả về List:** nếu cần giữ key-value, hãy tạo Map bằng Java hoặc dùng một giải pháp mapping phù hợp.
3. **Property và method phải truy cập được:** expression chỉ chạy được nếu EvaluationContext có accessor hoặc resolver phù hợp.
4. **Phần tử null cần xử lý:** safe projection bảo vệ collection nguồn; property access bên trong vẫn cần safe navigation khi cần.
5. **Projection không phải phép lọc:** dùng selection nếu cần loại bỏ phần tử.
6. **Không nên đặt side effect trong projection:** expression được đánh giá cho từng phần tử; một method thay đổi trạng thái có thể tạo tác động khó kiểm soát.
7. **Cân nhắc hiệu năng ở đường chạy nóng:** projection là một trong các dạng expression mà SpEL compiler không hỗ trợ biên dịch. Nếu expression chạy rất thường xuyên trên collection lớn, hãy đo đạc và cân nhắc Java Stream hoặc mapper chuyên dụng.

Nếu expression do người dùng hoặc hệ thống bên ngoài cung cấp, cần giới hạn các object, property accessor, method resolver và function có thể truy cập trong EvaluationContext. StandardEvaluationContext cung cấp nhiều khả năng của SpEL và không nên dùng để chạy expression không tin cậy. SimpleEvaluationContext giới hạn một số tính năng, nhưng việc giới hạn context vẫn cần được thiết kế cẩn thận.

## 12. Những lỗi thường gặp

1. **Dùng selection thay cho projection:** selection lọc phần tử; projection chuyển đổi phần tử.
2. **Quên dấu chấm trước !:** cú pháp projection là **.![...]**.
3. **Nhầm #this với #root:** #this là phần tử hiện tại; #root luôn là root context object.
4. **Giả định Map projection giữ nguyên Map:** projection trên Map trả về List và expression chạy trên từng Map.Entry.
5. **Không xử lý phần tử null:** collection có thể tồn tại nhưng một phần tử hoặc property bên trong có thể null.
6. **Dùng projection để tạo DTO phức tạp:** mapping lớn với nhiều quy tắc thường nên đặt trong Java mapper.
7. **Giả định kết quả là deep copy:** projection tạo collection mới nhưng object được trả về có thể vẫn là reference đến object gốc.
8. **Không xác định root object của integration point:** cùng một expression có thể có ý nghĩa khác nếu context thay đổi.
9. **Dùng projection trong đường chạy hiệu năng cao mà chưa đo:** SpEL compiler không hỗ trợ biên dịch expression chứa projection.

## 13. Ghi nhớ nhanh

- Collection projection dùng cú pháp **collection.![projectionExpression]**.
- Projection đánh giá expression cho từng phần tử và tạo collection kết quả mới.
- Có thể lấy property, property lồng nhau, gọi method được phép hoặc tính giá trị mới.
- Trong projection, **#this** là phần tử hiện tại; **#root** vẫn là root context object.
- Projection hỗ trợ array, Iterable và Map.
- Với Map, projection chạy trên từng Map.Entry và trả về List kết quả.
- **?.!** là null-safe projection cho collection nguồn có thể null.
- Safe projection không tự bảo vệ property bên trong expression; dùng safe navigation tại từng điểm có thể null.
- Dùng **.?[...]** để lọc rồi **.![...]** để chuyển đổi phần tử.
- Projection tạo collection mới nhưng không deep-copy object được trả về.
- Dùng projection cho phép chuyển đổi ngắn; dùng Java mapper hoặc Stream khi logic phức tạp hay yêu cầu hiệu năng rõ ràng.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — Safe Navigation for Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — Evaluation and SpEL Compiler Limitations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
