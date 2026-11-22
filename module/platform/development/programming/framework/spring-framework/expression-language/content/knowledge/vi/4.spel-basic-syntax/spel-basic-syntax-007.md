# Thứ tự phân tích cú pháp và nhóm bằng dấu ngoặc trong SpEL

Khi một biểu thức SpEL có nhiều toán tử, kết quả không được xác định đơn giản bằng cách đọc từ trái sang phải. Parser áp dụng thứ tự ưu tiên của toán tử và cấu trúc cú pháp để tạo biểu thức. Dấu ngoặc tròn giúp người viết chủ động nhóm các phần cần được tính hoặc đánh giá cùng nhau.

Hiểu đúng precedence và grouping giúp tránh điều kiện sai, phép tính sai, lỗi khi kết hợp toán tử và những biểu thức khó bảo trì. Bài này đi từ cách parser hiểu biểu thức, bảng ưu tiên các nhóm toán tử thường dùng, tính kết hợp, cách dùng dấu ngoặc và quy trình debug.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Giải thích vì sao SpEL không luôn đánh giá biểu thức theo thứ tự trái sang phải.
- Đọc một biểu thức có nhiều toán tử và xác định phần nào được nhóm trước.
- Dùng dấu ngoặc tròn để thay đổi hoặc làm rõ thứ tự đánh giá.
- Phân biệt thứ tự ưu tiên với tính kết hợp của toán tử.
- Nhận biết dấu ngoặc dùng để nhóm biểu thức và dấu ngoặc dùng trong lời gọi method, hàm hoặc truy cập collection.
- Viết và kiểm thử các biểu thức số học, so sánh, logic, điều kiện và truy cập object có cấu trúc rõ ràng.

Bạn nên biết literal, biến có tiền tố #, property access, method invocation và các toán tử cơ bản của SpEL. Bài này tập trung vào cách kết hợp chúng trong một biểu thức.

## 2. Parser xử lý biểu thức như thế nào?

Khi gọi parseExpression, SpEL phân tích chuỗi đầu vào và tạo một Expression thể hiện cấu trúc của biểu thức. Cấu trúc đó phản ánh các quy tắc cú pháp, thứ tự ưu tiên và các nhóm được tạo bởi dấu ngoặc.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("2 + 3 * 4");

Integer result = expression.getValue(Integer.class);
~~~

Kết quả là 14 vì phép nhân có độ ưu tiên cao hơn phép cộng. Có thể hình dung parser nhóm biểu thức thành:

~~~text
       +
      / \
     2   *
        / \
       3   4
~~~

Nếu muốn cộng trước rồi mới nhân, hãy đặt dấu ngoặc:

~~~java
Expression expression =
    parser.parseExpression("(2 + 3) * 4");

Integer result = expression.getValue(Integer.class);
~~~

Kết quả lúc này là 20. Cấu trúc được nhóm thành:

~~~text
        *
       / \
      +   4
     / \
    2   3
~~~

Điểm quan trọng: parser quyết định cấu trúc cú pháp khi parse. EvaluationContext và dữ liệu runtime cung cấp các giá trị để đánh giá cấu trúc đó; chúng không tự thay đổi thứ tự ưu tiên của toán tử.

## 3. Thứ tự ưu tiên của các nhóm toán tử

Bảng sau trình bày thứ tự ưu tiên từ cao xuống thấp đối với các nhóm toán tử thường gặp trong biểu thức SpEL. Những cấu trúc truy cập như property, index và lời gọi method là thành phần của biểu thức cơ sở, không phải tất cả đều là toán tử nhị phân.

| Ưu tiên | Nhóm | Thành phần thường gặp |
|---|---|---|
| Cao | Truy cập và tham chiếu | property bằng dấu chấm, safe navigation, index, lời gọi method, biến #, bean @, kiểu T(...) |
|  | Một ngôi | phủ định ! hoặc not, dấu dương và âm một ngôi |
|  | Nhân chia | *, /, %, div, mod |
|  | Cộng trừ | +, - |
|  | Quan hệ | <, >, <=, >=, lt, gt, le, ge, between, matches, instanceof |
|  | Bằng nhau | ==, !=, eq, ne |
|  | Logic AND | and, && |
|  | Logic OR | or, \|\| |
| Thấp | Điều kiện và Elvis | biểu thức điều kiện ? : và Elvis ?: |
| Thấp nhất | Gán | = |

