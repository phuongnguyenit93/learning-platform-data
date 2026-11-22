# Dùng ngoặc để làm rõ ý định của biểu thức số học

Trong SpEL, ngoặc tròn giúp xác định nhóm phép tính cần được thực hiện trước. Một biểu thức có thể hợp lệ về cú pháp nhưng vẫn cho kết quả khác với điều người viết mong muốn nếu người đọc hiểu sai thứ tự ưu tiên của toán tử. Việc đặt ngoặc đúng chỗ làm rõ ý định, giúp biểu thức dễ đọc, dễ kiểm tra và an toàn hơn khi được dùng trong cấu hình hoặc rule nghiệp vụ.

Ngoặc tròn không chỉ hữu ích để thay đổi thứ tự tính. Chúng còn giúp người đọc nhận ra đâu là tử số, mẫu số, phần chiết khấu, tổng phụ hoặc điều kiện cần được tính như một đơn vị logic.

## 1. Thứ tự ưu tiên cơ bản của phép toán

Trong các biểu thức số học thông thường, phép nhân, chia và lấy phần dư được thực hiện trước phép cộng và trừ. Khi các toán tử có cùng mức ưu tiên, phép tính được xử lý theo thứ tự từ trái sang phải.

Ví dụ:

~~~text
2 + 3 * 4
~~~

Kết quả là 14 vì phép nhân được thực hiện trước: 3 * 4 = 12, sau đó 2 + 12 = 14.

Nếu muốn cộng trước rồi mới nhân, hãy đặt phần cần cộng trong ngoặc:

~~~text
(2 + 3) * 4
~~~

Kết quả là 20. Ngoặc khiến nhóm 2 + 3 được tính trước, sau đó kết quả 5 được nhân với 4.

Bảng sau tóm tắt cách đọc các phép toán thường gặp:

| Nhóm phép toán | Toán tử | Ghi chú |
|---|---|---|
| Nhóm biểu thức | ( ... ) | Đánh giá biểu thức bên trong trước |
| Lũy thừa | ^ | Dùng để biểu diễn phép lũy thừa trong SpEL |
| Nhân, chia, lấy phần dư | *, /, % | Ưu tiên cao hơn cộng và trừ |
| Cộng, trừ | +, - | Thực hiện sau nhân, chia và lấy phần dư |

Khi một biểu thức kết hợp nhiều nhóm toán tử, ngoặc là cách rõ ràng nhất để thể hiện thứ tự mà nghiệp vụ yêu cầu. Với những biểu thức có lũy thừa hoặc dấu âm một ngôi, nên dùng ngoặc để làm rõ phần cơ số, số mũ và phạm vi của dấu âm thay vì buộc người đọc phải tự suy luận.

## 2. Thay đổi kết quả bằng cách nhóm phép tính

Cùng một dãy số và toán tử có thể cho kết quả khác nhau tùy vị trí ngoặc.

### 2.1. Cộng trước hay nhân trước

~~~text
10 + 5 * 2
(10 + 5) * 2
10 + (5 * 2)
~~~

Kết quả tương ứng là 20, 30 và 20. Biểu thức đầu tiên và thứ ba cho cùng kết quả vì nhân vốn đã có ưu tiên cao hơn cộng. Biểu thức thứ hai thay đổi thứ tự bằng cách nhóm phép cộng trước.

### 2.2. Chia một tích hay nhân sau khi chia

~~~text
100 / 5 * 2
100 / (5 * 2)
(100 / 5) * 2
~~~

Kết quả lần lượt là 40, 10 và 40. Phép chia và nhân cùng mức ưu tiên nên chuỗi không có ngoặc được xử lý từ trái sang phải. Nếu ý định là chia cho toàn bộ tích 5 * 2, mẫu số phải được đặt trong ngoặc.

Đây là trường hợp rất dễ gây lỗi khi viết tỷ lệ, định mức, giá trung bình hoặc công thức phân bổ.

### 2.3. Phạm vi của phép trừ

~~~text
100 - 20 - 5
100 - (20 - 5)
(100 - 20) - 5
~~~

Kết quả tương ứng là 75, 95 và 75. Phép trừ không có tính kết hợp như phép cộng theo cách nhóm tùy ý. Ngoặc giúp xác định rõ khoản nào được trừ trước và phần nào là một nhóm cần giữ nguyên.

## 3. Dùng ngoặc trong SpEL với ExpressionParser

Khi dùng SpEL trực tiếp, nội dung trong ngoặc được phân tích như một phần của biểu thức. Không cần API riêng để tạo nhóm phép toán.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression first = parser.parseExpression("10 + 5 * 2");
Expression second = parser.parseExpression("(10 + 5) * 2");

