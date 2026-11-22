# Toán tử between và cách diễn đạt khoảng giá trị

## Mục tiêu

Sau bài này, bạn có thể dùng toán tử **between** trong Spring Expression Language (SpEL) để kiểm tra một giá trị có nằm trong một khoảng hay không; hiểu hai đầu mút của khoảng được xử lý như thế nào; truyền cận dưới và cận trên bằng biến; và chọn cách viết phù hợp cho khoảng đóng, khoảng mở hoặc khoảng nửa mở. Bạn cũng sẽ biết cách xử lý kiểu dữ liệu, giá trị null, khoảng không hợp lệ và các trường hợp biên.

## 1. Toán tử between dùng để làm gì?

**between** là toán tử so sánh dùng để kiểm tra một giá trị có nằm giữa hai giá trị giới hạn hay không. Cú pháp cơ bản:

~~~text
value between {lowerBound, upperBound}
~~~

Ví dụ:

~~~text
#age between {18, 65}
~~~

Biểu thức trả về **true** nếu **#age** nằm trong khoảng từ 18 đến 65 theo thứ tự so sánh. Nếu nhỏ hơn 18 hoặc lớn hơn 65, kết quả là **false**.

Toán tử này giúp diễn đạt một quy tắc khoảng giá trị gọn hơn việc viết hai phép so sánh riêng. Nó đặc biệt hữu ích khi biểu thức cấu hình cần kiểm tra tuổi, điểm số, mức giá, ngày tháng hoặc một ngưỡng nghiệp vụ.

## 2. Cú pháp và hai cận của khoảng

Vế trái của **between** là giá trị cần kiểm tra. Vế phải là một inline list gồm hai phần tử theo thứ tự:

1. Cận dưới (lower bound).
2. Cận trên (upper bound).

Ví dụ:

~~~text
#score between {0, 100}
~~~

Có thể hiểu biểu thức này tương đương với:

~~~text
#score >= 0 and #score <= 100
~~~

Vì vậy, **between** dùng **khoảng đóng**: cả cận dưới và cận trên đều được tính là nằm trong khoảng.

| Giá trị kiểm tra | Biểu thức | Kết quả |
|---:|---|---|
| 0 | 0 between {0, 100} | true |
| 1 | 1 between {0, 100} | true |
| 50 | 50 between {0, 100} | true |
| 100 | 100 between {0, 100} | true |
| -1 | -1 between {0, 100} | false |
| 101 | 101 between {0, 100} | false |

Nếu nghiệp vụ yêu cầu không tính một hoặc cả hai đầu mút, **between** không thể diễn đạt trực tiếp khoảng mở. Hãy dùng các phép so sánh riêng như **>**, **<**, **>=** và **<=**.

## 3. Inline list ở vế phải

Cặp dấu ngoặc nhọn trong cú pháp **between** biểu diễn một inline list của SpEL:

~~~text
#temperature between {18, 26}
~~~

Đây là danh sách hai giá trị cận, không phải cú pháp tạo dãy số từ 18 đến 26. Biểu thức không duyệt qua từng số nguyên trong khoảng; nó so sánh giá trị bên trái với hai cận.

Thứ tự hai phần tử có ý nghĩa. Phần tử thứ nhất là cận dưới và phần tử thứ hai là cận trên:

~~~text
#quantity between {#minimumQuantity, #maximumQuantity}
~~~

Không đảo hai cận chỉ vì muốn viết theo thứ tự khác. Nếu cận dưới lớn hơn cận trên trong cùng một miền so sánh, không có giá trị thông thường nào thỏa đồng thời điều kiện lớn hơn hoặc bằng cận dưới và nhỏ hơn hoặc bằng cận trên. Nên xác thực thứ tự cận ở lớp Java trước khi đánh giá nếu hai cận đến từ dữ liệu động.

Vế phải cần cung cấp đúng hai giá trị giới hạn. Nếu biểu thức không tạo ra cấu trúc hai phần tử phù hợp, việc đánh giá có thể thất bại. Khi cần khoảng động, hãy dùng hai biến hoặc hai thuộc tính đã được cung cấp trong context.

