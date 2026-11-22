# TypeLocator, TypeConverter và OperatorOverloader

Trong Spring Expression Language (SpEL), biểu thức được phân tích thành cây biểu thức rồi đánh giá trong một EvaluationContext. Context cung cấp các dịch vụ mà SpEL cần khi chạy. Ba extension point trong bài này giải quyết ba câu hỏi khác nhau:

- **TypeLocator:** tên kiểu trong biểu thức tương ứng với lớp Java nào?
- **TypeConverter:** giá trị hiện có được chuyển sang kiểu đích như thế nào?
- **OperatorOverloader:** phép toán có sẵn như cộng hoặc nhân được thực hiện ra sao với các kiểu dữ liệu miền nghiệp vụ?

Chúng thường được cấu hình trên StandardEvaluationContext. Khi tách đúng trách nhiệm của từng thành phần, ta có thể mở rộng SpEL cho mô hình miền riêng mà vẫn giữ cách đánh giá biểu thức rõ ràng và có kiểm soát.

## 1. Vị trí của ba thành phần trong quá trình đánh giá

Một luồng SpEL cơ bản gồm parser, expression và evaluation context:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("price * quantity");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Object result = expression.getValue(context);
~~~

Parser tạo Expression từ chuỗi. Khi gọi getValue, Expression đọc root object và sử dụng các dịch vụ trong context khi cần. Ba thành phần có vai trò riêng:

| Thành phần | Đầu vào chính | Kết quả |
|---|---|---|
| TypeLocator | Tên lớp, ví dụ java.lang.Math | Đối tượng Class<?> |
| TypeConverter | Giá trị, kiểu nguồn và kiểu đích | Giá trị đã chuyển kiểu |
| OperatorOverloader | Loại phép toán và hai toán hạng | Kết quả của phép toán tùy chỉnh |

Ví dụ, biểu thức T(Math).max(10, 20) cần TypeLocator để tìm lớp Math. Việc truyền đối số vào một phương thức có tham số kiểu khác có thể cần TypeConverter. Biểu thức left + right với hai đối tượng Money có thể cần OperatorOverloader nếu muốn định nghĩa phép cộng theo quy tắc nghiệp vụ.

Ba thành phần không thay thế lẫn nhau: TypeLocator không chuyển dữ liệu; TypeConverter không định nghĩa ý nghĩa của toán tử; OperatorOverloader không tìm lớp theo tên.

## 2. TypeLocator — tìm lớp từ tên kiểu

### 2.1. Nhiệm vụ và API

TypeLocator thuộc package org.springframework.expression. Nó nhận tên kiểu được tham chiếu trong biểu thức và trả về Class tương ứng:

~~~java
public interface TypeLocator {
    Class<?> findType(String typeName) throws EvaluationException;
}
~~~

TypeLocator thường được SpEL sử dụng khi gặp toán tử tham chiếu kiểu T(...). Sau khi lớp được tìm thấy, biểu thức có thể tham chiếu thành viên static hoặc sử dụng kiểu đó trong các cấu trúc SpEL được hỗ trợ.

Ví dụ:

~~~java
T(java.lang.Math).max(10, 20)
~~~

Nếu package java.lang đã được import mặc định, có thể viết ngắn:

~~~java
T(Math).max(10, 20)
~~~

T(...) là cú pháp tham chiếu một kiểu Java. Nó không phải cú pháp tạo bean Spring và cũng không tự tạo một đối tượng mới.

### 2.2. StandardTypeLocator

Spring cung cấp StandardTypeLocator để xử lý việc tìm lớp thông thường. Nó có thể tìm lớp bằng tên đầy đủ và hỗ trợ các package prefix được đăng ký làm import. Package java.lang được đăng ký mặc định.

~~~java
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.domain");

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);
context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký import, biểu thức có thể dùng tên lớp ngắn nếu tên đó không bị nhập nhằng:

~~~java
T(Money).of("125.00", "USD")
~~~

