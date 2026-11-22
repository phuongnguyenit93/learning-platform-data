# Literal số thập phân và các kiểu số được suy ra

Trong SpEL, literal số là giá trị số được viết trực tiếp trong biểu thức, chẳng hạn 12, 12.5 hoặc 1.25M. Cách viết literal ảnh hưởng đến kiểu Java mà parser tạo ra. Đây là chi tiết quan trọng khi biểu thức thực hiện phép tính, truyền kết quả vào method, gán vào thuộc tính hoặc inject vào field có kiểu cụ thể.

Đặc biệt, một số thập phân viết với dấu chấm không mặc nhiên trở thành BigDecimal. Trong SpEL, literal số thực không có hậu tố thường được suy ra là Double. Nếu cần biểu diễn số thập phân bằng BigDecimal, hãy dùng hậu tố M. Việc chọn đúng kiểu ngay từ literal giúp tránh sai số nhị phân và giảm các chuyển đổi kiểu ngoài ý muốn.

## 1. Literal số nguyên và literal số thực

SpEL hỗ trợ literal số nguyên và số thực. Cách viết quyết định nhóm kiểu số được parser chọn:

| Cách viết | Kiểu thường được suy ra | Ý nghĩa |
|---|---|---|
| 42 | Integer | Số nguyên mặc định |
| 42L | Long | Số nguyên có hậu tố L |
| 42.5 | Double | Số thực mặc định |
| 42.5D | Double | Chỉ rõ kiểu Double |
| 42.5F | Float | Chỉ rõ kiểu Float |
| 42.5M | BigDecimal | Số thập phân theo biểu diễn decimal |

Các hậu tố chữ cái có thể được viết theo dạng hoa hoặc thường theo cú pháp SpEL. Trong code và tài liệu, nên thống nhất cách viết hoa L, D, F, M để dễ nhận biết.

Điểm cần nhớ là 42.5 và 42.5M có cùng giá trị toán học theo cách viết thông thường, nhưng không cùng kiểu Java. Literal đầu tiên là Double; literal thứ hai là BigDecimal.

## 2. Vì sao literal số thập phân mặc định là Double?

Khi parser gặp một literal có phần thập phân hoặc dạng số mũ mà không có hậu tố chỉ định kiểu khác, SpEL mặc định tạo giá trị Double.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object value = parser.parseExpression("12.50").getValue();

System.out.println(value);                      // 12.5
System.out.println(value.getClass().getName()); // java.lang.Double
~~~

Dấu chấm trong literal biểu thị số thực, nhưng nó không nói rằng ứng dụng muốn dùng BigDecimal. Double là kiểu dấu phẩy động nhị phân 64-bit của Java. Nhiều phân số thập phân quen thuộc, ví dụ 0.1, không có biểu diễn nhị phân hữu hạn chính xác. Vì vậy, giá trị lưu trong Double có thể là số gần đúng.

Đối với tính toán khoa học, thống kê, đồ họa hoặc các trường hợp chấp nhận sai số dấu phẩy động, Double thường phù hợp. Với tiền tệ, thuế, tỷ lệ phần trăm cần quy tắc làm tròn rõ ràng hoặc dữ liệu tài chính, BigDecimal thường là lựa chọn thích hợp hơn.

Không nên suy ra kiểu dữ liệu chỉ từ cách hiển thị của số. Hai giá trị có thể cùng được in thành 12.5 nhưng một giá trị là Double và giá trị kia là BigDecimal.

## 3. Dùng hậu tố M để tạo BigDecimal

SpEL hỗ trợ hậu tố M hoặc m để chỉ rõ một literal BigDecimal. Tính năng này có từ Spring Framework 5.3.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object decimal = parser.parseExpression("12.50M").getValue();

System.out.println(decimal);                      // 12.50
System.out.println(decimal.getClass().getName()); // java.math.BigDecimal
~~~

Hậu tố M đặc biệt hữu ích khi viết biểu thức trong annotation, rule hoặc cấu hình vì nó giúp thể hiện ý định kiểu ngay tại vị trí literal:

~~~java
@Value("#{12.50M}")
private BigDecimal unitPrice;
~~~

Trong ví dụ này, biểu thức trả về BigDecimal. Spring inject kết quả vào field BigDecimal mà không cần dựa vào việc chuyển một Double sang BigDecimal.

Có thể dùng literal BigDecimal trong các biểu thức tính toán:

~~~text
(19.90M * 3) + 5.00M
~~~

Khi thiết kế biểu thức tiền tệ, nên giữ các toán hạng ở kiểu decimal nhất quán và xác định rõ quy tắc scale, precision và làm tròn ở nơi phù hợp. Hậu tố M chọn kiểu BigDecimal cho literal; nó không tự quyết định chính sách làm tròn của nghiệp vụ.

## 4. Hậu tố F, D và L

Ngoài M, các hậu tố giúp chỉ rõ kiểu số khác.

### 4.1. Float với F

~~~java
Object value = parser.parseExpression("3.14F").getValue();

System.out.println(value.getClass().getName()); // java.lang.Float
~~~

Float dùng 32 bit và có độ chính xác thấp hơn Double. Chỉ dùng khi kiểu Float là một phần của hợp đồng dữ liệu hoặc có lý do về bộ nhớ/interop cụ thể. Không nên chọn Float cho tiền tệ.

### 4.2. Double với D

~~~java
Object value = parser.parseExpression("3.14D").getValue();

System.out.println(value.getClass().getName()); // java.lang.Double
~~~

D làm rõ ý định dùng Double. Với literal số thực không có hậu tố, đây cũng là kiểu mặc định.

### 4.3. Long với L

~~~java
Object value = parser.parseExpression("9000000000L").getValue();

System.out.println(value.getClass().getName()); // java.lang.Long
~~~

Hậu tố L chỉ ra literal số nguyên kiểu Long. Nó hữu ích với số nguyên lớn hơn phạm vi Integer và khi method hoặc thuộc tính đích yêu cầu Long.

Các hậu tố xác định kiểu của literal đầu vào. Kiểu kết quả sau một phép toán còn phụ thuộc vào các toán hạng và cách toán tử xử lý chúng.

## 5. Số mũ và cách viết số thập phân

SpEL chấp nhận cách viết số thực với ký pháp số mũ. Ví dụ:

~~~text
1.5e3
2.75E-2
1.5e3M
~~~

Ký pháp này biểu diễn lần lượt 1500, 0.0275 và 1500 dưới dạng BigDecimal khi có hậu tố M. Dạng số mũ thuận tiện với các giá trị rất lớn hoặc rất nhỏ, nhưng có thể khó đọc trong cấu hình nghiệp vụ nếu người đọc quen với cách viết thập phân thông thường.

Khi viết literal trong rule hoặc cấu hình được nhiều người bảo trì, hãy ưu tiên định dạng giúp người đọc nhận ra ngay đơn vị và độ lớn. Nếu giá trị là tiền, hãy ghi rõ đơn vị ở tên biến hoặc tài liệu xung quanh; SpEL chỉ nhìn thấy con số và kiểu số, không biết nó là đồng, đô la hay phần trăm.

## 6. Kiểm tra kiểu thực tế mà parser tạo ra

Khi chưa chắc parser suy ra kiểu nào, hãy lấy giá trị dưới dạng Object rồi kiểm tra class thực tế. Đừng yêu cầu parser chuyển ngay sang một kiểu đích nếu mục tiêu là kiểm tra kiểu gốc của literal.

~~~java
ExpressionParser parser = new SpelExpressionParser();

String[] literals = {
        "12",
        "12L",
        "12.5",
        "12.5D",
        "12.5F",
        "12.5M"
};

for (String source : literals) {
    Object value = parser.parseExpression(source).getValue();

    System.out.printf(
            "%-8s -> %-20s value=%s%n",
            source,
            value.getClass().getSimpleName(),
            value
    );
}
~~~

Kết quả minh họa:

~~~text
12       -> Integer              value=12
12L      -> Long                 value=12
12.5     -> Double               value=12.5
12.5D    -> Double               value=12.5
12.5F    -> Float                value=12.5
12.5M    -> BigDecimal           value=12.5
~~~

Nếu gọi getValue(BigDecimal.class) hoặc một overload có kiểu kết quả, Spring có thể chuyển đổi giá trị sang kiểu được yêu cầu nếu converter hỗ trợ. Khi kiểm tra type inference, hãy dùng getValue() trả về Object để phân biệt kiểu literal ban đầu với kiểu sau chuyển đổi.

## 7. Kiểu literal và kiểu kết quả của phép toán

Không nên cho rằng kiểu của kết quả luôn giống kiểu của literal đầu tiên. Một biểu thức có thể kết hợp nhiều kiểu số; toán tử và cơ chế chuyển đổi sẽ quyết định cách thực hiện phép toán và kiểu kết quả.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object a = parser.parseExpression("10 + 2").getValue();
Object b = parser.parseExpression("10.5 + 2.5").getValue();
Object c = parser.parseExpression("10.5M + 2.5M").getValue();

System.out.println(a.getClass().getName());
System.out.println(b.getClass().getName());
System.out.println(c.getClass().getName());
~~~

Các biểu thức số nguyên thuần, số thực mặc định và BigDecimal literal đi qua các đường xử lý số khác nhau. Nếu kiểu kết quả là một phần của API hoặc được truyền vào method overload, hãy kiểm tra nó bằng một phép thử nhỏ trên đúng phiên bản Spring mà ứng dụng đang chạy.

Đặc biệt, khi trộn BigDecimal với Double hoặc Float, đừng dựa vào giả định rằng mọi phép toán sẽ tự động chuyển sang BigDecimal theo ý muốn. Hãy viết các literal cùng kiểu, hoặc chuyển đổi rõ ràng ở ranh giới dữ liệu. Điều này giúp tránh phụ thuộc vào quy tắc chuyển đổi ngầm và tránh đưa sai số dấu phẩy động vào phép tính decimal.

## 8. BigDecimal, độ chính xác và scale

BigDecimal biểu diễn số thập phân bằng một giá trị nguyên không dấu phẩy động và một scale. Điều này phù hợp với nhiều bài toán cần biểu diễn decimal theo quy tắc rõ ràng.

Ví dụ:

~~~java
BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);

System.out.println(total); // 59.70
~~~

Trong SpEL, có thể viết các literal tương ứng với hậu tố M:

~~~text
19.90M * 3M
~~~

Dùng BigDecimal không có nghĩa mọi phép toán tự động có kết quả theo scale nghiệp vụ mong muốn. Phép chia có thể tạo ra số thập phân vô hạn; khi đó Java BigDecimal cần quy tắc scale và RoundingMode thích hợp. Các phép tính tiền tệ thường cần quy định làm tròn ở bước nghiệp vụ xác định, ví dụ khi tính thuế, phân bổ chiết khấu hoặc tổng hợp dòng hàng.

Ngoài ra, scale là một phần của BigDecimal. 19.90M và 19.9M có cùng giá trị số học nhưng scale khác nhau. Nếu nghiệp vụ quan tâm số chữ số thập phân hiển thị hoặc so sánh bằng BigDecimal.equals() trong Java, hãy xử lý scale có chủ đích. Khi so sánh giá trị số học trong Java, compareTo() thường phù hợp hơn nếu scale không cần phải giống nhau.

## 9. Chuyển đổi kiểu khi đưa kết quả vào Java hoặc Spring

Kết quả SpEL có thể được yêu cầu dưới dạng một kiểu Java cụ thể:

~~~java
Expression expression = parser.parseExpression("12.50M");

BigDecimal amount = expression.getValue(BigDecimal.class);
~~~

Hoặc inject trực tiếp trong Spring:

~~~java
@Component
public class PricingDefaults {

    @Value("#{12.50M}")
    private BigDecimal defaultPrice;

    @Value("#{0.15M}")
    private BigDecimal taxRate;

    @Value("#{3.5}")
    private double measurement;
}
~~~