Integer firstResult = first.getValue(Integer.class);
Integer secondResult = second.getValue(Integer.class);

System.out.println(firstResult);  // 20
System.out.println(secondResult); // 30
~~~

Ví dụ cho thấy cùng parser và cùng kiểu literal, chỉ cần thay đổi vị trí ngoặc là kết quả đã khác. Vì vậy, khi đọc một biểu thức cấu hình, đừng chỉ nhìn các toán tử riêng lẻ; hãy đọc cấu trúc nhóm từ trong ra ngoài.

Có thể dùng ngoặc lồng nhau:

~~~java
Expression expression = parser.parseExpression(
        "((10 + 5) * 2) - (8 / 4)"
);

Integer result = expression.getValue(Integer.class);
~~~

Biểu thức trên tính hai nhóm bên trong trước, nhân nhóm thứ nhất với 2, tính nhóm chia ở vế còn lại rồi trừ hai kết quả. Ngoặc lồng nhau hợp lệ, nhưng nên tránh lồng quá sâu nếu có thể tách phép tính thành các biến hoặc thuộc tính có tên rõ ràng.

## 4. Dùng ngoặc để làm rõ tử số và mẫu số

Khi viết công thức có nhiều thành phần, hãy nhóm riêng tử số và mẫu số theo đúng ý nghĩa toán học.

Ví dụ, tính điểm trung bình có trọng số:

~~~text
(scoreA * weightA + scoreB * weightB) / (weightA + weightB)
~~~

Ngoặc thứ nhất xác định tổng điểm đã nhân trọng số. Ngoặc thứ hai xác định tổng trọng số. Không có hai nhóm này, người đọc khó xác định mẫu số có bao gồm cả hai trọng số hay chỉ một phần.

