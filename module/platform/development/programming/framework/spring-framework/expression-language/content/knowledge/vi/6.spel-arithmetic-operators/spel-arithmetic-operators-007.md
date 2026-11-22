# Giới hạn độ chính xác và khả năng tràn số

## Mục tiêu

Sau bài này, bạn có thể nhận biết các rủi ro số học khi dùng Spring Expression Language (SpEL): sai số của số thực dấu phẩy động, tràn số nguyên có giới hạn, khác biệt giữa độ chính xác và scale của BigDecimal, cũng như cách phép chia cần quy tắc làm tròn rõ ràng. Bạn sẽ biết cách truyền BigInteger và BigDecimal vào biểu thức, chọn phép toán phù hợp, và kiểm tra các giá trị biên trước khi đưa biểu thức vào ứng dụng.

## 1. Vì sao biểu thức số học có thể cho kết quả bất ngờ?

SpEL cung cấp các toán tử số học như cộng, trừ, nhân, chia, lấy dư và lũy thừa. Tuy nhiên, SpEL thực hiện các phép toán dựa trên kiểu số của toán hạng và cơ chế xử lý số của Java. Vì vậy, biểu thức ngắn không tự động có độ chính xác vô hạn.

Ba nhóm vấn đề thường gặp:

- **Sai số biểu diễn:** một số thập phân không thể biểu diễn chính xác bằng kiểu dấu phẩy động nhị phân như ¤float¤ hoặc ¤double¤.
- **Tràn số (overflow):** kết quả vượt phạm vi của kiểu số nguyên có giới hạn như ¤int¤ hoặc ¤long¤.
- **Làm tròn và scale:** phép chia hoặc phép tính tiền tệ có thể cần số chữ số thập phân cụ thể và một chính sách làm tròn được quy định.

Điều quan trọng là xác định kiểu dữ liệu của từng toán hạng trước khi đánh giá biểu thức. Hai biểu thức có cùng hình thức nhưng dùng kiểu số khác nhau có thể có độ chính xác, phạm vi và kết quả khác nhau.

## 2. Số nguyên có giới hạn và hiện tượng tràn số

Các kiểu nguyên thủy và lớp bao tương ứng trong Java có phạm vi hữu hạn. Ví dụ:

- ¤byte¤: từ -128 đến 127.
- ¤short¤: từ -32.768 đến 32.767.
- ¤int¤: từ -2.147.483.648 đến 2.147.483.647.
- ¤long¤: từ -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807.

Nếu kết quả phép tính vượt giới hạn của kiểu nguyên, Java có thể giữ lại các bit thấp theo biểu diễn số nguyên có dấu. Điều này dẫn đến tràn số thay vì tự động mở rộng sang kiểu lớn hơn.

Ví dụ, truyền các biến kiểu Integer vào SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#max + #one");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("max", Integer.MAX_VALUE);
context.setVariable("one", 1);

Integer result = expression.getValue(context, Integer.class);
~~~

Với hai toán hạng ¤Integer¤, phép cộng có thể tràn và cho kết quả ¤-2147483648¤. Việc yêu cầu kết quả qua ¤getValue(context, Integer.class)¤ không biến phép cộng bên trong thành phép cộng số nguyên không giới hạn.

Có thể gặp tình huống tương tự với ¤long¤ khi kết quả vượt ¤Long.MAX_VALUE¤ hoặc thấp hơn ¤Long.MIN_VALUE¤.

### 2.1. Cách tránh tràn số nguyên

Nếu miền giá trị có thể vượt phạm vi ¤long¤, hãy dùng ¤BigInteger¤ hoặc một kiểu số có phạm vi phù hợp trước khi thực hiện phép tính.

Ví dụ:

~~~java
context.setVariable("max", BigInteger.valueOf(Long.MAX_VALUE));
context.setVariable("one", BigInteger.ONE);

Expression expression =
    parser.parseExpression("#max.add(#one)");