## 4. Dùng biến làm cận dưới và cận trên

Không cần viết cố định các con số trong biểu thức. Có thể truyền cận vào EvaluationContext bằng biến:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#score between {#minimum, #maximum}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("score", 82);
context.setVariable("minimum", 60);
context.setVariable("maximum", 100);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Kết quả là **true** vì 82 nằm trong khoảng đóng từ 60 đến 100.

Khi giá trị cận thay đổi theo cấu hình hoặc người dùng, chỉ cần cập nhật biến trong context mà không phải ghép chuỗi biểu thức mới. Cách này cũng giúp tránh nối trực tiếp dữ liệu đầu vào vào mã SpEL.

Có thể lấy cận từ một đối tượng gốc:

~~~text
#measurement.value between {#measurement.minAllowed, #measurement.maxAllowed}
~~~

Hoặc sử dụng root object không có tiền tố # nếu ứng dụng truyền nó trực tiếp vào getValue:

~~~text
value between {minAllowed, maxAllowed}
~~~

Tên thuộc tính cần khớp với mô hình đối tượng và khả năng truy cập của EvaluationContext.

## 5. Diễn đạt khoảng đóng, khoảng mở và khoảng nửa mở

Chọn toán tử dựa trên ý nghĩa của hai đầu mút trong nghiệp vụ.

| Loại khoảng | Điều kiện | Ví dụ SpEL |
|---|---|---|
| Đóng [a, b] | x >= a and x <= b | #x between {#a, #b} |
| Mở (a, b) | x > a and x < b | #x > #a and #x < #b |
| Nửa mở [a, b) | x >= a and x < b | #x >= #a and #x < #b |
| Nửa mở (a, b] | x > a and x <= b | #x > #a and #x <= #b |

Ví dụ, một hệ thống phân loại điểm có thể coi điểm từ 0 đến dưới 5 là chưa đạt:

~~~text
#score >= 0 and #score < 5
~~~

Nếu quy tắc chấp nhận cả điểm 5:

~~~text
#score between {0, 5}
~~~

Đối với khoảng thời gian, kiểu nửa mở thường hữu ích. Ví dụ, một khoảng ngày bắt đầu được tính nhưng ngày kết thúc không được tính:

~~~text
#eventDate >= #startDate and #eventDate < #endDate
~~~

Khoảng nửa mở giúp hai khoảng liền nhau không bị trùng tại ranh giới. **between** phù hợp khi cả hai đầu mút đều được bao gồm.

## 6. Kết hợp between với toán tử logic

Có thể kết hợp **between** với **and**, **or** và **not** để mô tả quy tắc nhiều điều kiện.

Ví dụ, một giao dịch cần có số tiền trong khoảng cho phép và trạng thái đã xác nhận:

~~~text
#transaction.amount between {#minimumAmount, #maximumAmount}
and #transaction.confirmed
~~~

Một trường hợp khác là kiểm tra tuổi thuộc một trong hai nhóm được phép:

