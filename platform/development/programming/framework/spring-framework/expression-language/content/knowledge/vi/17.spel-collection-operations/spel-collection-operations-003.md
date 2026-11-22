# Truy vấn phần tử đầu, cuối và phần tử thỏa điều kiện

SpEL cung cấp ba toán tử selection để tìm phần tử trong collection theo một điều kiện: .?[...] lấy tất cả phần tử phù hợp, .^[...] lấy phần tử phù hợp đầu tiên và .$[...] lấy phần tử phù hợp cuối cùng. Cả ba đều đánh giá predicate trên các phần tử của collection, nhưng hình dạng kết quả và số phần tử được trả về khác nhau.

Các toán tử này hữu ích khi cần tìm đơn hàng đầu tiên đang chờ xử lý, sản phẩm cuối cùng còn hàng, tất cả người dùng đang hoạt động hoặc entry đầu tiên trong một Map thỏa điều kiện. Chọn đúng toán tử giúp biểu thức thể hiện rõ mục tiêu truy vấn và tránh phải lọc toàn bộ collection trong Java chỉ để lấy một kết quả.

## 1. Ba dạng selection trong SpEL

Cú pháp tổng quát:

~~~text
collection.?[condition]
collection.^[condition]
collection.$[condition]
~~~

Ý nghĩa:

| Toán tử | Mục đích | Kết quả |
|---|---|---|
| .?[condition] | Lấy tất cả phần tử thỏa điều kiện | Collection kết quả |
| .^[condition] | Lấy phần tử đầu tiên thỏa điều kiện | Một phần tử hoặc null |
| .$[condition] | Lấy phần tử cuối cùng thỏa điều kiện | Một phần tử hoặc null |

Predicate nằm trong ngoặc vuông. SpEL đánh giá điều kiện trên từng phần tử đang được xét. Với List, thứ tự phần tử trong kết quả tuân theo thứ tự duyệt của List nguồn.

Ví dụ với một danh sách đơn hàng:

~~~text
#orders.?[status == 'PAID']
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

Biểu thức đầu trả về tất cả đơn đã thanh toán. Biểu thức thứ hai trả về đơn đã thanh toán đầu tiên theo thứ tự List. Biểu thức thứ ba trả về đơn đã thanh toán cuối cùng theo thứ tự List.

## 2. Lấy tất cả phần tử phù hợp bằng .?[...]

Selection thông thường dùng .?[...]. Nó duyệt collection và giữ lại mọi phần tử có predicate đúng.

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

Kết quả chứa cả hai đơn A-01 và A-03. Collection nguồn không bị lọc tại chỗ; SpEL tạo collection kết quả mới chứa các phần tử phù hợp.

Dùng .?[...] khi cần hiển thị danh sách kết quả, tiếp tục xử lý nhiều phần tử hoặc lấy số lượng phần tử thỏa điều kiện. Nếu chỉ cần một kết quả, hãy cân nhắc toán tử first hoặc last selection để thể hiện ý định trực tiếp.

## 3. Lấy phần tử phù hợp đầu tiên bằng .^[...]

Toán tử .^[...] dừng ở phần tử đầu tiên thỏa predicate và trả về chính phần tử đó:

~~~text
#orders.^[status == 'PAID']
~~~

Nếu List có thứ tự A-01, A-02, A-03 và A-01 là đơn đã thanh toán, biểu thức trả về A-01. Những phần tử sau không cần được kiểm tra sau khi đã tìm thấy kết quả đầu tiên.

Ví dụ Java:

~~~java
Expression firstPaid = parser.parseExpression(
        "#orders.^[status == 'PAID']"
);

Order first = firstPaid.getValue(context, Order.class);

if (first != null) {
    System.out.println(first.getOrderNumber());
}
~~~

Kết quả không phải List chứa một phần tử; đó là object Order được chọn. Nếu không có phần tử phù hợp, kết quả là null.

Toán tử này phù hợp khi thứ tự collection đã mang ý nghĩa nghiệp vụ, ví dụ ưu tiên theo thứ tự xử lý, thứ tự hiển thị hoặc thứ tự đã được sắp xếp trước. Nếu muốn lấy đơn có thời gian tạo sớm nhất, hãy bảo đảm collection đã được sắp xếp theo thời gian trước khi dùng .^[...]. Selection không tự sắp xếp dữ liệu.

## 4. Lấy phần tử phù hợp cuối cùng bằng .$[...]

Toán tử .$[...] lấy phần tử cuối cùng thỏa predicate:

~~~text
#orders.$[status == 'PAID']
~~~

Nếu các đơn A-01 và A-03 đều đã thanh toán, biểu thức trả về A-03 vì nó xuất hiện sau cùng trong thứ tự duyệt của List.

Ví dụ:

~~~java
Expression lastPaid = parser.parseExpression(
        "#orders.$[status == 'PAID']"
);

Order last = lastPaid.getValue(context, Order.class);

if (last != null) {
    System.out.println(last.getOrderNumber());
}
~~~

Kết quả cũng là một object đơn lẻ hoặc null. Nó không phải collection kết quả.

Dùng .$[...] khi cần phần tử phù hợp cuối cùng theo thứ tự hiện có. Nếu mục tiêu là lấy giá trị lớn nhất, mới nhất hoặc có ưu tiên cao nhất, đừng mặc định phần tử cuối cùng đáp ứng điều đó. Hãy sắp xếp collection theo tiêu chí mong muốn trước hoặc dùng một phép tính phù hợp với mục tiêu.

## 5. Predicate và đối tượng hiện tại

Predicate là biểu thức Boolean được đánh giá cho từng phần tử. Trong quá trình selection, #this đại diện cho phần tử hiện tại.

~~~text
#orders.^[#this.total >= 100]
#users.$[#this.active]
#products.?[#this.stock > 0]
~~~

Có thể truy cập property trực tiếp mà không cần viết #this nếu không có sự mơ hồ:

~~~text
#orders.^[total >= 100]
~~~

Khi predicate cần so sánh phần tử với dữ liệu bên ngoài collection, có thể dùng #root hoặc biến context:

~~~text
#orders.^[total >= #minimumTotal]
~~~

Ví dụ:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.^[total >= #minimumTotal]"
);

Order qualifyingOrder = expression.getValue(context, Order.class);
~~~

Ở đây total được đọc trên Order hiện tại, còn #minimumTotal được lấy từ biến context. Hãy dùng tên biến rõ nghĩa để người đọc nhận ra tiêu chí tìm kiếm.

## 6. Kết quả khi không tìm thấy phần tử

Ba toán tử có cách thể hiện kết quả không khớp khác nhau:

- .?[...] trả về collection rỗng nếu không có phần tử phù hợp.
- .^[...] trả về null nếu không có phần tử phù hợp.
- .$[...] trả về null nếu không có phần tử phù hợp.

Ví dụ:

~~~text
#orders.?[status == 'CANCELLED']
#orders.^[status == 'CANCELLED']
#orders.$[status == 'CANCELLED']
~~~

Nếu không có đơn bị hủy, biểu thức đầu trả về List rỗng; hai biểu thức sau trả về null.

Đây là khác biệt quan trọng khi code Java nhận kết quả. Với selection tất cả, có thể kiểm tra isEmpty(). Với first/last selection, cần kiểm tra null trước khi gọi method hoặc truy cập property.

Ví dụ:

~~~java
Order firstCancelled = parser.parseExpression(
        "#orders.^[status == 'CANCELLED']"
).getValue(context, Order.class);

if (firstCancelled == null) {
    System.out.println("Không tìm thấy đơn bị hủy");
}
~~~

Không nên nhầm collection nguồn null với collection hợp lệ nhưng không có phần tử phù hợp. Nếu biến #orders là null, không có collection để selection; biểu thức có thể phát sinh lỗi khi đánh giá. Hãy chuẩn hóa hoặc kiểm tra nguồn dữ liệu trước khi truy vấn.

## 7. Phân biệt selection đầu/cuối với truy cập theo index

Truy cập theo index lấy phần tử ở một vị trí cố định:

~~~text
#orders[0]
#orders[#orders.size() - 1]
~~~

First/last selection tìm phần tử đầu/cuối thỏa một điều kiện:

~~~text
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

Hai nhóm cú pháp có mục đích khác nhau:

| Nhu cầu | Cú pháp |
|---|---|
| Phần tử tại vị trí 0 | #orders[0] |
| Phần tử cuối theo index | #orders[#orders.size() - 1] |
| Phần tử đầu tiên có status PAID | #orders.^[status == 'PAID'] |
| Phần tử cuối cùng có status PAID | #orders.$[status == 'PAID'] |
| Tất cả phần tử có status PAID | #orders.?[status == 'PAID'] |

Dùng indexer khi vị trí đã biết. Dùng selection khi muốn tìm theo điều kiện. Không nên lấy phần tử đầu hoặc cuối theo index rồi mới kiểm tra điều kiện nếu mục tiêu thực sự là tìm phần tử đầu/cuối thỏa predicate.

## 8. Thứ tự collection quyết định kết quả đầu và cuối

Selection đầu và cuối phụ thuộc vào thứ tự duyệt collection. Với List, thứ tự này thường rõ ràng vì List giữ thứ tự phần tử.

