# Projection trên property lồng nhau trong SpEL

Projection trong Spring Expression Language (SpEL) cho phép áp dụng một biểu thức lên từng phần tử của collection và thu kết quả thành một collection mới. Khi property cần lấy nằm sâu trong object graph, projection có thể đi qua nhiều tầng như customer.address.city hoặc product.category.name.

Để dùng đúng projection trên property lồng nhau, cần hiểu đối tượng hiện tại trong mỗi lần lặp, cách phân giải property, cách xử lý null ở từng tầng và hình dạng kết quả khi projection lồng nhau. Bài học này tập trung vào các trường hợp thực tế khi chuyển collection object thành danh sách giá trị hoặc cấu trúc dữ liệu gọn hơn.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Dùng toán tử projection .![] để lấy property từ từng phần tử.
- Truy cập property lồng nhau trong biểu thức projection.
- Hiểu vai trò của #this và phân biệt nó với #root.
- Xử lý object hoặc property trung gian có thể null.
- Tạo projection lồng nhau và nhận biết kết quả dạng list-of-lists.
- Kết hợp selection và projection để lọc rồi biến đổi dữ liệu.
- Tạo map nhỏ cho từng phần tử khi cần nhiều trường đầu ra.
- Đánh giá projection bằng Java và kiểm thử các trường hợp dữ liệu biên.

Bạn nên biết collection, JavaBean getter, property path, biến SpEL và cách dùng SpelExpressionParser cùng EvaluationContext.

## 2. Projection là gì?

Projection là thao tác biến đổi từng phần tử của collection bằng một biểu thức. Cú pháp tổng quát:

~~~text
collection.![expression]
~~~

SpEL duyệt collection, đánh giá expression trên từng phần tử rồi tạo collection kết quả. Với một List đầu vào, kết quả projection thông thường là một List mới có một kết quả tương ứng cho mỗi phần tử đầu vào.

Ví dụ, giả sử có danh sách Product và mỗi product có property name:

~~~text
#products.![name]
~~~

Biểu thức trả về danh sách tên sản phẩm. Thay vì nhận các Product object đầy đủ, phần kết quả chỉ chứa giá trị name.

Projection khác selection:

| Thao tác | Cú pháp | Kết quả |
|---|---|---|
| Selection | .?[condition] | Các phần tử gốc thỏa điều kiện |
| Projection | .![expression] | Kết quả expression trên từng phần tử |

Selection lọc phần tử; projection biến đổi phần tử. Hai thao tác có thể kết hợp để chỉ biến đổi những phần tử phù hợp.

## 3. Property lồng nhau trong projection

Giả sử mô hình dữ liệu có cấu trúc:

~~~java
class Order {
    private Customer customer;
    private BigDecimal total;

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

class Customer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

Mỗi Order có customer; mỗi Customer có address; Address có city. Nếu muốn lấy thành phố của tất cả đơn hàng, có thể viết:

~~~text
#orders.![customer.address.city]
~~~

Trong mỗi vòng projection, SpEL lấy customer của Order hiện tại, tiếp tục lấy address rồi đọc city. Kết quả là danh sách city theo thứ tự các phần tử trong collection nguồn.

Ví dụ đầu vào:

| Order | Customer | Address city |
|---|---|---|
| O-100 | An | Hanoi |
| O-101 | Binh | Da Nang |
| O-102 | Chi | Can Tho |

Projection trả về:

~~~text
{'Hanoi', 'Da Nang', 'Can Tho'}
~~~

Cú pháp trên minh họa collection kết quả; kiểu runtime cụ thể phụ thuộc collection và giá trị được projection tạo ra.

### 3.1. Không cần lặp lại tên collection bên trong expression

Trong projection:

~~~text
#orders.![customer.address.city]
~~~

SpEL tự đặt phần tử đang được xử lý làm đối tượng hiện tại. Không cần viết lại #orders.customer.address.city, vì #orders là collection chứ không phải một Order riêng lẻ.

Tên property không có tiền tố được phân giải trên phần tử hiện tại. Nếu muốn tham chiếu rõ ràng, có thể dùng #this:

~~~text
#orders.![#this.customer.address.city]
~~~

Hai cách có cùng ý nghĩa trong ví dụ này. Dùng tên property trực tiếp thường gọn hơn; #this hữu ích khi biểu thức phức tạp hoặc có nhiều ngữ cảnh lồng nhau.

## 4. Hiểu #this và #root trong projection

SpEL cung cấp hai tham chiếu quan trọng:

- #this: đối tượng hiện tại tại vị trí đang được đánh giá.
- #root: root object của EvaluationContext.

Khi projection chạy trên một collection, #this thường là phần tử hiện tại. Trong projection lồng nhau, đối tượng hiện tại thay đổi theo tầng lặp.

Ví dụ:

~~~text
#orders.![#this.customer.address.city]
~~~

Ở projection ngoài, #this là một Order. Khi đọc customer.address.city, các property được phân giải từ Order đó.

Nếu root object là một đối tượng khác và cần truy cập lại nó trong biểu thức, #root vẫn đại diện root object ban đầu. Không nhầm #root với phần tử hiện tại của collection.

Hãy dùng #this để thể hiện rõ ý định khi biểu thức có nhiều tầng collection hoặc khi một tên property có thể gây nhầm lẫn với property của root object.

## 5. Null trong property path lồng nhau

Property lồng nhau có thể thiếu dữ liệu. Ví dụ Order tồn tại nhưng customer null, hoặc customer tồn tại nhưng address null. Truy cập thông thường:

~~~text
#orders.![customer.address.city]
~~~

có thể phát sinh lỗi khi một mắt xích trung gian null.

Dùng null-safe navigation tại từng tầng có thể null:

~~~text
#orders.![customer?.address?.city]
~~~

Nếu chính phần tử Order có thể null, bảo vệ cả phần tử hiện tại:

~~~text
#orders.![#this?.customer?.address?.city]
~~~

Mỗi dấu ?. bảo vệ receiver ngay trước nó. Nếu customer null, biểu thức trả null cho nhánh đó; nếu address null, bước đọc city trả null. Kết quả projection vẫn có vị trí tương ứng với phần tử nguồn, và giá trị tại vị trí đó có thể là null.

### 5.1. Null ở collection nguồn là tình huống riêng

Null-safe navigation bên trong expression không tự bảo vệ collection nguồn. Nếu orders null, biểu thức #orders.![...] vẫn không thể bắt đầu projection.

Có thể kiểm tra collection trước:

~~~text
#orders != null ? #orders.![customer?.address?.city] : null
~~~

Cách này trả null khi collection nguồn null. Nếu nghiệp vụ muốn collection rỗng thay cho null, hãy chọn giá trị mặc định có chủ đích và bảo đảm kiểu kết quả phù hợp.

Spring Framework 6.2 trở lên hỗ trợ null-safe projection trực tiếp trên collection bằng cú pháp:

~~~text
#orders?.![customer?.address?.city]
~~~

Cú pháp này bảo vệ collection receiver. Các dấu ?. bên trong projection vẫn cần thiết để bảo vệ customer và address nếu chúng có thể null. Với phiên bản Spring cũ hơn, hãy dùng guard tường minh trước projection.

### 5.2. Null khác với property không tồn tại

Null-safe navigation xử lý receiver có giá trị null. Nó không sửa tên property sai hoặc tạo property không tồn tại. Nếu model không có getter/accessor cho city, biểu thức vẫn có thể thất bại. Hãy phân biệt dữ liệu null với lỗi cấu trúc object hoặc lỗi truy cập.

## 6. Projection lồng nhau

Một phần tử có thể chứa collection con. Ví dụ mỗi Order có một List LineItem, và mỗi LineItem có sku.

Có thể lấy danh sách SKU của từng đơn hàng bằng projection lồng nhau:

~~~text
#orders.![items.![sku]]
~~~

Projection ngoài chạy trên từng Order. Projection trong chạy trên items của Order hiện tại. Kết quả là một collection lồng nhau:

~~~text
[
  ['SKU-A', 'SKU-B'],
  ['SKU-C'],
  ['SKU-D', 'SKU-E', 'SKU-F']
]
~~~

Đây là list-of-lists: mỗi danh sách con tương ứng một đơn hàng. Projection không tự flatten các collection con thành một danh sách duy nhất.

Nếu cần bảo vệ các tầng null:

~~~text
#orders.![items?.![sku]]
~~~

Trên Spring Framework 6.2 trở lên, ?. trước projection con bảo vệ items null. Nếu LineItem có thể null hoặc sku nằm trong property path sâu hơn, tiếp tục dùng #this?.property hoặc safe navigation tại các mắt xích cần thiết.

### 6.1. Khi cần flatten kết quả

Nếu mục tiêu là một danh sách SKU phẳng, hãy thực hiện flatten ở Java sau khi projection, hoặc dùng Java Stream để map rồi flatMap. Không giả định .![] sẽ tự gộp collection con.

Ví dụ Java:

~~~java
List<String> allSkus = orders.stream()
    .filter(Objects::nonNull)
    .filter(order -> order.getItems() != null)
    .flatMap(order -> order.getItems().stream())
    .filter(Objects::nonNull)
    .map(LineItem::getSku)
    .toList();
~~~

Java thể hiện rõ cách xử lý null và flatten. Nếu logic cần nhiều bước biến đổi, lọc và xử lý lỗi, Stream hoặc vòng lặp Java thường dễ đọc hơn một expression SpEL lồng sâu.

## 7. Kết hợp selection và projection

Một use case phổ biến là lọc collection trước rồi mới lấy property lồng nhau.

Ví dụ chỉ lấy city của các đơn hàng đã thanh toán:

~~~text
#orders.?[status == 'PAID'].![customer?.address?.city]
~~~

Thao tác đầu tiên:

~~~text
#orders.?[status == 'PAID']
~~~

giữ lại các Order có status là PAID.

Thao tác thứ hai:

~~~text
.![customer?.address?.city]
~~~

lấy city của customer cho từng đơn hàng đã lọc.

Có thể lọc theo property lồng nhau:

~~~text
#orders.?[customer != null and customer.active].![customer.address.city]
~~~

Trong predicate, #this là Order hiện tại. Điều kiện customer != null được đặt trước customer.active để AND short-circuit bảo vệ truy cập property.

Nếu address cũng có thể null, hãy viết projection với safe navigation:

~~~text
#orders.?[customer != null and customer.active].![customer?.address?.city]
~~~

Selection giữ lại object gốc; projection tạo giá trị mới từ các object đó.

## 8. Tạo cấu trúc đầu ra bằng map trong projection

Projection không bắt buộc chỉ trả về một property. Expression bên trong .![] có thể là một biểu thức phức tạp, kể cả map inline.

Ví dụ muốn tạo một summary cho mỗi Order:

~~~text
#orders.![{
    'orderNumber': number,
    'city': customer?.address?.city,
    'total': total
}]
~~~