Trong đó Money nằm trong package com.example.domain. Nếu không muốn phụ thuộc vào import prefix, có thể dùng tên đầy đủ:

~~~java
T(com.example.domain.Money).of("125.00", "USD")
~~~

StandardTypeLocator cũng có constructor nhận ClassLoader. Điều này hữu ích trong môi trường có class loader riêng, chẳng hạn ứng dụng plugin hoặc môi trường triển khai có nhiều vùng tải lớp.

### 2.3. Khi nào cần TypeLocator tùy chỉnh?

Dùng StandardTypeLocator khi ứng dụng tin cậy biểu thức và chỉ cần cơ chế phân giải lớp thông thường. Có thể triển khai TypeLocator riêng khi ứng dụng cần chính sách phân giải khác, ví dụ:

- Chỉ cho phép một tập lớp đã khai báo.
- Ánh xạ alias nghiệp vụ sang lớp Java.
- Phân giải lớp theo một ClassLoader cụ thể.
- Trả lỗi có thông tin rõ ràng khi biểu thức tham chiếu kiểu không được phép.

Cần phân biệt import prefix với allowlist bảo mật. Việc chỉ đăng ký một vài package trong StandardTypeLocator không đồng nghĩa các lớp khác đã bị chặn: tên lớp đầy đủ vẫn có thể được phân giải. Nếu cần giới hạn lớp, hãy triển khai TypeLocator kiểm tra allowlist thực sự và kiểm soát cả những khả năng khác được cấp cho EvaluationContext.

## 3. TypeConverter — chuyển giá trị sang kiểu đích

### 3.1. Nhiệm vụ và API

TypeConverter chịu trách nhiệm chuyển một giá trị từ kiểu nguồn sang kiểu đích. Interface nằm trong org.springframework.expression:

~~~java
public interface TypeConverter {
    boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);

    Object convertValue(
            Object value,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) throws EvaluationException;
}
~~~

TypeDescriptor thuộc org.springframework.core.convert. Nó mô tả kiểu Java cùng metadata liên quan, chẳng hạn generic type và annotation. Vì vậy, nó cung cấp nhiều thông tin hơn một Class đơn thuần.

SpEL có thể cần chuyển kiểu trong những tình huống như:

- Gán một giá trị vào property có kiểu cụ thể.
- Truyền argument cho method hoặc constructor.
- Chuyển dữ liệu khi một thao tác đánh giá yêu cầu kiểu đích tương ứng.

Ví dụ, một property có kiểu int có thể nhận giá trị biểu diễn dưới dạng chuỗi nếu TypeConverter đang dùng hỗ trợ phép chuyển đổi đó.

### 3.2. StandardTypeConverter và ConversionService

Spring cung cấp StandardTypeConverter. Bộ chuyển đổi này ủy quyền công việc cho Spring ConversionService. Nhờ vậy, ứng dụng có thể tái sử dụng cơ chế Converter, ConverterFactory và GenericConverter thay vì tự viết toàn bộ logic chuyển kiểu cho SpEL.

Có thể cung cấp ConversionService riêng cho StandardTypeConverter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

Ví dụ trên giả định CustomerId là kiểu miền có constructor nhận một String:

~~~java
public record CustomerId(String value) {
}
~~~

Khi một vị trí trong biểu thức cần CustomerId và giá trị đầu vào là String, ConversionService có thể sử dụng converter vừa đăng ký.

### 3.3. Chuyển đổi tường minh và TypeDescriptor

Có thể truy cập TypeConverter từ EvaluationContext để thực hiện chuyển đổi trực tiếp:

~~~java
TypeConverter converter = context.getTypeConverter();

Object converted = converter.convertValue(
        "42",
        TypeDescriptor.valueOf(String.class),
        TypeDescriptor.valueOf(Integer.class)
);
~~~

Kết quả là một Integer nếu converter hỗ trợ chuyển String sang Integer. canConvert có thể được gọi trước để kiểm tra khả năng chuyển đổi mà không thực hiện chuyển đổi.