BigInteger result =
    expression.getValue(context, BigInteger.class);
~~~

¤BigInteger¤ lưu số nguyên với độ dài tùy theo bộ nhớ khả dụng, nên không gặp tràn số theo giới hạn cố định 32 hoặc 64 bit. Tuy nhiên, nó vẫn có chi phí bộ nhớ và CPU; không nên dùng một cách thiếu kiểm soát cho giá trị đầu vào có kích thước tùy ý.

Nếu muốn giữ kiểu ¤int¤ hoặc ¤long¤, hãy kiểm tra giới hạn trước khi cộng hoặc nhân. Java có các phương thức như ¤Math.addExact(...)¤ và ¤Math.multiplyExact(...)¤ để phát hiện tràn số bằng ngoại lệ. Có thể đặt phép kiểm tra này trong một phương thức Java được kiểm soát và chỉ đưa kết quả đã xác thực vào context của SpEL.

## 3. Sai số của float và double

¤float¤ và ¤double¤ dùng biểu diễn dấu phẩy động nhị phân. Nhiều phân số thập phân thông dụng không có biểu diễn nhị phân hữu hạn. Vì vậy, giá trị được lưu thường là một số gần đúng.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("0.1 + 0.2");

Double result = expression.getValue(Double.class);
System.out.println(result);
~~~

Kết quả có thể hiển thị gần ¤0.30000000000000004¤ thay vì chính xác ¤0.3¤. Đây là đặc tính của số dấu phẩy động nhị phân, không phải lỗi riêng của SpEL.

Sai số nhỏ có thể tích lũy qua nhiều phép tính. Nếu dùng ¤double¤ để cộng dồn số tiền, tính lãi, tính tỷ lệ hoặc so sánh một ngưỡng chính xác, kết quả có thể lệch so với quy tắc nghiệp vụ.

¤double¤ vẫn phù hợp với nhiều phép tính khoa học, thống kê hoặc đồ họa nơi sai số gần đúng được chấp nhận. Điều cần tránh là dùng nó cho đại lượng cần biểu diễn thập phân chính xác mà không có chính sách xử lý sai số.

## 4. Dùng BigInteger cho số nguyên lớn

¤BigInteger¤ biểu diễn số nguyên có độ dài tùy ý, hữu ích khi giá trị có thể vượt phạm vi của ¤long¤, chẳng hạn số đếm lớn, mã hóa số học hoặc các phép tính tổ hợp.

Có thể truyền biến ¤BigInteger¤ vào SpEL rồi gọi các phương thức số học:

~~~java
BigInteger left = new BigInteger("9223372036854775808");
BigInteger right = new BigInteger("10000000000000000000");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("left", left);
context.setVariable("right", right);

Expression expression =
    parser.parseExpression("#left.multiply(#right)");

BigInteger product =
    expression.getValue(context, BigInteger.class);
~~~

Các phương thức như ¤add¤, ¤subtract¤, ¤multiply¤, ¤divide¤ và ¤remainder¤ cho phép làm việc với số nguyên lớn mà không bị tràn theo giới hạn cố định của kiểu nguyên thủy.

Phép chia ¤BigInteger¤ vẫn là phép chia số nguyên: phần thập phân bị loại bỏ. Nếu nghiệp vụ cần phần thập phân, hãy dùng ¤BigDecimal¤ hoặc một mô hình dữ liệu khác phù hợp.

## 5. Dùng BigDecimal cho số thập phân cần độ chính xác

¤BigDecimal¤ biểu diễn số thập phân bằng một số nguyên không scale (unscaled value) cùng với scale. Nó phù hợp cho tiền tệ, đơn giá, thuế, tỷ lệ và các phép tính mà chữ số thập phân có ý nghĩa nghiệp vụ.

Nên tạo ¤BigDecimal¤ từ chuỗi thập phân:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.08");
~~~