Mỗi phần tử kết quả là một map có ba key. Cấu trúc đầu ra có dạng:

~~~text
[
  {'orderNumber': 'O-100', 'city': 'Hanoi', 'total': 120},
  {'orderNumber': 'O-101', 'city': null, 'total': 80}
]
~~~

Cách này hữu ích khi cần tạo dữ liệu trình bày nhỏ hoặc truyền kết quả sang một bước xử lý tiếp theo. Key trong map inline là chuỗi literal; value được đánh giá trên Order hiện tại.

Nếu cấu trúc kết quả ổn định và được dùng rộng rãi trong ứng dụng, hãy cân nhắc tạo DTO có kiểu trong Java thay vì truyền Map<String, Object>.

## 9. Đánh giá projection bằng Java

Ví dụ tạo parser và truyền collection vào context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression(
        "#orders.![customer?.address?.city]"
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);

List<?> cities =
    expression.getValue(context, List.class);
~~~

Biến orders có thể chứa các Order object. Projection đọc property trên từng phần tử và trả collection các city.

Nếu muốn lấy một property sâu hơn, chỉ cần thay expression:

~~~java
#orders.![customer?.address?.city]
~~~

Nếu muốn lấy map summary:

~~~java
#orders.![{'number': number, 'city': customer?.address?.city}]
~~~

Dữ liệu được truyền qua biến giúp expression không phụ thuộc vào cách ứng dụng tạo collection. Không cần ghép object hoặc giá trị runtime vào chuỗi biểu thức.

## 10. Projection có thay đổi collection nguồn không?

Projection tạo collection kết quả từ các giá trị được tính trên phần tử nguồn. Bản thân thao tác projection không có nghĩa là cập nhật property của các phần tử nguồn.

Ví dụ:

~~~text
#products.![price * 1.1]
~~~

Biểu thức tính giá mới cho từng phần tử và trả danh sách kết quả. Nó không tự gọi setter để cập nhật price trên Product.

Nếu expression bên trong projection gọi method có tác dụng phụ hoặc dùng toán tử gán, hành vi đó có thể làm thay đổi object. Vì vậy, không nên đưa các thao tác ghi hoặc method có side effect vào projection chỉ đọc. Hãy giữ expression thuần để kết quả dễ dự đoán.

## 11. Kiểu dữ liệu và kết quả projection

Kết quả của projection phụ thuộc vào expression bên trong:

| Expression | Giá trị của mỗi phần tử kết quả |
|---|---|
| .![name] | Giá trị name |
| .![total > 100] | Boolean |
| .![price * quantity] | Kết quả phép tính |
| .![customer?.address?.city] | City hoặc null |
| .![{'id': id, 'name': name}] | Map cho mỗi phần tử |
| .![items.![sku]] | Collection con cho mỗi phần tử |

Khi dùng getValue(context, List.class), các phần tử trong List vẫn có thể có kiểu khác nhau nếu expression trả về nhiều loại value. Hãy kiểm tra kiểu trước khi ép kiểu và xác định hợp đồng dữ liệu của kết quả.

Nếu kết quả là list-of-lists, đừng ép trực tiếp thành List<String>. Nếu kết quả là map, hãy kiểm tra key và value trước khi sử dụng.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Property lồng nhau phát sinh lỗi | Một object trung gian null | Dùng ?. tại từng tầng nullable |
| Collection nguồn null | Projection bắt đầu trên null | Guard collection hoặc dùng null-safe projection trên Spring 6.2+ |
| Phần tử nguồn null | Property được truy cập trên phần tử null | Dùng #this?.property trong expression |
| Property không được tìm thấy | Sai tên hoặc accessor không hỗ trợ | Kiểm tra model và getter/accessor |
| Kết quả có nhiều list con | Projection lồng nhau giữ cấu trúc phân cấp | Flatten bằng Java nếu cần danh sách phẳng |
| Kết quả chứa null | Một property path trả về null | Quy định rõ giữ null, lọc bỏ hay thay default |
| Dữ liệu nguồn bị thay đổi | Expression gọi method có side effect hoặc phép gán | Giữ projection chỉ đọc và chuyển cập nhật sang Java |
| Biểu thức quá khó đọc | Nhiều tầng collection và property lồng nhau | Chia thành các bước Java hoặc tạo DTO |

Khi debug, hãy thử projection trên một property đơn giản trước, sau đó thêm từng tầng property. Tiếp theo thử với phần tử null, property trung gian null và collection con null để xác định chính xác ranh giới gây lỗi.

## 13. Bài tập thực hành

1. Tạo List Product có name và category.name. Dùng projection lấy tên category của từng product.
2. Tạo List Order có customer.address.city. Lấy danh sách city bằng projection lồng nhau.
3. Đặt customer null ở một Order và thử biểu thức có safe navigation.
4. Đặt một phần tử Order null và bảo vệ bằng #this?.
5. Tạo Order có List LineItem; dùng projection lồng nhau để lấy SKU theo từng đơn.
6. Kết hợp selection để chỉ lấy city của đơn hàng đã thanh toán.
7. Tạo map summary cho mỗi Order gồm orderNumber, city và total.
8. So sánh list-of-lists từ projection lồng nhau với kết quả flatten bằng Java Stream.
9. Kiểm tra collection nguồn null, collection rỗng và collection có phần tử null.
10. Xác nhận projection không cập nhật property nguồn khi expression chỉ đọc.

## 14. Checklist trước khi dùng projection trên property lồng nhau

- [ ] Collection nguồn có tồn tại không?
- [ ] Đã xác định phần tử hiện tại trong projection chưa?
- [ ] Đường dẫn property có đúng với model và accessor không?
- [ ] Đã bảo vệ từng object trung gian có thể null chưa?
- [ ] Phần tử collection có thể null không?
- [ ] Collection con có thể null hoặc rỗng không?
- [ ] Kết quả là list giá trị, list map hay list-of-lists?
- [ ] Có cần flatten kết quả bằng Java không?
- [ ] Có value nào được tạo bằng map inline không?
- [ ] Expression có gọi method gây side effect hoặc cập nhật object không?
- [ ] Đã kiểm thử dữ liệu đầy đủ, null và collection rỗng chưa?
- [ ] Nếu dùng null-safe projection trên collection, phiên bản Spring có hỗ trợ không?

## 15. Kết luận

Projection .![] cho phép biến đổi từng phần tử collection bằng một biểu thức SpEL. Khi property nằm sâu trong object graph, có thể truy cập trực tiếp như customer.address.city; #this đại diện phần tử hiện tại trong mỗi vòng lặp. Hãy dùng null-safe navigation tại từng tầng có thể null, phân biệt collection null với collection rỗng và nhớ rằng projection lồng nhau tạo list-of-lists chứ không tự flatten. Với biểu thức dài, dữ liệu phức tạp hoặc cần nhiều bước biến đổi, chuyển logic sang Java giúp kiểm soát kiểu, null và hiệu năng rõ ràng hơn.