TypeDescriptor đặc biệt hữu ích với collection và generic type. Ví dụ, List<String> và List<Integer> có cùng raw class là List nhưng yêu cầu chuyển đổi phần tử khác nhau. Khi metadata generic được cung cấp đầy đủ, ConversionService có thể xử lý kiểu phần tử chính xác hơn.

### 3.4. Đăng ký converter ở đâu?

Nếu converter phản ánh quy tắc chuyển đổi dùng chung trong ứng dụng, hãy đăng ký nó trên ConversionService mà ứng dụng quản lý rồi truyền service đó vào StandardTypeConverter. Cách này giúp các thành phần khác của Spring có thể tái sử dụng cùng quy tắc.

Nếu chỉ một evaluation context cần hành vi riêng, có thể tạo ConversionService riêng cho context đó. Tránh thay đổi một ConversionService dùng chung chỉ để phục vụ một biểu thức đặc biệt nếu điều đó có thể ảnh hưởng các luồng xử lý khác.

TypeConverter chỉ giải quyết chuyển kiểu. Nó không quyết định ý nghĩa của phép cộng, phép so sánh hoặc các toán tử khác. Nếu muốn cộng hai đối tượng miền, hãy xem OperatorOverloader.

## 4. OperatorOverloader — định nghĩa toán tử cho kiểu miền

### 4.1. Nhiệm vụ và API

OperatorOverloader cho phép ứng dụng định nghĩa cách thực hiện một số toán tử SpEL có sẵn với các toán hạng tùy chỉnh:

~~~java
public interface OperatorOverloader {
    boolean overridesOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand);

    Object operate(
            Operation operation,
            Object leftOperand,
            Object rightOperand) throws EvaluationException;
}
~~~

SpEL hỏi overridesOperation để xác định implementation tùy chỉnh có xử lý phép toán với cặp toán hạng hiện tại hay không. Nếu phương thức trả về true, SpEL gọi operate để lấy kết quả.

Operation biểu diễn nhóm phép toán có sẵn như ADD, SUBTRACT, MULTIPLY, DIVIDE, MODULUS và POWER. OperatorOverloader mở rộng hành vi của những toán tử này; nó không bổ sung cú pháp hoặc ký hiệu toán tử mới vào ngôn ngữ SpEL.

### 4.2. Ví dụ: cộng hai đối tượng Money

Giả sử ứng dụng có kiểu Money gồm số tiền và đơn vị tiền tệ:

~~~java
public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }

    public static Money of(String amount, String currencyCode) {
        return new Money(
                new BigDecimal(amount),
                Currency.getInstance(currencyCode)
        );
    }
}
~~~

Quy tắc nghiệp vụ ở ví dụ này là chỉ cộng được hai khoản tiền có cùng currency. Ta có thể triển khai OperatorOverloader:

~~~java
public final class MoneyOperatorOverloader
        implements OperatorOverloader {

    @Override
    public boolean overridesOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand) {

        return operation == Operation.ADD
                && leftOperand instanceof Money
                && rightOperand instanceof Money;
    }

    @Override
    public Object operate(
            Operation operation,
            Object leftOperand,
            Object rightOperand) throws EvaluationException {

        if (operation == Operation.ADD
                && leftOperand instanceof Money left
                && rightOperand instanceof Money right) {

            if (!left.currency().equals(right.currency())) {
                throw new EvaluationException(
                        "Cannot add Money values with different currencies"
                );
            }

            return new Money(
                    left.amount().add(right.amount()),
                    left.currency()
            );
        }

        throw new EvaluationException(
                "Unsupported operation: " + operation
        );
    }
}
~~~

Đăng ký implementation trên context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setOperatorOverloader(
        new MoneyOperatorOverloader()
);
~~~

Khi TypeLocator đã biết package chứa Money, biểu thức có thể gọi factory method static rồi cộng hai kết quả:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(Money).of('10.00', 'USD') + " +
        "T(Money).of('5.00', 'USD')"
);