Không nên tạo trực tiếp từ một giá trị ¤double¤ nếu cần giữ chính xác biểu diễn thập phân ban đầu:

~~~java
BigDecimal risky = new BigDecimal(0.1);
BigDecimal preferred = new BigDecimal("0.1");
~~~

¤risky¤ nhận giá trị nhị phân gần đúng mà ¤double¤ đang lưu, sau đó biểu diễn chính xác giá trị gần đúng đó dưới dạng thập phân. ¤preferred¤ bắt đầu từ chuỗi "0.1" nên biểu diễn đúng giá trị thập phân mong muốn.

Có thể dùng ¤BigDecimal¤ trong biểu thức SpEL bằng cách truyền biến từ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#price.multiply(#quantity)");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("19.99"));
context.setVariable("quantity", new BigDecimal("3"));

BigDecimal subtotal =
    expression.getValue(context, BigDecimal.class);
~~~

Khi các toán hạng là ¤BigDecimal¤, phép toán tương ứng có thể giữ cách biểu diễn thập phân. Tuy nhiên, cần xác định rõ scale và chính sách làm tròn ở những bước nghiệp vụ yêu cầu chúng.

## 6. Phân biệt precision và scale của BigDecimal

Hai khái niệm này thường bị nhầm lẫn:

- **Precision:** tổng số chữ số có nghĩa của giá trị.
- **Scale:** số chữ số nằm bên phải dấu thập phân.

Ví dụ:

| Giá trị | Precision | Scale |
|---|---:|---:|
| ¤12.34¤ | 4 | 2 |
| ¤0.0012¤ | 2 | 4 |
| ¤1200¤ | 4 | 0 |
| ¤1.2300¤ | 5 | 4 |

Hai giá trị ¤1.23¤ và ¤1.2300¤ có cùng giá trị số khi so sánh bằng ¤compareTo¤, nhưng có scale khác nhau. Scale có thể ảnh hưởng đến định dạng, phép chia và cách biểu diễn kết quả.

Một số phương thức hữu ích:

~~~java
value.precision();
value.scale();
value.setScale(2, RoundingMode.HALF_UP);
~~~

¤setScale(2, ...)¤ tạo một giá trị có hai chữ số sau dấu thập phân theo quy tắc làm tròn được chọn. Đây là cách diễn đạt một yêu cầu nghiệp vụ như “lưu số tiền đến hai chữ số thập phân”.

Không nên đồng nhất precision với số chữ số sau dấu thập phân. Nếu nghiệp vụ giới hạn tổng số chữ số có nghĩa, cần dùng precision hoặc ¤MathContext¤; nếu nghiệp vụ yêu cầu số chữ số sau dấu thập phân cố định, cần dùng scale.

## 7. Phép chia và quy tắc làm tròn

Phép chia là nơi precision và scale thường trở nên quan trọng. Một số kết quả thập phân có biểu diễn hữu hạn, ví dụ ¤1 / 4 = 0.25¤. Một số kết quả có biểu diễn thập phân vô hạn tuần hoàn, ví dụ ¤1 / 3¤.

Với ¤BigDecimal¤, phép chia chính xác không giới hạn scale có thể không thực hiện được nếu kết quả là số thập phân vô hạn tuần hoàn. Java có thể ném ¤ArithmeticException¤ khi không cung cấp quy tắc làm tròn phù hợp.

Hãy chỉ rõ scale và ¤RoundingMode¤ khi cần kết quả có số chữ số thập phân cố định:

~~~java
BigDecimal amount = new BigDecimal("10");
BigDecimal divisor = new BigDecimal("3");

BigDecimal result =
    amount.divide(divisor, 2, RoundingMode.HALF_UP);
// 3.33
~~~

Có thể gọi phương thức này từ SpEL:

~~~java
Expression expression =
    parser.parseExpression(
        "#amount.divide(#divisor, #scale, #rounding)"
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("amount", new BigDecimal("10"));
context.setVariable("divisor", new BigDecimal("3"));
context.setVariable("scale", 2);
context.setVariable("rounding", RoundingMode.HALF_UP);

BigDecimal result =
    expression.getValue(context, BigDecimal.class);
~~~

¤RoundingMode.HALF_UP¤ là một lựa chọn phổ biến, nhưng không phải lúc nào cũng là quy tắc đúng. Nghiệp vụ có thể yêu cầu ¤HALF_EVEN¤, ¤DOWN¤, ¤CEILING¤ hoặc một chính sách khác. Hãy thống nhất quy tắc làm tròn với yêu cầu tài chính và áp dụng ở đúng bước của quy trình.

Nếu cần giới hạn số chữ số có nghĩa thay vì số chữ số sau dấu thập phân, có thể dùng ¤MathContext¤:

~~~java
MathContext mathContext =
    new MathContext(8, RoundingMode.HALF_EVEN);

BigDecimal result = amount.divide(divisor, mathContext);
~~~

Precision trong ¤MathContext¤ là số chữ số có nghĩa, không phải scale. Việc chọn ¤MathContext¤ hay ¤setScale¤ phụ thuộc vào loại giới hạn mà nghiệp vụ đặt ra.

## 8. So sánh BigDecimal đúng cách

¤BigDecimal.equals(...)¤ xét cả giá trị và scale. Vì thế:

~~~java
new BigDecimal("1.0").equals(new BigDecimal("1.00")) // false
~~~

Trong khi:

~~~java
new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0 // true
~~~

Nếu muốn so sánh giá trị số mà không quan tâm scale, hãy dùng ¤compareTo¤:

~~~text
#left.compareTo(#right) == 0
#left.compareTo(#limit) >= 0
~~~

Điều này hữu ích khi viết điều kiện SpEL cho số tiền hoặc ngưỡng thập phân. Nếu dùng phép bằng ¤==¤ trên ¤BigDecimal¤, cần hiểu rõ quy tắc so sánh mà biểu thức đang áp dụng và khác biệt giữa so sánh đối tượng với so sánh giá trị số.

## 9. Chuyển đổi kiểu không thay thế kiểm tra phạm vi

SpEL có thể chuyển đổi giá trị thông qua cơ chế ¤TypeConverter¤ của ¤EvaluationContext¤, và ¤getValue(...)¤ có thể được yêu cầu trả về một kiểu đích.

Ví dụ:

~~~java
Integer count = expression.getValue(context, Integer.class);
~~~

Yêu cầu kiểu kết quả không đảm bảo phép tính trước đó không tràn số. Nếu biểu thức đã tính bằng ¤Integer¤ và bị tràn, việc chuyển kết quả sang một kiểu khác không thể khôi phục giá trị đúng ban đầu.

Tương tự, chuyển một số thực dấu phẩy động sang ¤BigDecimal¤ không thể tự động khôi phục phần thập phân đã mất do biểu diễn nhị phân. Hãy chọn kiểu số ngay từ đầu, trước khi thực hiện phép toán.

Nếu cần giới hạn miền giá trị, hãy kiểm tra trước hoặc sau phép tính tại lớp Java:

~~~java
if (quantity < 0 || quantity > MAX_ALLOWED_QUANTITY) {
    throw new IllegalArgumentException("Quantity is out of range");
}
~~~

Với phép cộng hoặc nhân kiểu nguyên thủy, cân nhắc ¤Math.addExact¤ và ¤Math.multiplyExact¤. Với ¤BigDecimal¤, kiểm tra scale, precision và giới hạn nghiệp vụ bằng các phương thức thích hợp.

## 10. Kiểm soát sai số trong bài toán tiền tệ

Với tiền tệ, hãy quyết định rõ:

1. Đơn vị tiền và số chữ số thập phân được lưu.
2. Kiểu dữ liệu sử dụng trong toàn bộ phép tính.
3. Thời điểm làm tròn: sau từng dòng hàng, sau tổng đơn hàng, hay khi ghi sổ.
4. Quy tắc làm tròn áp dụng.
5. Cách xử lý số âm, hoàn tiền, thuế và tỷ lệ chiết khấu.
6. Giới hạn giá trị hợp lệ và cách xử lý khi vượt giới hạn.

Ví dụ tính tổng dòng hàng:

~~~java
BigDecimal unitPrice = new BigDecimal("12.345");
BigDecimal quantity = new BigDecimal("3");

BigDecimal lineTotal = unitPrice.multiply(quantity)
    .setScale(2, RoundingMode.HALF_UP);
// 37.04
~~~

Nếu làm tròn đơn giá trước khi nhân, kết quả có thể khác với việc nhân chính xác rồi làm tròn tổng dòng. Hai cách có thể đều hợp lệ trong những nghiệp vụ khác nhau; điều quan trọng là chọn đúng quy tắc và áp dụng nhất quán.

SpEL nên thể hiện phép tính ngắn khi dữ liệu đã được chuẩn hóa và kiểu số đã được lựa chọn. Những quy tắc tài chính phức tạp, cần audit hoặc phối hợp nhiều bước, nên nằm trong service Java để dễ kiểm thử và kiểm soát.

## 11. Kiểm thử các giá trị biên

Không nên chỉ kiểm thử một vài giá trị thông thường. Với biểu thức số học, cần có dữ liệu ở sát ranh giới và trường hợp đặc biệt:

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Giá trị bằng ¤Integer.MAX_VALUE¤ | Phép cộng hoặc nhân có vượt phạm vi không |
| Giá trị bằng ¤Long.MAX_VALUE¤ | Có cần dùng BigInteger không |
| Giá trị âm sát giới hạn | Tràn số theo chiều âm |
| ¤0.1 + 0.2¤ | Sai số dấu phẩy động |
| Chia cho 0 | Lỗi số học và cách ứng dụng xử lý |
| ¤1 / 3¤ với BigDecimal | Có cung cấp scale hoặc MathContext không |
| ¤1.0¤ và ¤1.00¤ | So sánh giá trị và scale |
| Giá trị rất lớn hoặc scale rất cao | Giới hạn precision, bộ nhớ và chi phí tính toán |
| Giá trị null hoặc sai kiểu | Lỗi chuyển đổi và lỗi đánh giá |

Có thể tạo các ¤Expression¤ riêng để kiểm thử cùng một quy tắc với nhiều bộ dữ liệu. Với mỗi trường hợp, hãy xác định trước kết quả mong đợi hoặc loại lỗi mong đợi. Điều này giúp phát hiện sự khác biệt giữa kiểu số đầu vào, cách làm tròn và kết quả mà ứng dụng sử dụng.

## 12. Ghi nhớ

SpEL cung cấp toán tử số học, nhưng độ chính xác và phạm vi kết quả phụ thuộc vào kiểu số thực tế. ¤int¤ và ¤long¤ có thể tràn; ¤float¤ và ¤double¤ có sai số biểu diễn nhị phân; ¤BigInteger¤ phù hợp với số nguyên lớn; ¤BigDecimal¤ phù hợp với số thập phân cần kiểm soát.

Với ¤BigDecimal¤, hãy phân biệt precision và scale, tạo giá trị từ chuỗi thập phân, chỉ rõ scale và ¤RoundingMode¤ khi chia hoặc làm tròn, và dùng ¤compareTo¤ khi cần so sánh giá trị không phụ thuộc scale.

Đừng dựa vào chuyển đổi kiểu ở cuối biểu thức để sửa sai số hoặc tràn đã xảy ra trước đó. Hãy chọn kiểu số trước phép tính, kiểm tra giới hạn, quy định chính sách làm tròn và kiểm thử các giá trị biên.