Bảng này giúp định hướng khi đọc biểu thức. Với biểu thức có nhiều tầng, hãy dùng dấu ngoặc để thể hiện ý định thay vì bắt người đọc phải tự nhớ toàn bộ precedence.

### 3.1. Nhân chia trước cộng trừ

Ví dụ:

~~~text
10 + 6 * 2
~~~

Kết quả là 22 vì 6 * 2 được thực hiện trước.

~~~text
(10 + 6) * 2
~~~

Kết quả là 32 vì dấu ngoặc buộc phép cộng được nhóm trước.

### 3.2. So sánh trước logic

Ví dụ:

~~~text
#age >= 18 and #verified
~~~

Biểu thức được hiểu là:

~~~text
(#age >= 18) and #verified
~~~

Phần so sánh được đánh giá trước, sau đó kết quả boolean được kết hợp bằng AND.

Tương tự:

~~~text
#admin or #age >= 18 and #verified
~~~

Do AND có độ ưu tiên cao hơn OR, cách nhóm là:

~~~text
#admin or ((#age >= 18) and #verified)
~~~

Nếu ý định nghiệp vụ là người dùng phải được xác minh và đồng thời là admin hoặc đủ tuổi, hãy viết rõ:

~~~text
(#admin or #age >= 18) and #verified
~~~

Hai biểu thức có thể cho kết quả khác nhau. Dấu ngoặc ở đây giúp tránh lỗi logic có ảnh hưởng trực tiếp đến quyền truy cập hoặc điều kiện nghiệp vụ.

### 3.3. Điều kiện được đánh giá sau điều kiện logic

Ví dụ:

~~~text
#score >= 60 and #attendance >= 80 ? 'PASS' : 'FAIL'
~~~

Phần điều kiện được nhóm trước khi chọn một trong hai nhánh. Có thể viết tường minh hơn:

~~~text
((#score >= 60) and (#attendance >= 80)) ? 'PASS' : 'FAIL'
~~~

Cách viết này dễ đọc khi biểu thức có nhiều điều kiện. Nếu nhánh true hoặc false lại chứa biểu thức logic khác, hãy nhóm riêng từng nhánh để làm rõ phạm vi.

## 4. Dấu ngoặc tròn thay đổi cách nhóm biểu thức

Dấu ngoặc tròn có ba lợi ích chính:

1. **Ghi đè precedence:** phần bên trong dấu ngoặc được xử lý như một nhóm trước khi kết hợp với phần bên ngoài.
2. **Làm rõ ý định:** người đọc nhìn thấy ngay điều kiện hoặc phép tính nào thuộc cùng một nhóm.
3. **Giảm lỗi khi sửa đổi:** khi thêm một điều kiện mới, phạm vi logic hiện tại được giữ rõ ràng.

### 4.1. Nhóm phép tính

~~~text
#price * (#quantity + #bonusQuantity)
~~~

Biểu thức tính giá theo tổng số lượng. Nếu bỏ ngoặc, phép nhân sẽ được thực hiện trước phép cộng và kết quả có thể khác.

### 4.2. Nhóm điều kiện logic

~~~text
(#role == 'ADMIN' or #role == 'MANAGER') and #active
~~~

Biểu thức yêu cầu tài khoản đang hoạt động và có một trong hai vai trò. Dấu ngoặc xác định nhóm vai trò trước khi kết hợp với trạng thái active.

### 4.3. Nhóm biểu thức lồng nhau

~~~text
((#subtotal - #discount) * (1 + #taxRate)) >= #minimum
~~~

Có thể chia biểu thức thành các phần:

- Tính subtotal sau giảm giá.
- Tính hệ số thuế.
- Nhân hai kết quả.
- So sánh tổng cuối cùng với minimum.

Với công thức tài chính hoặc nghiệp vụ có nhiều bước, nên dùng biến trung gian trong Java hoặc tách thành các expression nhỏ nếu điều đó giúp kiểm thử và giải thích dễ hơn.

## 5. Thứ tự ưu tiên khác với tính kết hợp

Precedence quyết định toán tử nào được nhóm trước khi có nhiều loại toán tử. Associativity quyết định cách nhóm khi nhiều toán tử cùng mức ưu tiên xuất hiện liên tiếp.

Các phép cộng, trừ, nhân và chia thông thường kết hợp từ trái sang phải trong các chuỗi toán tử cùng mức.

Ví dụ:

~~~text
20 / 5 * 2
~~~

Được nhóm như:

~~~text
(20 / 5) * 2
~~~

Kết quả là 8.

Tương tự:

~~~text
10 - 3 - 2
~~~

Được nhóm như:

~~~text
(10 - 3) - 2
~~~

Kết quả là 5. Nếu muốn trừ từ phải sang trái, hãy viết rõ:

~~~text
10 - (3 - 2)
~~~

Kết quả là 9.

Không nên nhầm tính kết hợp với quy luật toán học của phép toán. Phép cộng và nhân có tính giao hoán trong nhiều trường hợp số học, nhưng phép trừ và chia thì không. Vì vậy, thay đổi dấu ngoặc có thể làm thay đổi kết quả.

Với biểu thức điều kiện lồng nhau hoặc biểu thức gán, hãy chủ động dùng ngoặc để tránh phụ thuộc vào cách người đọc nhớ quy tắc kết hợp.

## 6. Dấu ngoặc trong method, function và truy cập collection

Không phải dấu ngoặc tròn nào cũng có nhiệm vụ nhóm một biểu thức lớn. SpEL còn dùng dấu ngoặc cho lời gọi method và function.

Ví dụ:

~~~text
#order.calculateTotal(#taxRate + 1)
~~~

Dấu ngoặc sau calculateTotal chứa danh sách đối số của method. Bên trong đối số, dấu ngoặc có thể tiếp tục nhóm phép tính:

~~~text
#order.calculateTotal((#baseRate + #extraRate) * #factor)
~~~

Ở đây có hai cấp cấu trúc:

- Cặp ngoặc ngoài xác định đối số truyền vào method.
- Cặp ngoặc bên trong nhóm phép cộng trước khi nhân.

Tương tự, khi gọi function:

~~~text
#normalize((#firstName + ' ') + #lastName)
~~~

Dấu ngoặc quanh đối số không thay thế quy tắc precedence bên trong đối số.

Với selection trên collection, dấu ngoặc vuông xác định predicate:

~~~text
#orders.?[(total > 100) and active]
~~~

Dấu ngoặc tròn bên trong predicate nhóm phép so sánh, còn dấu ngoặc vuông xác định điều kiện lọc phần tử. Trong predicate, #this đại diện cho phần tử hiện tại.

## 7. Kết hợp với biến, property và safe navigation

Các tham chiếu property và biến có thể xuất hiện trong một biểu thức logic hoặc số học. Hãy nhóm phần tính toán trước khi so sánh:

~~~text
(#order.unitPrice * #order.quantity) >= #minimum
~~~

Nếu truy cập property lồng nhau có thể null, safe navigation giúp biểu thức trả về null tại nhánh không tồn tại:

~~~text
#customer?.address?.city
~~~

Khi kết hợp với Elvis để chọn giá trị mặc định, có thể nhóm phần lấy giá trị trước khi nối chuỗi hoặc so sánh:

~~~text
(#customer?.displayName ?: 'Guest') + ' - welcome'
~~~

Dấu ngoặc làm rõ rằng kết quả của safe navigation và Elvis là phần được nối với chuỗi phía sau.

Không nên kỳ vọng dấu ngoặc xử lý được null. Nó chỉ nhóm cú pháp. Muốn kiểm soát null, cần dùng safe navigation, Elvis hoặc logic kiểm tra phù hợp.

## 8. Viết biểu thức nhiều điều kiện dễ đọc

Giả sử ứng dụng quyết định có cho phép một đơn hàng được xử lý hay không. Điều kiện gồm trạng thái đơn hàng, số tiền và quyền người dùng.

Biểu thức ngắn:

~~~text
#order.active and (#order.total >= #minimum or #isAdmin)
~~~

Cách đọc:

1. Kiểm tra tổng tiền đạt ngưỡng hoặc người dùng có quyền admin.
2. Kiểm tra đơn hàng đang active.
3. Chỉ khi cả hai phần đều đúng thì kết quả mới là true.

Nếu viết thành một chuỗi dài không nhóm, người đọc dễ nhầm giữa điều kiện bắt buộc và điều kiện thay thế. Hãy dùng dấu ngoặc để phân biệt:

- Điều kiện phải đúng trong mọi trường hợp.
- Các lựa chọn chỉ cần một nhánh đúng.
- Điều kiện ngoại lệ.
- Điều kiện phủ định.

Ví dụ khác:

~~~text
#enabled and not (#status == 'BLOCKED' or #expired)
~~~

Có thể viết rõ hơn:

~~~text
#enabled and (not (#status == 'BLOCKED' or #expired))
~~~

Khi điều kiện liên quan tới quyền, trạng thái thanh toán hoặc kiểm soát truy cập, nên ưu tiên cách viết tường minh và có test cho từng nhánh.

## 9. Parse expression và đánh giá kết quả

Một biểu thức có thể được parse mà chưa cần biết giá trị runtime của các biến. Sau đó, truyền EvaluationContext khi đánh giá:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "(#score >= 60 and #attendance >= 80) ? 'PASS' : 'FAIL'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("score", 85);
context.setVariable("attendance", 90);

String result = expression.getValue(context, String.class);
~~~

Kết quả là PASS.

Có thể thay đổi dữ liệu trong context cho lần đánh giá khác mà không phải viết lại quy tắc. Điều này hữu ích khi biểu thức là cấu hình cố định còn dữ liệu thay đổi theo từng đối tượng.

Cần phân biệt:

- Parse kiểm tra cú pháp và tạo cấu trúc biểu thức.
- Evaluate thực hiện cấu trúc đó với root object, biến, function và các quyền có trong context.
- Parentheses quyết định grouping ở bước parse; giá trị biến không làm thay đổi grouping.
- Một biểu thức parse thành công vẫn có thể lỗi khi evaluate nếu biến chưa được khai báo, property không tồn tại hoặc kiểu dữ liệu không phù hợp.

## 10. Cách debug biểu thức có nhiều tầng

Khi biểu thức trả kết quả khác dự kiến, hãy thu nhỏ nó theo từng phần:

1. Parse và đánh giá phần số học riêng.
2. Đánh giá từng điều kiện so sánh thành Boolean.
3. Kết hợp các điều kiện bằng AND hoặc OR.
4. Thêm biểu thức điều kiện để chọn kết quả.
5. Sau cùng mới thêm property path, method hoặc collection operation.

Ví dụ, thay vì debug ngay biểu thức:

~~~text
(#order.total - #order.discount) >= #minimum and #customer.active
~~~

Hãy kiểm tra lần lượt:

~~~text
#order.total - #order.discount
~~~

~~~text
(#order.total - #order.discount) >= #minimum
~~~

~~~text
#customer.active
~~~

~~~text
((#order.total - #order.discount) >= #minimum) and #customer.active
~~~

Nếu các phần riêng đều đúng nhưng biểu thức kết hợp sai, hãy xem lại grouping và precedence.

Có thể dùng dấu ngoặc ngay cả khi precedence hiện tại đã cho kết quả mong muốn. Mục tiêu là làm cho biểu thức tự giải thích được ý định của người viết.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Kết quả phép tính khác dự kiến | Nhân/chia được ưu tiên hơn cộng/trừ | Nhóm phần cần tính trước bằng ngoặc |
| Điều kiện OR làm kết quả true ngoài dự kiến | AND có độ ưu tiên cao hơn OR | Nhóm các nhánh OR và điều kiện bắt buộc |
| Điều kiện ternary chọn nhánh sai | Điều kiện trước dấu ? chưa được nhóm như mong muốn | Đặt ngoặc quanh toàn bộ điều kiện Boolean |
| Biểu thức dài khó đọc | Quá nhiều toán tử và property path trong một dòng | Nhóm theo nghiệp vụ hoặc tách biến trung gian |
| Method nhận giá trị đối số sai | Nhầm ngoặc gọi method với ngoặc nhóm phép tính | Xem riêng danh sách đối số và nhóm biểu thức bên trong |
| Parse thành công nhưng evaluate thất bại | Biến, root object hoặc property không có trong context | Kiểm tra dữ liệu runtime và quyền truy cập |
| Sửa biểu thức làm thay đổi logic cũ | Thêm toán tử mà không xác định lại phạm vi nhóm | Viết lại grouping tường minh và bổ sung test |

## 12. Bài tập thực hành

### Bài 1: phép tính

Dự đoán kết quả của các biểu thức sau, rồi chạy bằng SpEL:

~~~text
2 + 3 * 4
(2 + 3) * 4
20 / 5 * 2
20 / (5 * 2)
~~~

Giải thích tại sao các kết quả khác nhau.

### Bài 2: điều kiện logic

Cho các biến:

- #isAdmin = false
- #age = 20
- #verified = false

So sánh:

~~~text
#isAdmin or #age >= 18 and #verified
~~~

và:

~~~text
(#isAdmin or #age >= 18) and #verified
~~~

Ghi lại kết quả và giải thích điều kiện nào bắt buộc.

### Bài 3: điều kiện nhiều nhánh

Viết biểu thức trả về:

- GOLD khi khách hàng có hạng GOLD và đơn hàng đạt ngưỡng.
- SILVER khi khách hàng có hạng SILVER và đơn hàng đạt ngưỡng.
- OTHER trong các trường hợp còn lại.

Nhóm điều kiện của từng hạng bằng dấu ngoặc để tránh nhầm giữa AND và OR.

### Bài 4: debug

Tạo một biểu thức có property lồng nhau, phép tính, so sánh và ternary. Đánh giá từng phần riêng, sau đó kết hợp lại. Thử bỏ một cặp ngoặc và ghi nhận trường hợp kết quả thay đổi.

## 13. Checklist trước khi lưu biểu thức

- [ ] Đã xác định toán tử nào có độ ưu tiên cao hơn chưa?
- [ ] Đã phân biệt precedence và associativity chưa?
- [ ] Đã nhóm rõ các phép tính cần thực hiện trước chưa?
- [ ] Đã nhóm các điều kiện AND/OR theo đúng nghiệp vụ chưa?
- [ ] Đã đặt ngoặc quanh điều kiện trước ternary khi biểu thức phức tạp chưa?
- [ ] Đã phân biệt ngoặc nhóm với ngoặc gọi method/function chưa?
- [ ] Đã kiểm tra root object, biến và property trong EvaluationContext chưa?
- [ ] Đã thử từng phần nhỏ trước khi đánh giá toàn biểu thức chưa?
- [ ] Đã có test cho cả trường hợp true, false và dữ liệu biên chưa?
- [ ] Biểu thức có đủ ngắn và rõ để người khác bảo trì không?

## 14. Kết luận

SpEL phân tích biểu thức theo cấu trúc cú pháp và thứ tự ưu tiên toán tử. Dấu ngoặc tròn cho phép ghi đè cách nhóm mặc định, thể hiện ý định và giữ logic ổn định khi biểu thức phát triển. Hãy phân biệt precedence với associativity, kiểm tra các điều kiện AND/OR và ternary bằng ví dụ cụ thể, rồi dùng grouping tường minh cho các quy tắc nghiệp vụ quan trọng. Một biểu thức tốt không chỉ cho kết quả đúng mà còn giúp người đọc hiểu ngay vì sao nó cho kết quả đó.