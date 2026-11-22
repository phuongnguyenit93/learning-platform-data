# Chuyển đổi kiểu khi hai toán hạng khác nhau trong SpEL

Trong Spring Expression Language (SpEL), hai toán hạng của một phép toán số học có thể mang kiểu Java khác nhau, chẳng hạn Integer và Long, Integer và Double hoặc Integer và BigDecimal. Kết quả phụ thuộc vào kiểu runtime của các toán hạng và cách SpEL xử lý toán tử tương ứng. Cần phân biệt **thăng hạng kiểu số khi tính toán** với **chuyển đổi kiểu qua TypeConverter** của EvaluationContext: hai cơ chế này có liên quan nhưng không đồng nghĩa.

## 1. Kiểu runtime của toán hạng ảnh hưởng kết quả

Các giá trị trong biểu thức có thể đến từ literal, root object, property hoặc biến. Khi một toán tử được đánh giá, SpEL nhận các giá trị runtime của hai toán hạng. Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("count", Integer.valueOf(10));
    context.setVariable("total", Long.valueOf(20));

    ExpressionParser parser = new SpelExpressionParser();
    Object result = parser.parseExpression("#count + #total")
            .getValue(context);

Ở đây `#count` là Integer và `#total` là Long. SpEL xử lý phép cộng trên hai giá trị số và kết quả mang kiểu số phù hợp với phép toán. Vì có Long tham gia, kết quả của phép cộng này là Long.

Điều quan trọng là SpEL đánh giá giá trị thực tế được truyền vào context. Một biến khai báo ở Java là Number vẫn có thể chứa Integer, Long, Double, BigDecimal hoặc kiểu số khác; kiểu runtime đó ảnh hưởng cách toán tử hoạt động.

## 2. Thăng hạng kiểu số (numeric promotion)

Khi cả hai toán hạng đều là Number, các toán tử số học của SpEL xử lý chúng theo các quy tắc số học tương ứng và chọn kiểu kết quả phù hợp với loại toán hạng. Một số trường hợp thường gặp:

| Toán hạng trái | Toán hạng phải | Kết quả thường gặp |
|---|---|---|
| Integer | Integer | Integer |
| Integer | Long | Long |
| Integer | Float | Float |
| Integer | Double | Double |
| Integer | BigInteger | BigInteger |
| Integer | BigDecimal | BigDecimal |

Ví dụ:

    context.setVariable("integerValue", 10);
    context.setVariable("longValue", 20L);
    context.setVariable("doubleValue", 2.5d);

    Object longResult = parser.parseExpression(
            "#integerValue + #longValue"
    ).getValue(context);

    Object doubleResult = parser.parseExpression(
            "#integerValue + #doubleValue"
    ).getValue(context);

Phép cộng thứ nhất kết hợp Integer và Long, nên kết quả là Long. Phép cộng thứ hai kết hợp Integer và Double, nên kết quả là Double.

Đừng chỉ nhìn vào cách viết literal để suy ra kiểu. Ví dụ `10` là literal số nguyên, `10L` là Long, `10.0` là Double và `10.0F` là Float. Khi giá trị đến từ biến hoặc property, hãy kiểm tra kiểu runtime thay vì suy đoán từ tên biến.

Thăng hạng kiểu không làm cho kiểu số trở nên vô hạn chính xác. Nếu một toán hạng là Float hoặc Double, kết quả vẫn chịu giới hạn của floating point. Nếu cần giữ độ chính xác thập phân, hãy dùng BigDecimal cho cả hai toán hạng.

## 3. Phép chia và kiểu kết quả

Kiểu toán hạng đặc biệt quan trọng với phép chia. Khi chia hai số nguyên, phần thập phân có thể bị loại bỏ theo phép chia số nguyên:

    parser.parseExpression("1 / 2").getValue();       // 0
    parser.parseExpression("1.0 / 2").getValue();     // 0.5

Ở biểu thức thứ nhất, cả hai toán hạng là số nguyên nên phép chia cho kết quả nguyên. Ở biểu thức thứ hai, một toán hạng là Double, vì vậy kết quả có phần thập phân.

Nếu nghiệp vụ cần kết quả chính xác, đừng cố sửa kiểu sau khi phép chia đã xảy ra. Chuyển hoặc tạo toán hạng về kiểu phù hợp trước khi thực hiện phép toán.

