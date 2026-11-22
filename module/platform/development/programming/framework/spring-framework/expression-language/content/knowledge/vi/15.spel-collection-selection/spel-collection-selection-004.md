# Selection trả về list kết quả

SpEL cung cấp toán tử selection để lọc các phần tử của một collection theo điều kiện. Khi nguồn là List, selection trả về một List mới chứa những phần tử thỏa mãn predicate. Cách viết này hữu ích khi cần chọn các đơn hàng đang mở, người dùng còn hoạt động, dòng hàng có số lượng lớn hơn một hoặc bất kỳ tập con nào của dữ liệu hiện có.

Selection chỉ quyết định phần tử nào được giữ lại. Nó không biến đổi từng phần tử như projection, cũng không tự sắp xếp hoặc thay đổi dữ liệu gốc. Hiểu rõ kết quả là một List mới, cách predicate được đánh giá và phạm vi của #this giúp biểu thức dễ dự đoán hơn.

## 1. Cú pháp selection trên List

Cú pháp selection tổng quát:

~~~text
collection.?[selectionExpression]
~~~

Dấu chấm trước toán tử cho biết selection được thực hiện trên collection. Phần trong ngoặc vuông là điều kiện được đánh giá cho từng phần tử. Chỉ những phần tử có điều kiện đúng mới được đưa vào kết quả.

Ví dụ:

~~~text
orders.?[status == 'PAID']
users.?[active == true]
products.?[price > 100]
numbers.?[#this > 10]
~~~

Nếu orders là List đơn hàng, biểu thức đầu trả về một List gồm các đơn có status là PAID. Nếu không có phần tử nào phù hợp, kết quả là List rỗng.

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = List.of(
        new Order("A-01", "PAID"),
        new Order("A-02", "PENDING"),
        new Order("A-03", "PAID")
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);

Expression expression = parser.parseExpression(
        "#orders.?[status == 'PAID']"
);

List<?> paidOrders = expression.getValue(context, List.class);

System.out.println(paidOrders.size()); // 2
~~~

Trong ví dụ, #orders lấy List từ biến context. Selection duyệt từng phần tử, kiểm tra property status rồi đưa các đơn phù hợp vào List kết quả.

## 2. Predicate được đánh giá trên từng phần tử

Biểu thức bên trong ngoặc vuông là predicate. SpEL đánh giá predicate với từng phần tử làm đối tượng hiện tại.

Với một List các object, có thể truy cập property trực tiếp:

~~~text
#orders.?[total >= 100]
#users.?[enabled and verified]
#products.?[category == 'BOOK']
~~~

Trong predicate, tên property như total, enabled hoặc category được phân giải trên phần tử đang xét. Không cần lặp lại đường dẫn collection ở mỗi điều kiện.

Ví dụ, nếu một phần tử là Order, biểu thức total >= 100 được đánh giá trên Order hiện tại. Nếu phần tử kế tiếp có total nhỏ hơn 100, nó không được đưa vào kết quả.

Predicate nên trả về giá trị Boolean rõ ràng. Hãy viết điều kiện đủ cụ thể để người đọc biết chính xác tiêu chí chọn phần tử nào được giữ lại.

## 3. Vai trò của #this và #root

SpEL cung cấp hai tham chiếu hữu ích khi selection đang duyệt collection:

- #this trỏ đến phần tử hiện tại mà predicate đang kiểm tra.
- #root trỏ đến đối tượng gốc của toàn bộ lượt đánh giá.

Ví dụ:

~~~text
#orders.?[#this.total >= 100]
~~~

Ở đây #this là từng Order trong List. Cách viết tường minh này hữu ích khi predicate có nhiều property hoặc khi cần phân biệt phần tử hiện tại với một object khác.

Giả sử root object là một Customer có danh sách orders và mã khách hàng:

~~~text
orders.?[#this.customerId == #root.id]
~~~

Trong predicate, #this là từng đơn hàng; #root vẫn là Customer ban đầu. Nhờ vậy, có thể lọc collection con dựa trên dữ liệu của object gốc.

Khi selection được lồng nhau, #this thay đổi theo collection đang được xử lý ở cấp hiện tại. Hãy dùng #root khi cần tham chiếu lại object gốc, đặc biệt nếu nhiều cấp collection có property trùng tên.

## 4. Kết quả selection là List mới

Với đầu vào là List, toán tử .?[...] trả về List chứa các phần tử phù hợp. Kết quả là collection mới; selection không xóa các phần tử không phù hợp khỏi List ban đầu.

Ví dụ:

~~~java
List<Integer> source = List.of(1, 2, 3, 4, 5);

context.setVariable("numbers", source);

Expression expression =
        parser.parseExpression("#numbers.?[#this % 2 == 0]");

List<?> evenNumbers = expression.getValue(context, List.class);

System.out.println(evenNumbers); // [2, 4]
System.out.println(source);      // [1, 2, 3, 4, 5]
~~~

List nguồn vẫn giữ nguyên các phần tử. Selection chỉ tạo tập kết quả để biểu thức hoặc code Java sử dụng tiếp.

Các phần tử được giữ theo thứ tự duyệt của List nguồn. Nếu nguồn chứa cùng một object nhiều lần và mỗi lần đều thỏa predicate, các lần xuất hiện đó vẫn được giữ trong kết quả. Selection không tự loại bỏ phần tử trùng lặp.

Kết quả chứa các reference tới phần tử đã chọn. Nếu phần tử là object mutable, thay đổi thuộc tính của object thông qua reference đó vẫn có thể ảnh hưởng tới object ban đầu. Việc tạo List kết quả mới không đồng nghĩa với sao chép sâu các phần tử.

## 5. Không có phần tử phù hợp

Nếu không có phần tử nào thỏa điều kiện, selection trên List trả về List rỗng:

~~~text
#orders.?[status == 'CANCELLED']
~~~

Không nên giả định kết quả là null chỉ vì không có kết quả phù hợp. Một List rỗng vẫn là một collection hợp lệ và có thể dùng để kiểm tra size, isEmpty hoặc lặp qua mà không có phần tử.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "#orders.?[status == 'CANCELLED']"
);

List<?> cancelled = expression.getValue(context, List.class);

if (cancelled.isEmpty()) {
    System.out.println("Không có đơn bị hủy");
}
~~~

Nếu ứng dụng cần một giá trị thay thế khi không tìm thấy phần tử, hãy xử lý rõ ràng sau selection hoặc dùng điều kiện bổ sung trong biểu thức. Đừng nhầm List rỗng với collection nguồn null.

## 6. Kết hợp nhiều điều kiện trong predicate

Predicate có thể kết hợp các phép so sánh và toán tử logic. Ví dụ:

~~~text
#orders.?[status == 'PAID' and total >= 100]
#users.?[active and (role == 'ADMIN' or role == 'EDITOR')]
#products.?[stock > 0 and price <= #maxPrice]
~~~

Có thể dùng ngoặc để làm rõ các nhóm điều kiện. AND và OR có short-circuit: nếu vế trái của AND là false, phần còn lại không cần đánh giá; nếu vế trái của OR là true, vế phải bị bỏ qua.

Điều này hữu ích khi cần kiểm tra null trước khi truy cập sâu:

~~~text
#users.?[#this.profile != null and #this.profile.enabled]
~~~

Nếu profile là null, vế phải không được đánh giá. Cách viết này tránh truy cập enabled trên một object null.

Khi predicate có nhiều điều kiện, hãy ưu tiên những kiểm tra đơn giản, có thể quyết định kết quả sớm ở bên trái. Điều đó vừa làm rõ ý định vừa tránh thực hiện các truy cập không cần thiết.

## 7. Truy cập property lồng nhau trong predicate

Có thể lọc theo thuộc tính ở nhiều cấp của object:

~~~text
#orders.?[customer.address.city == 'Da Nang']
#employees.?[department.name == 'Engineering']
#products.?[supplier.active == true]
~~~

Mỗi đường dẫn property được đánh giá trên phần tử hiện tại. Nếu một object trung gian là null, việc truy cập property tiếp theo có thể gây lỗi.

Hãy kiểm tra object trung gian trước khi đọc sâu:

~~~text
#employees.?[department != null and department.name == 'Engineering']
~~~

Do AND short-circuit, nếu department là null thì department.name không được truy cập.

Với object graph phức tạp, nên chuẩn bị dữ liệu có trạng thái rõ ràng hoặc dùng DTO phục vụ biểu thức. Predicate càng phụ thuộc nhiều getter và quan hệ lồng nhau thì càng khó dự đoán hiệu năng và lỗi runtime.

## 8. Selection lồng nhau

Một phần tử của List có thể chứa một List khác. Có thể thực hiện selection ở nhiều cấp để lọc collection ngoài rồi lọc tiếp collection con.

Ví dụ, mỗi Order có một danh sách lines:

~~~text
#orders.?[status == 'PAID'].![lines.?[quantity > 1]]
~~~

Biểu thức trên trước tiên chọn các đơn đã thanh toán, sau đó projection từng đơn thành List các dòng có quantity lớn hơn một. Kết quả ở đây là collection các List con vì projection tạo một giá trị cho mỗi đơn hàng đã chọn.

Nếu mục tiêu chỉ là chọn các đơn có ít nhất một dòng phù hợp, có thể dùng method anyMatch hoặc một method nghiệp vụ có tên rõ ràng nếu object cung cấp. Tránh viết một biểu thức lồng nhau quá dài khi một method thuần sẽ làm ý định dễ hiểu hơn.

Ví dụ selection trực tiếp trên danh sách con khi mỗi phần tử có collection riêng có thể được thực hiện trong predicate bằng method hoặc property phù hợp. Hãy kiểm tra kiểu kết quả và phạm vi #this ở từng cấp để không nhầm phần tử đơn hàng với phần tử dòng hàng.

## 9. Phân biệt selection với projection

Selection và projection đều dùng cú pháp có ngoặc vuông, nhưng mục đích khác nhau:

| Toán tử | Cú pháp | Tác dụng | Kết quả |
|---|---|---|---|
| Selection | .?[condition] | Giữ lại phần tử thỏa điều kiện | List con đối với List nguồn |
| Projection | .![expression] | Biến đổi mỗi phần tử thành một giá trị | List các giá trị được chiếu |

Ví dụ selection:

~~~text
#orders.?[status == 'PAID']
~~~

Kết quả vẫn chứa các Order đã thanh toán.

Ví dụ projection:

~~~text
#orders.![orderNumber]
~~~

Kết quả là List các orderNumber, không còn là List Order.

Có thể kết hợp hai thao tác:

~~~text
#orders.?[status == 'PAID'].![orderNumber]
~~~

Trước tiên lọc các Order đã thanh toán, sau đó lấy mã của từng đơn. Hãy chọn selection khi muốn giữ object phù hợp và projection khi muốn tạo một collection giá trị mới từ chúng.

## 10. Selection trên Map có kết quả khác

Mặc dù bài này tập trung vào List, cần nhớ selection không phải lúc nào cũng trả về List. Khi nguồn là Map, selection giữ lại các entry phù hợp và trả về Map kết quả.

Ví dụ:

~~~text
#scores.?[value >= 80]
~~~

Trong selection trên Map, predicate được đánh giá trên entry; có thể truy cập key và value của entry. Các cặp key-value phù hợp được giữ lại trong Map kết quả.

Vì vậy, hãy xác định kiểu collection nguồn trước khi dựa vào kiểu kết quả. Với List, kết quả là List; với Map, kết quả là Map. Nếu code Java yêu cầu một kiểu cụ thể, hãy dùng đúng overload getValue hoặc chuyển đổi rõ ràng sau đánh giá.

## 11. First và last selection không trả về List

Ngoài selection thông thường, SpEL còn có dạng lấy phần tử phù hợp đầu tiên hoặc cuối cùng:

~~~text
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

- .^[...] chọn phần tử đầu tiên thỏa predicate.
- .$[...] chọn phần tử cuối cùng thỏa predicate.

Hai toán tử này trả về một phần tử phù hợp, không phải List kết quả. Nếu không có phần tử phù hợp, kết quả có thể là null.

So sánh:

~~~text
#orders.?[status == 'PAID']
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

Biểu thức đầu lấy tất cả đơn đã thanh toán. Biểu thức thứ hai lấy đơn đầu tiên phù hợp. Biểu thức thứ ba lấy đơn cuối cùng phù hợp theo thứ tự duyệt của collection.

Nếu mục tiêu là hiển thị nhiều kết quả hoặc tiếp tục lọc collection, dùng .?[...]. Nếu chỉ cần một phần tử đầu/cuối, dùng toán tử tương ứng và xử lý trường hợp không tìm thấy.

## 12. Hiệu năng và tác dụng phụ trong predicate

Selection cần kiểm tra predicate trên các phần tử được duyệt cho đến hết collection. Với List có n phần tử, một phép lọc đơn giản thường cần đánh giá predicate tối đa n lần.

Nếu predicate gọi method tốn chi phí, truy cập quan hệ lazy hoặc thực hiện I/O, chi phí có thể tăng đáng kể. Ví dụ:

~~~text
#orders.?[customer.loadRiskScore() > 5]
~~~

Nếu có nhiều đơn hàng, method loadRiskScore có thể được gọi nhiều lần. Nếu method truy vấn database hoặc gọi dịch vụ bên ngoài, một biểu thức lọc ngắn có thể gây nhiều thao tác tốn kém.

Hãy ưu tiên predicate thuần, chỉ đọc dữ liệu đã có. Nếu cần tính toán phức tạp, hãy chuẩn bị dữ liệu trước hoặc dùng service/query chuyên biệt. Không nên đặt thao tác ghi dữ liệu, gửi thông báo hoặc thay đổi trạng thái trong predicate vì selection có thể gọi predicate nhiều lần.

## 13. Kiểm soát null và collection nguồn

Cần phân biệt hai tình huống:

- Collection nguồn là null: không có collection để selection; biểu thức có thể lỗi khi đánh giá.
- Collection nguồn tồn tại nhưng không có phần tử phù hợp: selection trả về List rỗng.

Hãy bảo đảm collection đầu vào được khởi tạo trước khi đánh giá. Nếu dữ liệu đến từ request hoặc database, có thể chuẩn hóa null thành collection rỗng trong Java trước khi đưa vào context.

Với phần tử null bên trong List, predicate nên kiểm tra #this trước khi truy cập property:

~~~text
#items.?[#this != null and #this.active]
~~~

AND short-circuit đảm bảo #this.active không được đánh giá khi phần tử hiện tại là null.

Không nên dùng một biểu thức selection để che giấu dữ liệu đầu vào thiếu cấu trúc. Hãy xác định rõ hợp đồng dữ liệu và xử lý lỗi ở nơi thích hợp.

## 14. Ví dụ hoàn chỉnh với dữ liệu đơn hàng

Giả sử mỗi Order có orderNumber, status và total. Mục tiêu là lấy các đơn đã thanh toán có tổng tiền từ 100 trở lên.

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = loadOrders();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.?[status == 'PAID' and total >= #minimumTotal]"
);

List<?> result = expression.getValue(context, List.class);

result.forEach(System.out::println);
~~~

Biểu thức giữ lại các Order thỏa cả hai điều kiện. Biến minimumTotal tách ngưỡng cấu hình khỏi chuỗi biểu thức, nên có thể thay đổi ngưỡng theo môi trường hoặc request mà không phải tạo lại nội dung rule.

Nếu cần lấy mã đơn hàng từ kết quả, có thể nối projection:

~~~text
#orders.?[status == 'PAID' and total >= #minimumTotal].![orderNumber]
~~~

Kết quả lúc này là List mã đơn hàng. Selection thực hiện lọc; projection thực hiện chuyển đổi phần tử đã lọc thành giá trị cần dùng.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Kết quả rỗng dù nguồn có dữ liệu | Predicate sai tên property hoặc điều kiện quá chặt | Kiểm tra từng điều kiện trên một phần tử |
| Kết quả null thay vì List rỗng | Collection nguồn null hoặc đang dùng first/last selection | Phân biệt nguồn null với không có phần tử phù hợp |
| Lỗi khi đọc property lồng nhau | Object trung gian null | Thêm kiểm tra null với AND short-circuit |
| Predicate đọc nhầm object | Nhầm #this với #root | Xác định rõ phần tử hiện tại và object gốc |
| Kết quả có phần tử trùng | List nguồn chứa cùng phần tử nhiều lần | Dùng distinct ở tầng Java nếu nghiệp vụ cần loại trùng |
| Kết quả là Map thay vì List | Nguồn selection là Map | Kiểm tra kiểu collection đầu vào |
| Kết quả chứa object thay vì property | Dùng selection khi muốn biến đổi phần tử | Dùng projection .![...] |
| Selection chạy chậm | Predicate gọi method hoặc getter tốn chi phí | Chuẩn bị dữ liệu trước và giữ predicate thuần |

## 16. Ghi nhớ

Selection trên List dùng cú pháp .?[predicate] và trả về một List mới gồm các phần tử thỏa điều kiện. Predicate được đánh giá trên từng phần tử; #this là phần tử hiện tại, còn #root là object gốc của lượt đánh giá. Nếu không có phần tử phù hợp, kết quả là List rỗng và List nguồn không bị lọc tại chỗ.

Selection giữ nguyên object được chọn, còn projection .![...] tạo List các giá trị biến đổi. Hai toán tử first và last selection .^[...] và .$[...] trả về một phần tử thay vì List. Hãy kiểm tra null, giữ predicate thuần, xác định đúng kiểu collection nguồn và dùng đúng toán tử theo hình dạng kết quả mà ứng dụng cần.