Ví dụ trong Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression weightedAverage = parser.parseExpression(
        "(#scoreA * #weightA + #scoreB * #weightB) "
        + "/ (#weightA + #weightB)"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("scoreA", 8);
context.setVariable("scoreB", 9);
context.setVariable("weightA", 2);
context.setVariable("weightB", 3);

Object result = weightedAverage.getValue(context);
~~~

Với dữ liệu ví dụ, công thức là (8 * 2 + 9 * 3) / (2 + 3), cho kết quả số học là 8.6. Kiểu kết quả thực tế phụ thuộc kiểu của các toán hạng và quy tắc phép toán; nếu cần một kiểu cụ thể, hãy thiết kế kiểu đầu vào và chuyển đổi kết quả phù hợp.

Tương tự, khi tính phần trăm hoặc tỷ lệ, nên đặt ngoặc cho toàn bộ phần cần chia:

~~~text
(part / total) * 100
(part * 100) / total
~~~

Hai cách viết có thể khác nhau về kiểu trung gian và độ chính xác tùy kiểu số được sử dụng. Với số nguyên, phép chia nguyên có thể làm mất phần thập phân trước khi nhân. Nếu cần tỷ lệ decimal, hãy chọn kiểu số phù hợp và nhóm phép tính theo đúng công thức nghiệp vụ.

## 5. Dùng ngoặc trong công thức giá, thuế và chiết khấu

Các công thức thương mại thường có nhiều bước: số lượng nhân đơn giá, trừ chiết khấu, sau đó cộng thuế hoặc phí. Hãy nhóm từng phần theo trình tự nghiệp vụ.

Giả sử:

- Đơn giá: 19.90
- Số lượng: 3
- Tỷ lệ chiết khấu: 10%
- Thuế: 8%

Một cách viết rõ ràng là:

~~~text
((unitPrice * quantity) * (1 - discountRate)) * (1 + taxRate)
~~~

Công thức này thể hiện lần lượt tổng tiền trước chiết khấu, hệ số sau chiết khấu và hệ số sau thuế.

Có thể viết trong SpEL với biến:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression totalExpression = parser.parseExpression(
        "(#unitPrice * #quantity) "
        + "* (1M - #discountRate) "
        + "* (1M + #taxRate)"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("unitPrice", new BigDecimal("19.90"));
context.setVariable("quantity", new BigDecimal("3"));
context.setVariable("discountRate", new BigDecimal("0.10"));
context.setVariable("taxRate", new BigDecimal("0.08"));

BigDecimal total = totalExpression.getValue(
        context,
        BigDecimal.class
);
~~~

Ở đây các giá trị decimal được truyền qua biến BigDecimal. Ngoặc cho thấy rõ từng hệ số và thứ tự kết hợp. Nếu viết trực tiếp literal BigDecimal trong biểu thức, có thể dùng hậu tố M, ví dụ:

~~~text
(19.90M * 3M) * (1M - 0.10M) * (1M + 0.08M)
~~~

Ngoặc chỉ xác định nhóm phép tính. Chúng không tự áp dụng quy tắc làm tròn tiền tệ, không xác định số chữ số thập phân cần giữ và không thay thế chính sách thuế. Những quy tắc đó cần được định nghĩa rõ ở tầng nghiệp vụ.

## 6. Dùng ngoặc với dấu âm và phép lũy thừa

Dấu âm có thể áp dụng cho một literal hoặc cho cả một nhóm biểu thức. Ngoặc giúp xác định phạm vi của dấu âm:

~~~text
-5 * 2
-(5 * 2)
(-5) * 2
~~~

Ba cách trên đều cho kết quả -10 trong ví dụ này, nhưng cách nhóm có ý nghĩa khác nhau khi thay đổi biểu thức:

~~~text
-(5 + 2)
(-5) + 2
~~~

Kết quả lần lượt là -7 và -3. Ở biểu thức đầu, dấu âm áp dụng cho toàn bộ tổng. Ở biểu thức thứ hai, chỉ số 5 mang dấu âm.

SpEL có toán tử lũy thừa ^. Khi biểu thức kết hợp lũy thừa với phép nhân, dấu âm hoặc nhiều số mũ, nên dùng ngoặc để thể hiện rõ cơ số và số mũ:

~~~text
(2 ^ 3) * 4
2 ^ (3 * 2)
(-2) ^ 2
-(2 ^ 2)
~~~

Các nhóm trên biểu đạt những ý định toán học khác nhau. Chẳng hạn, (-2) ^ 2 là bình phương số âm, còn -(2 ^ 2) là lấy số đối của bình phương 2. Không nên bỏ ngoặc nếu điều đó khiến người đọc phải đoán dấu âm thuộc cơ số hay thuộc toàn bộ kết quả.

## 7. Ngoặc trong biểu thức kết hợp số học và điều kiện

Ngoặc cũng hữu ích khi kết quả số học được dùng trong điều kiện so sánh hoặc logic.

~~~text
(price * quantity) >= minimumTotal
(discount + tax) <= maximumAdjustment
((width * height) / 2) > minimumArea
~~~

Ví dụ, kiểm tra tổng tiền của đơn hàng:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression eligible = parser.parseExpression(
        "(#order.unitPrice * #order.quantity) "
        + "- #order.discount >= #minimumTotal"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Boolean accepted = eligible.getValue(context, Boolean.class);
~~~

Ngoặc quanh đơn giá nhân số lượng giúp người đọc nhận ra tổng tiền trước chiết khấu. Sau đó biểu thức trừ khoản giảm giá và so sánh với ngưỡng tối thiểu.

Với điều kiện có cả toán tử and/or, hãy nhóm các mệnh đề để thể hiện rõ ý định logic. Ngoặc quanh phần số học và ngoặc quanh nhóm điều kiện phục vụ hai mục đích khác nhau, nhưng đều làm cấu trúc biểu thức dễ hiểu hơn.

## 8. Ngoặc không thay đổi kiểu số hoặc quy tắc làm tròn

Ngoặc xác định thứ tự và phạm vi phép tính. Bản thân dấu ngoặc không chuyển Double thành BigDecimal, không biến phép chia thành phép chia chính xác và không làm tròn kết quả.

Ví dụ, nếu các toán hạng là Double thì:

~~~text
(0.1 + 0.2) * 10
~~~

vẫn sử dụng số học dấu phẩy động của Double. Thêm ngoặc không loại bỏ sai số biểu diễn nhị phân.

Nếu cần decimal cho tiền tệ, hãy dùng BigDecimal hoặc literal BigDecimal có hậu tố M:

~~~text
(0.10M + 0.20M) * 10M
~~~

Đối với phép chia BigDecimal có kết quả thập phân vô hạn, ứng dụng vẫn cần quy định scale và RoundingMode phù hợp. Hãy xử lý làm tròn ở bước nghiệp vụ xác định, thay vì kỳ vọng ngoặc giải quyết vấn đề độ chính xác.

Ngoài ra, cách nhóm có thể làm thay đổi kiểu của giá trị trung gian vì các toán tử được áp dụng theo từng bước. Khi kiểu kết quả là một phần của hợp đồng với method hoặc thuộc tính đích, hãy kiểm tra kiểu runtime trên phiên bản Spring thực tế.

## 9. Viết biểu thức dễ đọc và dễ bảo trì

Một biểu thức ngắn có thể không cần ngoặc ở mọi vị trí vì thứ tự ưu tiên đã rõ. Tuy nhiên, với biểu thức nghiệp vụ, một cặp ngoặc bổ sung thường đáng giá nếu nó thể hiện một khái niệm như tổng phụ, tỷ lệ, hệ số hoặc ngưỡng.

Một số nguyên tắc thực hành:

1. Đặt ngoặc quanh tử số và mẫu số khi công thức có nhiều toán hạng.
2. Đặt ngoặc quanh tổng hoặc hiệu cần được nhân/chia như một đơn vị.
3. Đặt ngoặc cho cơ số, số mũ và phạm vi của dấu âm khi biểu thức có lũy thừa.
4. Dùng khoảng trắng nhất quán quanh toán tử để dễ đọc.
5. Không lồng ngoặc quá sâu; cân nhắc đưa phần tính toán phức tạp vào biến hoặc method có tên rõ ràng.
6. Giữ các toán hạng cùng kiểu số khi cần độ chính xác xác định.
7. Viết ví dụ kiểm chứng với giá trị đầu vào đại diện, nhất là tại biên như 0, số âm, mẫu số 0 và giá trị rất lớn.

Không nên thêm ngoặc một cách máy móc vào mọi toán tử. Mục tiêu là làm rõ cấu trúc có ý nghĩa và giúp người đọc nhanh chóng xác định nhóm nào được tính trước.

## 10. Kiểm tra biểu thức bằng các trường hợp đối chiếu

Khi viết một công thức có ngoặc, hãy kiểm tra ít nhất hai dạng: công thức đúng theo ý định và một dạng dễ bị viết nhầm nếu bỏ ngoặc. Điều này giúp chứng minh cặp ngoặc thực sự quan trọng.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object withoutGrouping =
        parser.parseExpression("100 / 5 * 2").getValue();

Object withGrouping =
        parser.parseExpression("100 / (5 * 2)").getValue();

System.out.println(withoutGrouping); // 40
System.out.println(withGrouping);    // 10
~~~

Khi kiểm tra biểu thức trên object nghiệp vụ, hãy chuẩn bị dữ liệu có giá trị dễ tính bằng tay, rồi so sánh kết quả SpEL với kết quả mong đợi. Nếu biểu thức được lưu trong cấu hình, hãy kiểm tra đúng chuỗi sau khi placeholder được phân giải và trước khi đánh giá để phát hiện nhầm lẫn giữa hai lớp cú pháp.

Các trường hợp nên xem xét:

- Giá trị bằng 0 hoặc âm.
- Mẫu số bằng 0 hoặc gần 0.
- Các toán hạng có kiểu khác nhau.
- Giá trị lớn có nguy cơ vượt phạm vi kiểu số.
- Giá trị decimal cần scale hoặc làm tròn.
- Biểu thức có lũy thừa hoặc nhiều nhóm ngoặc lồng nhau.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả cộng nhân khác mong đợi | Quên rằng nhân/chia được ưu tiên trước cộng/trừ | Nhóm phần cần tính trước bằng ngoặc |
| Chia cho tổng nhưng kết quả quá lớn/nhỏ | Chỉ một phần mẫu số nằm trong phép chia | Đặt toàn bộ mẫu số trong ngoặc |
| Phép trừ cho kết quả sai | Nhầm thứ tự nhóm các phép trừ | Viết rõ nhóm cần trừ bằng ngoặc |
| Dấu âm áp dụng sai phạm vi | Không rõ dấu âm thuộc một số hay cả biểu thức | Dùng ngoặc quanh cơ số hoặc nhóm cần lấy số đối |
| Công thức tỷ lệ mất phần thập phân | Dùng kiểu số nguyên cho phép chia trung gian | Chọn kiểu decimal phù hợp và nhóm phép tính rõ ràng |
| Kết quả tiền tệ có sai số | Dùng Double/Float hoặc không có chính sách làm tròn | Dùng BigDecimal và xác định scale/rounding |
| Biểu thức khó đọc dù kết quả đúng | Quá nhiều toán tử và ngoặc lồng sâu | Tách thành biến hoặc method có tên mô tả ý nghĩa |

## 12. Ghi nhớ

Ngoặc tròn là công cụ thể hiện ý định trong biểu thức số học SpEL. Phép nhân, chia và lấy phần dư có ưu tiên cao hơn cộng và trừ; các phép cùng mức được xử lý theo thứ tự từ trái sang phải. Ngoặc cho phép nhóm tử số, mẫu số, tổng phụ, hệ số chiết khấu, cơ số hoặc toàn bộ phần cần mang dấu âm.

Ngoặc chỉ quyết định cách nhóm phép toán. Kiểu số, độ chính xác và làm tròn vẫn phụ thuộc vào literal, biến, toán tử và quy tắc nghiệp vụ. Hãy viết biểu thức theo cấu trúc mà người đọc có thể kiểm chứng bằng mắt, rồi xác nhận bằng các ví dụ có kết quả mong đợi rõ ràng.