Với Set hoặc collection khác, thứ tự phụ thuộc implementation. HashSet không đảm bảo thứ tự duyệt ổn định. LinkedHashSet giữ thứ tự chèn; TreeSet duyệt theo thứ tự comparator. Nếu dùng .^[...] hoặc .$[...] trên một collection không có thứ tự xác định, kết quả có thể không ổn định theo ý nghiệp vụ.

Ví dụ:

~~~java
Set<String> states = new LinkedHashSet<>();
states.add("PENDING");
states.add("PAID");
states.add("CANCELLED");

context.setVariable("states", states);
~~~

Với LinkedHashSet, thứ tự duyệt theo thứ tự chèn. Nhưng nếu thay bằng HashSet, không nên dựa vào một phần tử cụ thể luôn là kết quả đầu hoặc cuối.

Nếu thứ tự quan trọng, hãy cung cấp List đã được sắp xếp hoặc một collection có thứ tự xác định. Selection không thêm quy tắc sắp xếp nào vào nguồn.

## 9. Selection trên Map

Khi nguồn là Map, predicate được đánh giá trên các entry. Trong predicate có thể truy cập key và value của entry.

Ví dụ:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("Lan", 92);
scores.put("Minh", 75);
scores.put("An", 88);

context.setVariable("scores", scores);
~~~

Lấy tất cả entry có điểm từ 80 trở lên:

~~~text
#scores.?[value >= 80]
~~~

Selection trên Map trả về Map gồm các entry phù hợp. Key và value gốc được giữ lại.

Có thể tìm entry đầu hoặc cuối thỏa điều kiện:

~~~text
#scores.^[value >= 80]
#scores.$[value >= 80]
~~~

Với first/last selection trên Map, kết quả là entry được chọn, không phải Map chứa toàn bộ kết quả. Có thể đọc key và value từ entry đó. Thứ tự đầu/cuối phụ thuộc thứ tự duyệt của Map; nếu cần kết quả ổn định, dùng implementation có thứ tự như LinkedHashMap hoặc TreeMap với comparator phù hợp.

Đừng nhầm value trong predicate của Map.Entry với một property value của domain object. Trong selection trên Map, key và value là hai thành phần của entry đang xét.

## 10. Kết hợp selection với projection

Selection giữ nguyên phần tử phù hợp. Projection .![...] biến mỗi phần tử thành một giá trị khác. Có thể kết hợp chúng để lọc trước rồi chỉ lấy dữ liệu cần thiết.

~~~text
#orders.?[status == 'PAID'].![orderNumber]
~~~

Biểu thức trên lấy tất cả đơn đã thanh toán rồi tạo List mã đơn hàng.

Nếu chỉ cần mã đơn hàng đầu tiên thỏa điều kiện, có thể gọi method trên kết quả first selection:

~~~text
#orders.^[status == 'PAID'].orderNumber
~~~

Nếu không tìm thấy phần tử, kết quả first selection là null; truy cập property tiếp theo cần được bảo vệ hoặc xử lý riêng. Có thể lấy object trước trong Java rồi mới đọc property để kiểm soát null rõ ràng.

Với Map, selection trả về Map hoặc entry tùy toán tử; hãy xác định kiểu kết quả trước khi nối thêm property access, indexer hoặc method call.

## 11. Kết hợp nhiều điều kiện trong predicate

Predicate có thể chứa nhiều điều kiện kết hợp bằng AND, OR và NOT:

~~~text
#orders.^[status == 'PAID' and total >= 100]
#users.$[active and (role == 'ADMIN' or role == 'EDITOR')]
#products.?[stock > 0 and price <= #maxPrice]
~~~

Dùng ngoặc để thể hiện nhóm điều kiện. AND có short-circuit khi vế trái false; OR có short-circuit khi vế trái true. Có thể tận dụng điều này để kiểm tra null trước khi truy cập property lồng nhau:

~~~text
#orders.^[customer != null and customer.active]
~~~

Nếu customer là null, phần customer.active không được đánh giá.

Predicate nên tập trung vào điều kiện chọn. Tránh đặt method có side effect như ghi dữ liệu, gửi thông báo hoặc thay đổi trạng thái trong predicate vì số lần gọi phụ thuộc collection và toán tử được dùng.

## 12. Hiệu năng và số phần tử được kiểm tra

Selection tất cả .?[...] cần duyệt collection để xác định toàn bộ phần tử phù hợp. Với n phần tử, predicate thường được đánh giá n lần.

First selection .^[...] có thể dừng ngay khi tìm thấy phần tử đầu tiên phù hợp. Nếu phần tử đầu tiên thỏa điều kiện, các phần tử phía sau không cần kiểm tra.

Last selection .$[...] cần xác định phần tử phù hợp cuối cùng, nên thông thường phải tiếp tục duyệt đến hết collection. Nếu collection lớn và chỉ cần phần tử cuối theo một tiêu chí, hãy cân nhắc việc sắp xếp hoặc truy vấn dữ liệu ở tầng nguồn thay vì luôn đưa toàn bộ collection vào SpEL.