Với BigDecimal, hãy tạo cả tử số và mẫu số dưới dạng BigDecimal trước khi chia. Phép chia BigDecimal có thể không có biểu diễn thập phân hữu hạn, ví dụ 1 chia 3; trong trường hợp đó cần chỉ định scale và rounding mode trong logic Java hoặc gọi một phương thức phù hợp để kiểm soát kết quả.

## 4. Phân biệt numeric promotion với TypeConverter

EvaluationContext cung cấp một TypeConverter để SpEL thực hiện các chuyển đổi kiểu trong những ngữ cảnh cần kiểu đích, ví dụ:

- Gán giá trị vào property có kiểu cụ thể.
- Chuyển đổi đối số khi gọi method hoặc constructor.
- Chuyển kết quả sang kiểu được yêu cầu qua overload `getValue(..., DesiredType.class)`.

Ví dụ yêu cầu kết quả chuyển sang Double:

    Double value = parser.parseExpression("#count + #total")
            .getValue(context, Double.class);

Đây là chuyển đổi kết quả sau khi biểu thức đã được đánh giá. Nó không thay đổi kiểu của các toán hạng trong phép cộng và không thể khôi phục phần thập phân đã bị mất trong một phép chia số nguyên.

Ví dụ, chuyển kết quả của `1 / 2` sang Double vẫn chỉ cho giá trị tương đương 0.0, vì phép chia đã cho kết quả nguyên bằng 0 trước khi chuyển đổi. Muốn có 0.5, phải dùng toán hạng số thực ngay từ đầu.

Vì vậy, khi hai toán hạng khác kiểu, hãy xác định trước mục tiêu:

1. Nếu cả hai đều là Number, chọn kiểu số phù hợp và để phép toán thực hiện theo quy tắc số học của SpEL.
2. Nếu cần kiểu đích cụ thể cho property, method hoặc kết quả, sử dụng cơ chế chuyển đổi của EvaluationContext.
3. Nếu một toán hạng là chuỗi chứa chữ số, hãy chuyển đổi tường minh trước khi tính toán; không mặc định rằng toán tử số học sẽ tự phân tích chuỗi thành Number.

## 5. Khi một toán hạng là String

String không phải Number. Với toán tử cộng, nếu có toán hạng dạng chuỗi, SpEL có thể thực hiện nối chuỗi thay vì cộng số:

    parser.parseExpression("'10' + 2").getValue(); // "102"

Kết quả là chuỗi `"102"`, không phải số 12. Đây là khác biệt quan trọng khi dữ liệu lấy từ form, file cấu hình hoặc API bên ngoài.

Nếu chuỗi biểu diễn một số, hãy chuyển đổi nó trước khi dùng trong phép tính. Với số nguyên:

    context.setVariable("rawCount", "10");

    Object count = parser.parseExpression(
            "T(java.lang.Integer).parseInt(#rawCount)"
    ).getValue(context);

Với số thập phân cần độ chính xác:

    context.setVariable("rawAmount", "123.4500");

    Object amount = parser.parseExpression(
            "new java.math.BigDecimal(#rawAmount)"
    ).getValue(context);

Sau đó dùng các giá trị đã chuyển đổi làm toán hạng. Khi dữ liệu đến từ ứng dụng, cách rõ ràng hơn là parse và validate trong Java rồi truyền Number đã chuẩn hóa vào context.

Nếu hai toán hạng là các object không thuộc nhóm Number hoặc String, phép toán có thể cần một OperatorOverloader tùy chỉnh. OperatorOverloader định nghĩa cách thực hiện toán tử trên kiểu riêng; nó không phải là cơ chế tự động chuyển chuỗi thành số.

## 6. Kết hợp BigInteger và BigDecimal

BigInteger phù hợp với số nguyên vượt miền Long hoặc cần giữ chính xác mọi chữ số. BigDecimal phù hợp với phép tính thập phân cần độ chính xác, ví dụ tiền tệ hoặc tỷ lệ.

Nên tạo BigDecimal từ chuỗi thập phân gốc:

    BigDecimal price = new BigDecimal("19.99");
    BigDecimal tax = new BigDecimal("1.50");

    context.setVariable("price", price);
    context.setVariable("tax", tax);

    BigDecimal total = parser.parseExpression("#price + #tax")
            .getValue(context, BigDecimal.class);

Không tạo BigDecimal từ một Double đã được tính trước nếu cần độ chính xác tuyệt đối. Khi đó sai số floating point có thể đã xuất hiện trước khi chuyển sang BigDecimal.