Money total = expression.getValue(context, Money.class);
~~~

Kết quả là Money có amount bằng 15.00 và currency USD. Nếu hai toán hạng dùng currency khác nhau, implementation ném EvaluationException để báo phép cộng không hợp lệ theo quy tắc nghiệp vụ.

Ví dụ này cũng cho thấy ba extension point có thể phối hợp: TypeLocator tìm lớp Money; OperatorOverloader xử lý phép cộng; TypeConverter có thể tham gia ở những vị trí cần chuyển kiểu argument hoặc giá trị gán.

### 4.3. Nguyên tắc khi viết OperatorOverloader

- Kiểm tra operation và kiểu runtime của cả hai toán hạng trong overridesOperation.
- Chỉ trả về true cho trường hợp implementation thực sự hỗ trợ.
- Kiểm tra điều kiện nghiệp vụ trong operate, ví dụ hai currency phải giống nhau.
- Ném EvaluationException với thông báo có ích khi toán hạng không hợp lệ.
- Giữ hành vi dễ dự đoán; tránh thao tác I/O hoặc thay đổi trạng thái bên ngoài trong một phép toán.
- Chỉ hỗ trợ những phép toán có ý nghĩa trong miền. Không nên định nghĩa phép nhân hoặc chia cho Money nếu nghiệp vụ chưa có quy tắc rõ ràng.

## 5. Cấu hình các thành phần trong cùng EvaluationContext

Một context có thể cấu hình đồng thời cả ba dịch vụ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

// 1. Phân giải tên lớp trong T(...)
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.domain");
context.setTypeLocator(typeLocator);

// 2. Chuyển đổi giá trị theo quy tắc của ứng dụng
DefaultConversionService conversionService =
        new DefaultConversionService();
conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);
context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

// 3. Định nghĩa phép toán cho kiểu miền
context.setOperatorOverloader(
        new MoneyOperatorOverloader()
);
~~~

Các setter được gọi trước khi đánh giá biểu thức. Có thể tái sử dụng context nếu root object và các dịch vụ cấu hình phù hợp với phạm vi sử dụng. Nếu context chứa trạng thái theo từng request hoặc dữ liệu người dùng, hãy quản lý vòng đời riêng để tránh chia sẻ trạng thái ngoài ý muốn.

Trong ứng dụng có nhiều nhóm biểu thức với chính sách khác nhau, nên tạo các context có cấu hình phù hợp cho từng nhóm. Điều này giúp giới hạn lớp được phép tham chiếu, converter được phép dùng và toán tử miền được hỗ trợ.

## 6. Phân biệt ba extension point

| Nhu cầu | Thành phần nên dùng | Ví dụ |
|---|---|---|
| Dùng T(Money) hoặc T(Math) | TypeLocator | Tìm lớp theo tên |
| Gán String vào property kiểu Integer | TypeConverter | Chuyển "42" thành 42 |
| Cộng hai giá trị Money | OperatorOverloader | Money + Money |
| Gọi static method sau khi tìm lớp | TypeLocator, sau đó là cơ chế method invocation | T(Math).max(1, 2) |
| Truyền argument cần chuyển kiểu vào method | TypeConverter | Chuyển argument theo kiểu tham số |

Một cách chọn nhanh:

1. Nếu vấn đề nằm ở tên lớp không được tìm thấy, kiểm tra TypeLocator.
2. Nếu lớp đã đúng nhưng giá trị không thể gán hoặc truyền vào tham số, kiểm tra TypeConverter và ConversionService.
3. Nếu hai toán hạng có kiểu hợp lệ nhưng phép toán không mang ý nghĩa mong muốn, kiểm tra OperatorOverloader.