Chi phí thực tế còn phụ thuộc predicate. Một điều kiện đọc property đơn giản thường rẻ hơn method call thực hiện truy vấn database hoặc tính toán phức tạp. Hãy chuẩn bị dữ liệu trước, tránh lazy loading ngoài dự kiến và giữ predicate thuần.

## 13. Null trong phần tử và property lồng nhau

Nếu collection có thể chứa phần tử null, hãy kiểm tra #this trước khi truy cập property:

~~~text
#items.^[#this != null and #this.active]
#items.$[#this != null and #this.score >= 80]
~~~

AND short-circuit bảo đảm phần bên phải không chạy khi phần tử hiện tại là null.

Với property lồng nhau:

~~~text
#orders.^[customer != null and customer.address != null and customer.address.city == 'Da Nang']
~~~

Mỗi điều kiện xác nhận object trung gian trước khi truy cập sâu hơn. Cách này giúp tránh lỗi null trong quá trình selection.

Nếu collection nguồn null, predicate không thể bắt đầu chạy. Hãy kiểm tra nguồn hoặc chuẩn hóa null thành collection rỗng trước khi đặt vào EvaluationContext.

## 14. Ví dụ truy vấn hoàn chỉnh

Giả sử cần tìm đơn đầu tiên đã thanh toán và có tổng tiền đạt ngưỡng. Nếu không có đơn phù hợp, ứng dụng cần hiển thị thông báo.

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = loadOrders();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.^[status == 'PAID' and total >= #minimumTotal]"
);

Order selected = expression.getValue(context, Order.class);

if (selected == null) {
    System.out.println("Không tìm thấy đơn phù hợp");
} else {
    System.out.println(selected.getOrderNumber());
}
~~~

Nếu cần tất cả đơn phù hợp, đổi sang .?[...] và nhận List. Nếu cần đơn phù hợp cuối cùng theo thứ tự collection, dùng .$[...]. Logic predicate có thể giữ nguyên; chỉ toán tử selection và kiểu kết quả thay đổi.

Khi nghiệp vụ yêu cầu “mới nhất”, hãy bảo đảm orders đã được sắp xếp theo thời gian tăng dần trước khi dùng .$[...], hoặc truy vấn trực tiếp từ database với ORDER BY và giới hạn kết quả. Toán tử last chỉ có nghĩa là cuối theo thứ tự duyệt hiện có.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Nhận List khi chỉ cần một object | Dùng .?[...] thay cho .^[...] hoặc .$[...] | Chọn toán tử theo hình dạng kết quả |
| Kết quả null dù collection có dữ liệu | Không có phần tử nào thỏa predicate | Kiểm tra điều kiện trên từng phần tử |
| Lấy nhầm phần tử đầu/cuối | Collection chưa được sắp xếp theo tiêu chí nghiệp vụ | Sắp xếp nguồn trước selection |
| Kết quả thay đổi giữa các lần chạy | Nguồn là Set/Map có thứ tự duyệt không ổn định | Dùng collection có thứ tự xác định |
| Gọi property trên null | Phần tử hoặc object lồng nhau null | Kiểm tra null bằng AND short-circuit |
| Nhầm key/value trong Map | Predicate đang xét Map.Entry | Dùng key và value đúng ngữ cảnh |
| Selection chậm | Predicate gọi method hoặc getter tốn chi phí | Chuẩn bị dữ liệu trước và giữ predicate thuần |
| Truy cập property sau first selection gây lỗi | Không có phần tử phù hợp nên kết quả null | Kiểm tra null trước khi đọc property |

## 16. Ghi nhớ

Dùng .?[...] để lấy tất cả phần tử thỏa điều kiện, .^[...] để lấy phần tử đầu tiên và .$[...] để lấy phần tử cuối cùng. Với List, kết quả first/last là một phần tử hoặc null; selection tất cả trả về List, có thể rỗng. Với Map, selection tất cả trả về Map, còn first/last selection trả về entry được chọn.

Kết quả đầu và cuối luôn phụ thuộc thứ tự duyệt của collection. Selection không tự sắp xếp dữ liệu và không thay đổi collection nguồn. Hãy xác định rõ kiểu collection, thứ tự, trường hợp không tìm thấy và kiểu kết quả trước khi dùng tiếp.

Giữ predicate đơn giản, kiểm tra null trước khi truy cập sâu và tránh side effect trong điều kiện. Khi cần kết quả ổn định theo nghiệp vụ, hãy sắp xếp hoặc truy vấn dữ liệu ở tầng phù hợp trước khi đánh giá SpEL.