Với hai toán hạng khác kiểu, đặc biệt khi trộn BigInteger, BigDecimal và floating point, hãy chuẩn hóa cả hai về kiểu mong muốn trước khi tính toán. Điều này làm rõ chính sách làm tròn, độ chính xác và kiểu kết quả của ứng dụng.

## 7. Kiểm tra kiểu kết quả khi debug

Khi biểu thức cho kết quả bất ngờ, hãy in cả giá trị và kiểu runtime:

    Object result = parser.parseExpression(
            "#left + #right"
    ).getValue(context);

    System.out.println(result);
    System.out.println(result.getClass().getName());

Có thể kiểm tra từng toán hạng ngay trong Java trước khi đưa vào context:

    System.out.println(context.lookupVariable("left").getClass());
    System.out.println(context.lookupVariable("right").getClass());

Điều này giúp phát hiện trường hợp một giá trị đáng lẽ là Long nhưng lại được tạo thành Integer, hoặc một số thập phân được đọc thành String. Với biểu thức phức tạp, hãy tách phép tính thành các biến trung gian để quan sát kiểu sau mỗi bước.

Khi dùng `getValue(context, TargetType.class)`, nhớ rằng TypeConverter đang chuyển kết quả cuối sang kiểu yêu cầu. Nếu cần xác định kiểu thực sự do toán tử tạo ra, gọi `getValue(context)` rồi kiểm tra `getClass()`.

## 8. Tùy chỉnh chuyển đổi kiểu

Nếu ứng dụng cần chuyển đổi giữa các kiểu dữ liệu riêng, có thể cấu hình TypeConverter trên StandardEvaluationContext. StandardTypeConverter có thể sử dụng Spring ConversionService để áp dụng các Converter đã đăng ký.

Ví dụ, tạo một converter ở tầng ứng dụng rồi cung cấp cho context:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

TypeConverter hữu ích khi SpEL cần chuyển đổi một giá trị sang kiểu đích trong quá trình gán property hoặc phân giải lời gọi. Tuy nhiên, hãy chuẩn hóa toán hạng trước phép toán nếu muốn kiểm soát chính xác kiểu số học. Đừng dựa vào một converter tùy chỉnh để thay thế mọi quy tắc số học của toán tử.

Nếu biểu thức đến từ người dùng, chỉ cung cấp những converter cần thiết và giới hạn các kiểu có thể được chuyển đổi. Một converter quá rộng có thể biến dữ liệu đầu vào không hợp lệ thành giá trị có ý nghĩa ngoài dự kiến.

## 9. Lỗi thường gặp

- **Cộng chuỗi thay vì cộng số:** kiểm tra kiểu runtime; parse String thành Number trước khi tính.
- **Mất phần thập phân khi chia:** dùng Double hoặc BigDecimal cho toán hạng trước phép chia.
- **Tràn số nguyên:** dùng Long hoặc BigInteger nếu giá trị vượt miền Integer/Long.
- **Sai số thập phân:** dùng BigDecimal được tạo từ chuỗi hoặc nguồn dữ liệu chính xác.
- **Chuyển kiểu quá muộn:** chuyển kết quả sau phép toán không khôi phục được độ chính xác đã mất.
- **Nhầm TypeConverter với numeric promotion:** TypeConverter phục vụ chuyển đổi sang kiểu đích; toán tử số học có quy tắc xử lý Number riêng.
- **Không kiểm tra kiểu kết quả:** dùng `getValue(context)` và `getClass()` khi cần xác định kiểu thực tế của kết quả.

## 10. Ghi nhớ

Khi hai toán hạng khác kiểu, trước hết xác định chúng có phải Number hay không. Với hai toán hạng số, SpEL áp dụng cách xử lý số học và kiểu kết quả dựa trên các kiểu runtime. Với String, đặc biệt ở toán tử cộng, có thể xảy ra nối chuỗi thay vì cộng số. TypeConverter xử lý các chuyển đổi cần kiểu đích như gán property, gọi method hoặc lấy kết quả theo kiểu yêu cầu; nó không thay thế việc chọn kiểu toán hạng phù hợp trước phép tính. Đối với số nguyên rất lớn, dùng BigInteger; đối với thập phân cần chính xác, dùng BigDecimal và chuẩn hóa cả hai toán hạng trước khi thực hiện phép toán.