Ví dụ trên làm rõ ý định: giá và thuế là BigDecimal, còn đại lượng đo lường dùng Double. Kiểu field không thay đổi cách parser đã tạo literal; nó là kiểu đích mà cơ chế đánh giá/chuyển đổi cần cung cấp.

Cần phân biệt hai tình huống cấu hình:

- @Value với một biểu thức SpEL như #{12.50M} yêu cầu Spring đánh giá biểu thức và literal đã mang kiểu BigDecimal.
- @Value với placeholder thuộc tính cấu hình lấy chuỗi từ property source rồi chuyển đổi sang kiểu field theo conversion service. Đây không phải là SpEL decimal literal.

Nếu cấu hình ngoài chứa chuỗi "12.50", việc inject vào BigDecimal dựa trên converter của Spring, không dựa trên hậu tố M trong SpEL. Hãy chọn đúng cơ chế theo nguồn dữ liệu và mục tiêu.

## 10. Dùng literal số trong điều kiện và rule

Literal số thường được dùng trong điều kiện:

~~~text
age >= 18
temperature < 37.5
total >= 100.00M
discountRate <= 0.15M
~~~

Trong biểu thức rule, kiểu số nên tương thích với kiểu của thuộc tính được so sánh. Nếu domain object dùng BigDecimal cho amount, nên dùng literal BigDecimal để biểu đạt ngưỡng. Nếu domain object dùng Integer cho count, literal số nguyên thường đủ rõ.

Ví dụ trong Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression rule = parser.parseExpression(
        "total >= 100.00M and itemCount >= 2"
);

boolean accepted = Boolean.TRUE.equals(
        rule.getValue(context, Boolean.class)
);
~~~

Khi biểu thức được cấu hình bởi người vận hành, hãy ghi rõ đơn vị, kiểu dữ liệu và quy tắc làm tròn của từng ngưỡng. 0.15M có thể là 15% dưới dạng tỷ lệ, nhưng SpEL không biết đó là tỷ lệ phần trăm nếu ứng dụng không quy định.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Giá trị 12.50 là Double dù field là BigDecimal | Literal mặc định của số thực là Double | Dùng 12.50M nếu muốn literal BigDecimal |
| Kết quả phép tính có sai số nhỏ | Đang dùng Double/Float cho phân số thập phân | Dùng BigDecimal literal và giữ toán hạng cùng kiểu |
| Method không nhận được tham số như mong đợi | Kiểu literal khác kiểu overload được chọn | Kiểm tra kiểu runtime và signature method |
| Chuyển đổi sang kiểu đích thất bại | Không có converter phù hợp hoặc giá trị không tương thích | Kiểm tra kiểu trả về, TypeConverter và kiểu field |
| Chia BigDecimal phát sinh lỗi | Kết quả có khai triển thập phân vô hạn mà không có scale/rounding phù hợp | Xác định scale và RoundingMode trong logic nghiệp vụ |
| Kết quả hiển thị khác số chữ số mong đợi | Giá trị số học và định dạng hiển thị là hai việc khác nhau | Format ở lớp trình bày, quy định scale khi tính toán |
| So sánh BigDecimal trong Java cho kết quả bất ngờ | equals() xét cả scale | Dùng compareTo() khi cần so sánh giá trị số học |

## 12. Ghi nhớ

Literal số thập phân không có hậu tố trong SpEL mặc định là Double. Hậu tố D chỉ rõ Double, F chọn Float, L chọn Long cho số nguyên và M chọn BigDecimal. Nếu cần decimal chính xác, hãy dùng M ngay trong biểu thức thay vì trông chờ chuyển đổi từ Double sau đó.

Kiểu của literal là điểm bắt đầu; kiểu kết quả phép toán còn phụ thuộc các toán hạng, toán tử và chuyển đổi. Hãy kiểm tra kiểu runtime khi nó ảnh hưởng đến method overload hoặc hợp đồng dữ liệu, giữ kiểu số nhất quán trong biểu thức, và xử lý scale/làm tròn ở tầng nghiệp vụ.