Không dùng TypeConverter để mô phỏng phép cộng đối tượng. Cũng không dùng OperatorOverloader để chuyển một String thành kiểu đích.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Type cannot be found khi đánh giá T(...) | Tên lớp sai hoặc TypeLocator chưa có import phù hợp | Dùng tên đầy đủ hoặc đăng ký import prefix |
| Lớp được tìm thấy nhưng method static không gọi được | Method không tồn tại, không public hoặc argument không phù hợp | Kiểm tra chữ ký method và khả năng chuyển kiểu |
| Không chuyển được giá trị sang kiểu property | ConversionService thiếu converter tương ứng | Đăng ký Converter/GenericConverter phù hợp |
| Collection chuyển đổi sai kiểu phần tử | Metadata generic không đầy đủ hoặc converter phần tử chưa phù hợp | Kiểm tra TypeDescriptor và kiểu phần tử |
| Toán tử tùy chỉnh không chạy | overridesOperation trả về false hoặc toán hạng có kiểu runtime khác dự kiến | Kiểm tra Operation và kiểu của cả hai toán hạng |
| Phép cộng chạy nhưng kết quả sai quy tắc miền | Logic trong operate chưa kiểm tra đầy đủ điều kiện nghiệp vụ | Bổ sung validation và lỗi EvaluationException cụ thể |

Khi debug, nên tách biểu thức lớn thành các biểu thức nhỏ. Kiểm tra riêng việc phân giải kiểu, chuyển đổi argument và phép toán sẽ giúp xác định đúng extension point gây lỗi.

## 8. Giới hạn quyền của biểu thức và an toàn

StandardEvaluationContext cung cấp khả năng đánh giá SpEL đầy đủ và có thể truy cập nhiều tính năng như tham chiếu kiểu, method, property, constructor hoặc bean tùy cấu hình. Vì vậy, không nên đánh giá trực tiếp biểu thức do người dùng không tin cậy gửi lên bằng một context có quyền truy cập rộng.

Một số nguyên tắc cần áp dụng:

- Nếu cho phép T(...), dùng TypeLocator có allowlist thực sự khi cần giới hạn lớp. Chỉ giới hạn import prefix của StandardTypeLocator chưa đủ để chặn tên lớp đầy đủ.
- Chỉ đăng ký các method resolver, property accessor, bean resolver và constructor resolver mà biểu thức thực sự cần.
- Converter tùy chỉnh nên có hành vi rõ ràng, giới hạn kiểu nguồn/đích và tránh tác dụng phụ không cần thiết.
- OperatorOverloader nên chỉ hỗ trợ phép toán đã được định nghĩa trong nghiệp vụ và kiểm tra toán hạng trước khi thực thi.
- Không xem TypeLocator hoặc TypeConverter riêng lẻ là ranh giới bảo mật cho toàn bộ SpEL.

Nếu chỉ cần truy cập property và một tập method được giới hạn, hãy cân nhắc SimpleEvaluationContext. Đây là lựa chọn có chủ đích cho một tập con SpEL và không cung cấp các tính năng đầy đủ như tham chiếu kiểu, constructor và bean reference. Chọn context theo đúng mức năng lực biểu thức mà ứng dụng cần.

## 9. Tổng kết

TypeLocator, TypeConverter và OperatorOverloader là ba điểm mở rộng độc lập trong quá trình đánh giá SpEL:

- TypeLocator biến tên kiểu trong biểu thức thành lớp Java.
- TypeConverter chuyển giá trị theo kiểu nguồn, kiểu đích và metadata TypeDescriptor.
- OperatorOverloader định nghĩa cách thực hiện các toán tử có sẵn với những kiểu miền tùy chỉnh.

Khi triển khai, hãy bắt đầu từ StandardEvaluationContext, chỉ thay thế dịch vụ cần tùy biến và kiểm tra kỹ quyền mà biểu thức được phép sử dụng. Cấu hình rõ ràng giúp SpEL tích hợp với kiểu dữ liệu miền của ứng dụng mà vẫn giữ được hành vi dễ hiểu, có thể kiểm soát và dễ bảo trì.
