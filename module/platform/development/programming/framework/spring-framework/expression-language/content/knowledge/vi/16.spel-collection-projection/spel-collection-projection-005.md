# Projection kết hợp với selection trong Spring Expression Language (SpEL)

Trong SpEL, **selection** dùng để lọc phần tử của một collection theo điều kiện, còn **projection** dùng để biến đổi mỗi phần tử thành một giá trị hoặc cấu trúc khác. Kết hợp hai phép toán này giúp biểu thức vừa chọn đúng dữ liệu cần thiết, vừa tạo ra kết quả có hình dạng phù hợp cho bước xử lý tiếp theo.

Một mẫu thường gặp là lọc danh sách đơn hàng đã thanh toán rồi lấy riêng tổng tiền của từng đơn:

~~~text
orders.?[status == 'PAID'].![total]
~~~

Phần selection giữ lại các đơn có status là PAID. Phần projection lấy thuộc tính total từ từng đơn đã được chọn và tạo ra một danh sách các tổng tiền.

Bài này giải thích cú pháp, thứ tự thực hiện, kiểu kết quả, cách áp dụng với List và Map, các biến thể selection, xử lý null và ví dụ Java có thể dùng trong ứng dụng.

## 1. Selection và projection làm hai việc khác nhau

Selection và projection đều thao tác trên collection nhưng có mục tiêu khác nhau.

**Selection** trả lời câu hỏi: phần tử nào được giữ lại?

~~~text
orders.?[total >= 100]
~~~

Biểu thức trên giữ lại những đơn hàng có total lớn hơn hoặc bằng 100.

**Projection** trả lời câu hỏi: từ mỗi phần tử, cần lấy hoặc tính ra giá trị nào?

~~~text
orders.![total]
~~~

Biểu thức trên tạo một danh sách mới chứa total của từng đơn hàng.

Có thể hình dung:

| Phép toán | Đầu vào | Kết quả |
|---|---|---|
| Selection | Collection và điều kiện Boolean | Collection gồm những phần tử thỏa điều kiện |
| Projection | Collection và biểu thức biến đổi | Collection gồm kết quả của biểu thức trên từng phần tử |

Selection quyết định phần tử nào được đưa tiếp vào kết quả. Projection quyết định dữ liệu nào được tạo ra từ mỗi phần tử.

## 2. Cú pháp selection trong SpEL

Selection dùng dấu hỏi chấm sau dấu chấm, theo sau là biểu thức điều kiện trong ngoặc vuông:

~~~text
collection.?[selectionExpression]
~~~

SpEL đánh giá điều kiện trên từng phần tử của collection. Trong lúc đánh giá điều kiện, phần tử hiện tại trở thành đối tượng hiện hành và có thể được truy cập qua các property của nó hoặc qua biến đặc biệt #this.

Ví dụ:

~~~text
customers.?[active]
customers.?[age >= 18]
customers.?[country == 'VN' and verified]
customers.?[#this.age >= 18]
~~~

Các biểu thức trên lần lượt lọc khách hàng đang active, đủ tuổi, thuộc quốc gia VN và đã xác minh, hoặc đủ tuổi bằng cách tham chiếu tường minh #this.

Điều kiện selection phải tạo ra kết quả Boolean phù hợp. Nếu biểu thức điều kiện tham chiếu property không tồn tại hoặc tạo ra kiểu không thể dùng như Boolean, quá trình đánh giá có thể phát sinh lỗi.

### 2.1. Selection lấy tất cả phần tử phù hợp

Toán tử .?[...] giữ lại tất cả phần tử có điều kiện đúng.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customers.?[active]");

List<?> activeCustomers =
        expression.getValue(context, List.class);
~~~

Nếu collection đầu vào là List, kết quả selection là collection chứa các phần tử phù hợp theo thứ tự gặp trong danh sách. Các phần tử được giữ lại là chính đối tượng ban đầu, chưa bị biến đổi thành property khác.

### 2.2. Selection lấy phần tử đầu tiên hoặc cuối cùng

SpEL còn cung cấp hai biến thể:

| Cú pháp | Ý nghĩa |
|---|---|
| .?[...] | Lấy tất cả phần tử phù hợp |
| .^[...] | Lấy phần tử phù hợp đầu tiên |
| .$[...] | Lấy phần tử phù hợp cuối cùng |

Ví dụ:

~~~text
orders.^[status == 'PAID']
orders.$[status == 'PAID']
~~~

Biểu thức đầu tiên trả về đơn hàng đầu tiên có status là PAID. Biểu thức thứ hai trả về đơn hàng cuối cùng có status đó.

Với selection đầu tiên hoặc cuối cùng, kết quả là một phần tử thay vì một collection. Nếu không tìm thấy phần tử phù hợp, kết quả là null. Vì vậy, mã Java cần xử lý trường hợp không có kết quả.

## 3. Cú pháp projection trong SpEL

Projection dùng dấu chấm than sau dấu chấm, theo sau là biểu thức trong ngoặc vuông:

~~~text
collection.![projectionExpression]
~~~

SpEL đánh giá biểu thức projection cho từng phần tử và thu thập các kết quả thành một List.

Ví dụ:

~~~text
customers.![name]
orders.![total]
products.![price * quantity]
~~~

Các biểu thức lần lượt tạo danh sách tên khách hàng, tổng tiền của từng đơn và giá trị price nhân quantity của từng sản phẩm.

Trong projection, #this tham chiếu phần tử đang được xử lý. Vì vậy, hai biểu thức sau có cùng ý nghĩa:

~~~text
orders.![total]
orders.![#this.total]
~~~

Projection thường tạo List kết quả ngay cả khi biểu thức bên trong trả về một kiểu đơn giản như String, Integer hoặc Boolean. Mỗi phần tử trong List là kết quả của biểu thức projection tương ứng.

### 3.1. Projection tạo dữ liệu mới, không thay đổi phần tử nguồn

Giả sử mỗi Customer có name và age. Projection:

~~~text
customers.![name]
~~~

tạo danh sách các tên. Nó không xóa age khỏi Customer và cũng không sửa các đối tượng nguồn.

Tương tự, projection:

~~~text
orders.![total * 1.1]
~~~

tính một giá trị mới cho mỗi đơn hàng. Biểu thức không tự gán kết quả ngược lại vào property total.

Nếu cần thay đổi property của đối tượng, đó là thao tác ghi property bằng API hoặc biểu thức gán phù hợp; projection chỉ tạo kết quả từ các phần tử được duyệt.

## 4. Kết hợp selection rồi projection

Khi muốn lọc collection trước, sau đó chỉ lấy một phần dữ liệu từ các phần tử còn lại, nối hai toán tử:

~~~text
collection.?[condition].![projectionExpression]
~~~

Ví dụ:

~~~text
orders.?[status == 'PAID'].![total]
~~~

SpEL thực hiện theo trình tự:

1. Đọc collection orders.
2. Selection đánh giá status == 'PAID' trên từng đơn hàng.
3. Giữ lại các đơn thỏa điều kiện.
4. Projection đánh giá total trên từng đơn đã chọn.
5. Trả về List các giá trị total.

Ví dụ khác:

~~~text
customers.?[active and age >= 18].![name]
~~~

Biểu thức chỉ lấy tên của khách hàng đang active và từ 18 tuổi trở lên.

Nếu không có phần tử nào thỏa điều kiện, selection tạo collection rỗng và projection trên collection rỗng cũng cho kết quả rỗng. Ứng dụng có thể xử lý kết quả này như một danh sách không có phần tử.

## 5. Kết hợp projection rồi selection

Có thể áp dụng projection trước rồi selection sau:

~~~text
collection.![projectionExpression].?[condition]
~~~

Trong trường hợp này, selection làm việc trên các giá trị do projection tạo ra, thay vì trên các đối tượng nguồn ban đầu.

Ví dụ, lấy điểm số rồi chỉ giữ các điểm từ 80 trở lên:

~~~text
students.![score].?[#this >= 80]
~~~

Thứ tự này khác với:

~~~text
students.?[score >= 80].![score]
~~~

Biểu thức đầu tiên chiếu mỗi Student thành một giá trị score rồi lọc các giá trị số. Biểu thức thứ hai lọc các Student theo score rồi chiếu những Student còn lại thành score.

Nếu chỉ cần một danh sách điểm đạt yêu cầu, hai biểu thức có thể tạo giá trị tương tự. Nhưng nếu cần dùng thêm property khác của Student trong điều kiện lọc, selection trước projection sẽ giữ nguyên đối tượng nguồn để điều kiện truy cập các property đó.

Ví dụ:

~~~text
students.?[score >= 80 and active].![name]
~~~

Cách này rõ ràng hơn nếu yêu cầu là lọc theo cả score và active, sau đó trả về name.

## 6. Ví dụ Java: lọc đơn hàng rồi lấy tổng tiền

Tạo lớp Order đơn giản:

~~~java
public class Order {
    private final String code;
    private final String status;
    private final BigDecimal total;

    public Order(String code, String status, BigDecimal total) {
        this.code = code;
        this.status = status;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Tạo đối tượng chứa collection:

~~~java
public class OrderReport {
    private final List<Order> orders;

    public OrderReport(List<Order> orders) {
        this.orders = orders;
    }

    public List<Order> getOrders() {
        return orders;
    }
}
~~~

Chuẩn bị dữ liệu và đánh giá biểu thức:

~~~java
List<Order> orders = Arrays.asList(
        new Order("A-100", "PAID", new BigDecimal("120.00")),
        new Order("A-101", "PENDING", new BigDecimal("80.00")),
        new Order("A-102", "PAID", new BigDecimal("250.00"))
);

OrderReport report = new OrderReport(orders);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID'].![total]"
);

List<?> paidTotals = expression.getValue(report, List.class);
~~~

Kết quả là danh sách gồm 120.00 và 250.00. Đơn hàng A-101 không xuất hiện vì status của nó là PENDING.

Nếu ứng dụng muốn lấy mã đơn thay vì tổng tiền, chỉ cần thay projection expression:

~~~text
orders.?[status == 'PAID'].![code]
~~~

Selection vẫn giữ nguyên; projection quyết định trường dữ liệu được trả về.

## 7. Ví dụ Java: lọc theo nhiều điều kiện rồi tạo object kết quả

Projection không chỉ lấy một property. Nó có thể tạo một cấu trúc kết quả khác, chẳng hạn inline map cho mỗi phần tử:

~~~text
orders.?[status == 'PAID'].![{'code': code, 'amount': total}]
~~~

Kết quả là một List các Map. Mỗi map chứa code và amount của một đơn đã thanh toán.

Có thể dùng cấu trúc này để tạo dữ liệu phục vụ báo cáo hoặc chuyển tiếp sang tầng xử lý khác:

~~~java
Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID']."
        + "![{'code': code, 'amount': total}]"
);

List<?> rows = expression.getValue(report, List.class);
~~~

Mỗi phần tử của rows là một Map. Khi nhận dữ liệu, nên dùng List<?> và kiểm tra kiểu từng phần tử nếu cấu trúc biểu thức có thể thay đổi.

Projection cũng có thể tính giá trị:

~~~text
orders.?[status == 'PAID'].![total * 1.1]
~~~

Biểu thức tạo tổng tiền đã nhân hệ số 1.1 cho từng đơn được chọn. Đây chỉ là giá trị tính toán trong kết quả, không cập nhật total trên Order.

## 8. Selection và projection trên Map

SpEL cũng hỗ trợ selection trên Map. Khi selection xử lý một Map, điều kiện được đánh giá trên từng Map.Entry. Có thể truy cập key và value của entry hiện tại.

Ví dụ:

~~~text
scores.?[value >= 80]
~~~

Biểu thức giữ lại các entry có value từ 80 trở lên. Kết quả selection trên Map vẫn là Map, giữ nguyên key và value của các entry được chọn.

Projection trên Map xử lý từng entry và tạo List kết quả:

~~~text
scores.![key]
scores.![value]
scores.![key + ':' + value]
~~~

Các biểu thức tạo danh sách key, danh sách value hoặc danh sách chuỗi kết hợp key và value.

Có thể kết hợp selection và projection:

~~~text
scores.?[value >= 80].![key]
~~~

Kết quả là danh sách key của những entry có điểm từ 80 trở lên.

Ví dụ Java:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 92);
scores.put("Binh", 75);
scores.put("Chi", 86);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression = parser.parseExpression(
        "#scores.?[value >= 80].![key]"
);

List<?> qualifiedNames = expression.getValue(context, List.class);
~~~

Với dữ liệu trên, qualifiedNames chứa An và Chi. Dùng LinkedHashMap giúp ví dụ giữ thứ tự chèn khi duyệt.

## 9. Kết quả và kiểu dữ liệu khi kết hợp hai phép toán

Kiểu kết quả phụ thuộc collection đầu vào và loại selection/projection được sử dụng.

| Biểu thức | Kết quả |
|---|---|
| list.?[condition] | List các phần tử nguồn thỏa điều kiện |
| list.^[condition] | Một phần tử nguồn đầu tiên thỏa điều kiện hoặc null |
| list.$[condition] | Một phần tử nguồn cuối cùng thỏa điều kiện hoặc null |
| list.![expression] | List các giá trị được chiếu |
| list.?[condition].![expression] | List các giá trị chiếu từ phần tử đã chọn |
| map.?[condition] | Map giữ các entry thỏa điều kiện |
| map.![expression] | List kết quả projection trên từng entry |
| map.?[condition].![expression] | List kết quả projection từ các entry đã chọn |

Nếu đầu vào là collection rỗng, selection giữ lại không phần tử nào và projection tạo List rỗng. Nếu đầu vào là null, thao tác selection hoặc projection thông thường có thể phát sinh lỗi khi đánh giá; dùng safe navigation khi dữ liệu có thể null.

Selection và projection không tự đảm bảo generic type như List<String> ở runtime. Trong Java, nhận List<?> trước rồi kiểm tra hoặc chuyển đổi phần tử nếu cần một kiểu cụ thể.

## 10. Xử lý null và safe navigation

Một collection có thể null, hoặc property được truy cập trong điều kiện selection có thể null. Cần phân biệt hai tình huống.

**Collection đầu vào null:** safe navigation có thể ngăn việc thực hiện selection hoặc projection trên collection null.

~~~text
orders?.?[status == 'PAID']
orders?.![total]
~~~

Nếu orders là null, biểu thức safe navigation trả về null thay vì cố duyệt collection.

**Property của phần tử null:** safe navigation có thể được dùng khi truy cập property lồng nhau. Ví dụ:

~~~text
customers.?[address?.city == 'Hanoi'].![name]
~~~

Biểu thức dùng safe navigation khi đọc city từ address. Cần xác định rõ cách xử lý null theo yêu cầu nghiệp vụ; một giá trị null không nên được mặc định coi là thỏa điều kiện.

Có thể kết hợp safe navigation trên cả selection và projection:

~~~text
orders?.?[status == 'PAID']?.![total]
~~~

Kết quả có thể là null nếu collection gốc null, hoặc một List nếu collection tồn tại. Do đó, mã Java nhận kết quả nên kiểm tra null trước khi duyệt.

## 11. Các biến thể selection khi kết hợp projection

Selection đầu tiên và cuối cùng có thể kết hợp với projection nếu muốn lấy một giá trị từ phần tử được chọn:

~~~text
orders.^[status == 'PAID']?.total
orders.$[status == 'PAID']?.total
~~~

Các biểu thức này lấy total của đơn PAID đầu tiên hoặc cuối cùng. Nếu không có đơn phù hợp, kết quả selection là null; safe navigation ?.total tránh truy cập property trên null.

Nếu cần danh sách tổng tiền của tất cả đơn đã thanh toán, dùng:

~~~text
orders.?[status == 'PAID'].![total]
~~~

Hãy chọn toán tử theo hình dạng kết quả cần nhận: một phần tử, một property đơn lẻ hoặc một collection mới.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng .![] khi muốn lọc | Projection biến đổi mọi phần tử, không loại phần tử theo điều kiện. | Dùng .?[] cho selection. |
| Dùng .?[] khi muốn chỉ lấy một property | Selection giữ đối tượng nguồn. | Nối .![] để projection property cần lấy. |
| Đảo thứ tự selection và projection | Điều kiện sau projection làm việc trên giá trị mới, không còn đối tượng nguồn ban đầu. | Lọc trước nếu điều kiện cần nhiều property của phần tử. |
| Quên #this trong biểu thức cần tham chiếu tường minh | Có thể gây nhầm đối tượng hiện hành trong biểu thức lồng nhau. | Dùng #this.property khi cần rõ ngữ cảnh. |
| Dùng .^[...] nhưng mong nhận List | Selection đầu tiên trả về một phần tử hoặc null. | Dùng .?[...] nếu cần collection. |
| Selection trên Map nhưng truy cập sai key/value | Phần tử hiện hành là Map.Entry. | Dùng key và value của entry. |
| Gọi property trên kết quả selection null | Không tìm thấy phần tử phù hợp. | Dùng safe navigation hoặc kiểm tra null. |
| Collection đầu vào có thể null | Selection/projection có thể thất bại khi duyệt null. | Dùng safe navigation và xử lý kết quả null ở Java. |
| Ép kiểu kết quả sang List<T> mà không kiểm tra | Generic type không được xác minh chỉ bằng List.class. | Nhận List<?> rồi xác nhận từng phần tử. |
| Nghĩ projection sửa đối tượng nguồn | Projection chỉ tạo kết quả từ biểu thức, không tự gán lại property. | Dùng thao tác ghi riêng nếu cần cập nhật dữ liệu. |

## 13. Cách tổ chức biểu thức dễ đọc

Với biểu thức dài, nên chia thành các nhóm có ý nghĩa:

~~~text
orders
    .?[status == 'PAID' and total >= 100]
    .![{'code': code, 'amount': total}]
~~~

Trong mã Java, có thể đặt biểu thức trên nhiều dòng trong chuỗi ghép hoặc lưu vào cấu hình riêng. Hãy đặt tên biến và property có ý nghĩa để điều kiện selection và biểu thức projection dễ hiểu.

Một vài nguyên tắc thực hành:

1. Selection trước projection khi cần lọc dựa trên các property của đối tượng nguồn.
2. Projection trước selection khi điều kiện lọc áp dụng trên giá trị đã được biến đổi.
3. Dùng ngoặc khi biểu thức điều kiện có nhiều toán tử logic.
4. Dùng #this để làm rõ phần tử hiện hành trong biểu thức lồng nhau.
5. Xử lý null cho collection và property lồng nhau.
6. Dùng kiểu nhận kết quả tổng quát rồi kiểm tra kiểu phần tử tại ranh giới Java khi cần.
7. Tách biểu thức phức tạp thành các biến hoặc bước xử lý dễ kiểm tra nếu nó trở nên khó đọc.

## 14. Ghi nhớ

- Selection dùng .?[condition] để giữ các phần tử phù hợp.
- .^[condition] lấy phần tử phù hợp đầu tiên; .$[condition] lấy phần tử cuối cùng.
- Projection dùng .![expression] để tạo List từ kết quả biểu thức trên từng phần tử.
- Selection rồi projection có dạng collection.?[condition].![expression].
- Projection rồi selection lọc trên các giá trị đã được biến đổi, nên có thể khác về ngữ nghĩa.
- Selection trên Map giữ các entry phù hợp; projection trên Map tạo List kết quả.
- Safe navigation hữu ích khi collection hoặc property có thể null.
- Selection/projection tạo kết quả mới; projection không tự sửa property của phần tử nguồn.
- Kiểm tra kiểu kết quả và null trước khi dùng trong mã Java.