~~~text
(#age between {18, 25}) or (#age between {30, 40})
~~~

Dấu ngoặc giúp người đọc thấy rõ mỗi phép **between** là một điều kiện độc lập. Có thể viết phủ định:

~~~text
not (#score between {0, 100})
~~~

Biểu thức này đúng khi điểm nằm ngoài khoảng đóng từ 0 đến 100. Nếu muốn thể hiện rõ hai trường hợp ngoài khoảng, có thể viết:

~~~text
#score < 0 or #score > 100
~~~

Khi có nhiều điều kiện, nên dùng dấu ngoặc để tránh nhầm lẫn về thứ tự ưu tiên của **and** và **or**.

## 7. Kiểu dữ liệu và quy tắc so sánh

**between** không giới hạn ở số nguyên. Nó có thể được dùng với các giá trị có thứ tự so sánh phù hợp, miễn là kiểu dữ liệu ở vế trái và hai cận có thể được so sánh theo cơ chế mà SpEL hỗ trợ.

### 7.1. Số nguyên và số thập phân

Ví dụ với điểm số:

~~~text
#score between {0.0, 10.0}
~~~

Khi làm việc với tiền hoặc giá trị thập phân chính xác, hãy truyền BigDecimal từ Java:

~~~java
context.setVariable("amount", new BigDecimal("125.50"));
context.setVariable("minimum", new BigDecimal("100.00"));
context.setVariable("maximum", new BigDecimal("200.00"));

Expression expression =
    parser.parseExpression("#amount between {#minimum, #maximum}");

Boolean inRange = expression.getValue(context, Boolean.class);
~~~

Nên giữ các toán hạng cùng miền kiểu hoặc có thể chuyển đổi tương thích. Đừng dựa vào việc chuyển đổi ngầm để che giấu dữ liệu sai kiểu.

### 7.2. Ngày và thời gian

Các kiểu ngày giờ có thứ tự so sánh có thể được dùng để kiểm tra một mốc thời gian nằm trong khoảng. Ví dụ:

~~~java
context.setVariable("eventDate", LocalDate.of(2026, 5, 12));
context.setVariable("startDate", LocalDate.of(2026, 1, 1));
context.setVariable("endDate", LocalDate.of(2026, 12, 31));

Expression expression =
    parser.parseExpression("#eventDate between {#startDate, #endDate}");

Boolean withinYear = expression.getValue(context, Boolean.class);
~~~

Cả ba biến đều dùng LocalDate, nên việc so sánh theo thứ tự ngày được xác định rõ.

Với thời điểm có múi giờ, hãy chuẩn hóa về một kiểu biểu diễn nhất quán, chẳng hạn Instant, hoặc thống nhất múi giờ trước khi tạo cận. Không so sánh ngày địa phương của các múi giờ khác nhau như thể chúng là cùng một mốc thời gian tuyệt đối.

### 7.3. Chuỗi

Chuỗi có thể được so sánh theo thứ tự từ điển (lexicographic) nếu kiểu so sánh được hỗ trợ. Ví dụ:

~~~text
#code between {'A100', 'A999'}
~~~

Cần hiểu rằng thứ tự từ điển không phải thứ tự số tự nhiên hoặc quy tắc sắp xếp theo ngôn ngữ người dùng. Ví dụ chuỗi "A20" và "A100" được so sánh theo ký tự, không phải tự động chuyển phần số thành số nguyên.

Không dùng **between** trên chuỗi để mô tả thứ tự nghiệp vụ phức tạp, thứ tự theo locale hoặc khoảng mã có quy tắc riêng. Với những trường hợp đó, hãy chuẩn hóa dữ liệu hoặc viết bộ so sánh trong Java.

## 8. Giá trị null, sai kiểu và khoảng không hợp lệ

Một biểu thức **between** chỉ có thể đánh giá khi giá trị cần kiểm tra và hai cận cung cấp đủ dữ liệu có thể so sánh.

Các trường hợp cần xử lý:

- Giá trị bên trái là null.
- Cận dưới hoặc cận trên là null.
- Một cận là chuỗi trong khi giá trị kiểm tra là kiểu số không tương thích.
- Hai cận thuộc các kiểu không thể so sánh với nhau hoặc với giá trị cần kiểm tra.
- Cận dưới lớn hơn cận trên.
- Biến hoặc thuộc tính được tham chiếu không tồn tại trong context.

Những trường hợp này có thể dẫn đến lỗi đánh giá thay vì kết quả **false**. **between** không tự thay thế dữ liệu thiếu bằng 0, không tự sắp xếp hai cận và không xác thực quy tắc nghiệp vụ.

Nếu dữ liệu đầu vào có thể thiếu, hãy kiểm tra trước:

~~~text
#value != null and #minimum != null and #maximum != null
and #minimum <= #maximum
and #value between {#minimum, #maximum}
~~~

Đây là cách diễn đạt nhiều điều kiện trong cùng một biểu thức. Tuy vậy, ứng dụng vẫn cần kiểm tra dữ liệu và xử lý lỗi ở lớp Java; không nên coi một biểu thức điều kiện là cơ chế xác thực toàn diện cho dữ liệu không đáng tin cậy.

## 9. Ví dụ thực tế: phân loại mức nhiệt độ

Giả sử ứng dụng giám sát nhiệt độ cần xác định một giá trị nằm trong vùng hoạt động bình thường:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#temperature between {#minimum, #maximum}"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("temperature", new BigDecimal("22.5"));
context.setVariable("minimum", new BigDecimal("18.0"));
context.setVariable("maximum", new BigDecimal("26.0"));

Boolean normal = expression.getValue(context, Boolean.class);
~~~

Kết quả là **true**. Nếu nhiệt độ đúng bằng 18.0 hoặc 26.0, kết quả vẫn là **true** vì hai cận được bao gồm.

Nếu quy tắc yêu cầu nhiệt độ phải lớn hơn 18.0 và nhỏ hơn 26.0, thay bằng:

~~~text
#temperature > #minimum and #temperature < #maximum
~~~

Không nên dùng **between** cho trường hợp cần loại bỏ hai đầu mút.

## 10. Ví dụ thực tế: kiểm tra hạn mức đơn hàng

Một đơn hàng được chấp nhận nếu tổng tiền nằm trong hạn mức đã cấu hình và trạng thái không bị hủy:

~~~text
#order != null
and #order.status != 'CANCELLED'
and #order.total between {#minimumTotal, #maximumTotal}
~~~

Các biến **#minimumTotal** và **#maximumTotal** có thể là BigDecimal được truyền từ Java. Nếu ứng dụng có nhiều loại tiền tệ, hãy bảo đảm giá trị đơn hàng và hai cận cùng đơn vị tiền trước khi so sánh.

Nếu quy tắc có thêm nhiều điều kiện như loại khách hàng, khu vực, trạng thái thanh toán hoặc giới hạn theo ngày, hãy cân nhắc đưa phần quyết định nghiệp vụ phức tạp vào một service Java. SpEL phù hợp với điều kiện khai báo ngắn và dễ hiểu.

## 11. Kiểm thử giá trị biên

Khoảng giá trị thường có lỗi ở đúng hai đầu mút. Khi kiểm thử một biểu thức **between**, hãy bao gồm:

| Trường hợp | Kết quả mong đợi với x between {10, 20} |
|---|---|
| x = 9 | false |
| x = 10 | true |
| x = 11 | true |
| x = 20 | true |
| x = 21 | false |

Ngoài hai cận, cần kiểm tra:

- Giá trị null.
- Một hoặc cả hai cận là null.
- Cận dưới bằng cận trên.
- Cận dưới lớn hơn cận trên.
- Giá trị thập phân sát cận.
- Kiểu dữ liệu không tương thích.
- Ngày giờ đúng tại thời điểm bắt đầu và kết thúc.

Nếu dùng khoảng mở hoặc nửa mở, hãy viết các ca kiểm thử riêng cho từng đầu mút. Đừng suy ra kết quả của khoảng mở từ kiểm thử **between** vì ngữ nghĩa hai loại khoảng khác nhau.

## 12. Ghi nhớ

Toán tử **between** kiểm tra một giá trị có nằm trong khoảng đóng hay không. Cú pháp là:

~~~text
value between {lowerBound, upperBound}
~~~

Cả cận dưới và cận trên đều được bao gồm. Vế phải là inline list chứa hai cận theo đúng thứ tự; nó không tạo một dãy số và không tự sắp xếp giới hạn.

Dùng **between** cho khoảng đóng. Dùng các phép so sánh **>**, **<**, **>=** và **<=** khi cần khoảng mở hoặc nửa mở. Các cận có thể là literal, biến hoặc thuộc tính, miễn là các kiểu dữ liệu có thể so sánh phù hợp.

Hãy xác thực dữ liệu null, kiểu dữ liệu và thứ tự hai cận; kiểm thử cả hai đầu mút; và giữ logic nghiệp vụ phức tạp trong Java. Khi quy tắc chỉ là kiểm tra một giá trị trong một khoảng, **between** giúp biểu thức SpEL ngắn và dễ đọc.