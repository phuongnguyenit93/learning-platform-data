# TypeLocator, TypeConverter và OperatorOverloader trong Spring Expression Language

EvaluationContext là môi trường mà Spring Expression Language (SpEL) sử dụng khi đánh giá một biểu thức. Ngoài root object và variables, context còn cung cấp các cơ chế mở rộng để SpEL tìm kiểu Java, chuyển đổi giá trị và xử lý những phép toán cần quy tắc riêng.

Ba thành phần quan trọng là:

- **TypeLocator:** tìm một kiểu Java khi expression sử dụng type reference như T(java.time.LocalDate).
- **TypeConverter:** kiểm tra và chuyển đổi giá trị sang kiểu mà một thao tác yêu cầu, chẳng hạn khi gán property hoặc yêu cầu kiểu kết quả.
- **OperatorOverloader:** cho phép ứng dụng định nghĩa cách thực hiện một số toán tử SpEL trên các kiểu dữ liệu tùy chỉnh.

Chúng giải quyết ba vấn đề khác nhau. TypeLocator tìm lớp; TypeConverter chuyển giá trị; OperatorOverloader thay đổi cách một phép toán được thực hiện. Cả ba đều được cấu hình thông qua EvaluationContext.

## 1. Vai trò của ba thành phần trong EvaluationContext

Khi SpEL đánh giá expression, nó có thể cần nhiều dịch vụ từ context:

| Thành phần | Câu hỏi mà thành phần giải quyết | Ví dụ |
|---|---|---|
| TypeLocator | Tên kiểu này tương ứng với Class nào? | T(java.math.BigDecimal) |
| TypeConverter | Giá trị này có thể chuyển sang kiểu đích không? | String "25" sang Integer |
| OperatorOverloader | Phép toán này có cách xử lý riêng cho hai toán hạng này không? | Money + Money |

Có thể hình dung luồng xử lý:

~~~text
Expression
   |
   v
EvaluationContext
   |
   +--> TypeLocator
   |       Tìm Class cho T(...)
   |
   +--> TypeConverter
   |       Chuyển đổi giá trị khi thao tác yêu cầu
   |
   +--> OperatorOverloader
           Xử lý phép toán tùy chỉnh nếu được hỗ trợ
~~~

Các thành phần này không thay thế lẫn nhau. Ví dụ, TypeLocator có thể tìm được lớp BigDecimal nhưng không tự chuyển một chuỗi thành BigDecimal. TypeConverter có thể chuyển đổi một giá trị nhưng không quyết định tên lớp nào được phép tham chiếu. OperatorOverloader có thể định nghĩa phép cộng cho Money nhưng không làm cho một type reference mới tự động được tìm thấy.

## 2. TypeLocator: tìm kiểu Java trong expression

SpEL hỗ trợ type reference bằng toán tử T(...):

~~~spel
T(java.lang.Math)
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

Khi gặp cú pháp này, SpEL cần tìm lớp tương ứng với tên được viết trong ngoặc. EvaluationContext cung cấp interface TypeLocator cho nhiệm vụ đó.

TypeLocator định nghĩa phương thức chính:

~~~java
Class<?> findType(String typeName) throws EvaluationException;
~~~

Đầu vào là tên kiểu; kết quả là đối tượng Class tương ứng. Nếu không tìm được kiểu hoặc chính sách của locator từ chối tên đó, thao tác có thể phát sinh EvaluationException.

### TypeLocator được sử dụng ở đâu?

Ví dụ:

~~~spel
T(java.lang.Math).max(10, 20)
~~~

SpEL cần:

1. Nhận diện type reference T(java.lang.Math).
2. Yêu cầu TypeLocator tìm lớp java.lang.Math.
3. Nhận Class tương ứng.
4. Giải quyết thành viên static max.
5. Gọi method với các đối số và nhận kết quả.

TypeLocator chỉ giải quyết tên kiểu. Việc tìm và gọi method static là các bước riêng, chịu ảnh hưởng bởi cơ chế truy cập và method resolution.

## 3. StandardTypeLocator và hành vi mặc định

StandardEvaluationContext thường sử dụng StandardTypeLocator làm TypeLocator mặc định. StandardTypeLocator tìm lớp thông qua classloader và hỗ trợ các package import.

Package java.lang được import sẵn, nên có thể viết tên ngắn:

~~~spel
T(String)
T(Integer)
T(Math)
~~~

Với các kiểu ngoài java.lang, có thể dùng tên đầy đủ:

~~~spel
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

Hoặc đăng ký package import để rút gọn tên:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

typeLocator.registerImport("java.math");
typeLocator.registerImport("java.time");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký, expression có thể viết:

~~~spel
T(BigDecimal)
T(LocalDate)
~~~

Import giúp rút gọn tên kiểu. Nó không phải allow-list và không có nghĩa các package khác bị cấm. Nếu ứng dụng cần giới hạn type reference, cần áp dụng chính sách riêng trong TypeLocator.

### Cấu hình classloader

Trong ứng dụng nhiều module, plugin hoặc môi trường có classloader riêng, classloader ảnh hưởng đến các lớp mà StandardTypeLocator có thể tìm thấy.

Có thể chỉ định classloader:

~~~java
ClassLoader classLoader =
    Thread.currentThread().getContextClassLoader();

StandardTypeLocator typeLocator =
    new StandardTypeLocator(classLoader);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Tên kiểu vẫn phải hợp lệ và lớp phải có thể được tải qua classloader đã chọn.

## 4. Tạo TypeLocator có allow-list

Nếu expression chỉ được tham chiếu một số kiểu cụ thể, có thể bọc một TypeLocator khác bằng chính sách allow-list.

Ví dụ, chỉ cho phép Math và BigDecimal:

~~~java
public class AllowListTypeLocator implements TypeLocator {

    private final TypeLocator delegate =
        new StandardTypeLocator();

    private final Set<String> allowedTypes = Set.of(
        "java.lang.Math",
        "java.math.BigDecimal"
    );

    @Override
    public Class<?> findType(String typeName)
            throws EvaluationException {

        if (!allowedTypes.contains(typeName)) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return delegate.findType(typeName);
    }
}
~~~

Đăng ký locator:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Integer result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context, Integer.class);
~~~

Kết quả là 20.

Một type reference ngoài danh sách, chẳng hạn T(java.lang.System), bị từ chối trước khi delegate tìm lớp.

Nếu muốn cho phép cả tên đầy đủ và tên ngắn, cần chuẩn hóa tên và định nghĩa rõ alias được chấp nhận. Không nên cho phép mọi tên mà delegate có thể tìm thấy rồi mới kiểm tra chính sách.

Allow-list TypeLocator chỉ giới hạn đường truy cập qua T(...). Nó không phải sandbox hoàn chỉnh: root object, variables, method resolver, property accessor hoặc bean resolver vẫn có thể cung cấp những đường truy cập khác.

## 5. TypeConverter: chuyển đổi giá trị theo kiểu đích

Một expression có thể tạo ra hoặc nhận một giá trị có kiểu khác với kiểu mà ứng dụng cần. TypeConverter giúp SpEL kiểm tra và thực hiện chuyển đổi đó.

Interface TypeConverter cung cấp hai thao tác quan trọng:

~~~java
boolean canConvert(
    TypeDescriptor sourceType,
    TypeDescriptor targetType
);

Object convertValue(
    Object value,
    TypeDescriptor sourceType,
    TypeDescriptor targetType
) throws EvaluationException;
~~~

- canConvert kiểm tra liệu có thể chuyển từ kiểu nguồn sang kiểu đích không.
- convertValue thực hiện chuyển đổi và trả về giá trị mới.

SpEL có thể cần chuyển đổi trong nhiều tình huống, ví dụ:

- Gán giá trị cho property có kiểu khác với giá trị đầu vào.
- Gọi method hoặc constructor khi đối số cần kiểu tương thích.
- Lấy kết quả qua overload getValue có chỉ định kiểu đích.
- Thực hiện các thao tác binding cần chuyển đổi dữ liệu.

### Ví dụ chuyển String thành Integer khi gán property

~~~java
public class RetrySettings {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Gán bằng SpEL:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression property =
    parser.parseExpression("retryCount");

property.setValue(context, "5");

System.out.println(settings.getRetryCount());
~~~

Với TypeConverter mặc định hỗ trợ String sang Integer, kết quả là:

~~~text
5
~~~

PropertyAccessor xác định property và setter đích. TypeConverter chuyển chuỗi "5" thành Integer trước khi giá trị được ghi.

## 6. TypeDescriptor mô tả kiểu nguồn và kiểu đích

TypeConverter làm việc cùng TypeDescriptor. TypeDescriptor cung cấp thông tin kiểu chi tiết hơn một đối tượng Class đơn thuần.

Nó có thể mô tả:

- Kiểu Java của giá trị.
- Kiểu phần tử của collection.
- Kiểu key và value của map.
- Kiểu thành phần của array.
- Annotation và metadata liên quan đến property.

Ví dụ:

~~~java
private List<Integer> retryCodes;
private Map<String, BigDecimal> thresholds;
~~~

Cả hai property đều có kiểu lớp ngoài là collection, nhưng kiểu phần tử hoặc key/value khác nhau. TypeDescriptor có thể cung cấp metadata generic để ConversionService lựa chọn chuyển đổi phù hợp.

Điều này đặc biệt hữu ích khi binding dữ liệu từ chuỗi hoặc cấu trúc dữ liệu tổng quát sang property có kiểu cụ thể.

## 7. StandardTypeConverter và ConversionService

StandardEvaluationContext thường sử dụng StandardTypeConverter làm TypeConverter mặc định. StandardTypeConverter kết nối SpEL với cơ chế chuyển đổi của Spring ConversionService.

Có thể tạo converter mặc định:

~~~java
StandardTypeConverter typeConverter =
    new StandardTypeConverter();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(typeConverter);
~~~

Hoặc cung cấp ConversionService cụ thể:

~~~java
ConversionService conversionService =
    new DefaultConversionService();

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

context.setTypeConverter(typeConverter);
~~~

Cách này cho phép SpEL dùng cùng hệ thống converter mà ứng dụng sử dụng ở các phần khác của Spring.

Không phải mọi giá trị đều chuyển đổi được. Khả năng chuyển đổi phụ thuộc vào converter đã đăng ký, kiểu nguồn, kiểu đích và định dạng dữ liệu.

Ví dụ, chuỗi "5" có thể chuyển thành Integer, nhưng chuỗi "five" không phải biểu diễn số nguyên hợp lệ với converter thông thường.

## 8. Đăng ký converter tùy chỉnh

Khi ứng dụng có kiểu domain riêng, có thể thêm Converter vào ConversionService.

Ví dụ, định nghĩa kiểu CurrencyCode:

~~~java
public class CurrencyCode {
    private final String value;

    public CurrencyCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Tạo converter:

~~~java
Converter<String, CurrencyCode> currencyCodeConverter =
    CurrencyCode::new;
~~~

Đăng ký và cấu hình cho SpEL:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(currencyCodeConverter);

StandardEvaluationContext context =
    new StandardEvaluationContext(paymentSettings);

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Nếu PaymentSettings có setter nhận CurrencyCode, expression có thể gán một chuỗi và sử dụng converter đã đăng ký:

~~~spel
currency = 'VND'
~~~

Khi ghi property, TypeConverter yêu cầu ConversionService chuyển String thành CurrencyCode rồi chuyển giá trị đã chuyển đổi cho cơ chế ghi.

Converter tùy chỉnh nên xác định rõ cách chuẩn hóa dữ liệu và cách xử lý đầu vào không hợp lệ. Nếu định dạng sai, nên báo lỗi rõ ràng thay vì âm thầm tạo giá trị không đúng nghiệp vụ.

## 9. OperatorOverloader: tùy chỉnh phép toán trong SpEL

SpEL hỗ trợ các toán tử như cộng, trừ, nhân, chia, modulo và lũy thừa. Với kiểu dữ liệu Java thông thường, SpEL áp dụng ngữ nghĩa toán tử có sẵn.

Khi ứng dụng có kiểu domain riêng, chẳng hạn Money hoặc Distance, có thể muốn định nghĩa cách thực hiện phép toán trực tiếp trên các giá trị đó. OperatorOverloader cho phép ứng dụng cung cấp hành vi này.

Interface OperatorOverloader có hai phương thức:

~~~java
boolean overridesOperation(
    Operation operation,
    Object leftOperand,
    Object rightOperand
);

Object overloadOperation(
    Operation operation,
    Object leftOperand,
    Object rightOperand
) throws EvaluationException;
~~~

- overridesOperation cho biết implementation có xử lý phép toán với cặp toán hạng hiện tại hay không.
- overloadOperation thực hiện phép toán và trả về kết quả.

SpEL dùng Operation để nhận diện loại phép toán, ví dụ ADD, SUBTRACT, MULTIPLY, DIVIDE, MODULUS hoặc POWER.

OperatorOverloader không thêm cú pháp toán tử mới vào ngôn ngữ và cũng không thay đổi precedence của toán tử. Nó cung cấp cách thực hiện riêng cho những phép toán SpEL đã nhận diện.

## 10. Ví dụ OperatorOverloader cho kiểu Money

Giả sử ứng dụng có kiểu Money chứa số tiền:

~~~java
public class Money {
    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Money add(Money other) {
        return new Money(amount.add(other.amount));
    }
}
~~~

Tạo OperatorOverloader để hỗ trợ phép cộng hai Money:

~~~java
public class MoneyOperatorOverloader
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
    public Object overloadOperation(
            Operation operation,
            Object leftOperand,
            Object rightOperand)
            throws EvaluationException {

        if (overridesOperation(
                operation,
                leftOperand,
                rightOperand)) {

            Money left = (Money) leftOperand;
            Money right = (Money) rightOperand;

            return left.add(right);
        }

        throw new EvaluationException(
            "Unsupported Money operation: " + operation
        );
    }
}
~~~

Đăng ký implementation trong context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);

context.setVariable(
    "left",
    new Money(new BigDecimal("100"))
);

context.setVariable(
    "right",
    new Money(new BigDecimal("50"))
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#left + #right");

Money result =
    expression.getValue(context, Money.class);
~~~

Kết quả là một Money mới có amount bằng 150.

Trong ví dụ:

1. SpEL đọc hai biến left và right.
2. Cả hai toán hạng đều là Money.
3. OperatorOverloader báo rằng nó hỗ trợ Operation.ADD cho cặp kiểu này.
4. overloadOperation gọi logic cộng của Money.
5. Kết quả Money được trả về cho expression.

## 11. Khi nào OperatorOverloader được sử dụng?

OperatorOverloader phù hợp khi toán tử cần ý nghĩa riêng cho một kiểu domain mà ngữ nghĩa mặc định của SpEL không đáp ứng.

Một số trường hợp có thể cân nhắc:

- Cộng hai giá trị Money theo quy tắc tiền tệ của ứng dụng.
- Cộng hoặc trừ hai giá trị Distance.
- Kết hợp hai kiểu giá trị domain có quy tắc toán học riêng.
- Định nghĩa phép tính cho kiểu dữ liệu đặc thù trong một DSL nội bộ.

Không nên dùng OperatorOverloader chỉ để thay đổi cách cộng các số nguyên hoặc nối chuỗi thông thường nếu ngữ nghĩa mặc định đã đúng.

Một implementation nên:

- Chỉ nhận những Operation và kiểu toán hạng mà nó thực sự hỗ trợ.
- Trả về kiểu kết quả có ý nghĩa và ổn định.
- Ném EvaluationException nếu bị gọi với phép toán ngoài phạm vi hỗ trợ.
- Tránh thay đổi trạng thái của toán hạng nếu phép toán được kỳ vọng là phép tính thuần.
- Xác định rõ quy tắc null và chuyển đổi kiểu nếu domain cần hỗ trợ các trường hợp đó.

## 12. Đăng ký ba thành phần trên StandardEvaluationContext

StandardEvaluationContext cho phép cấu hình riêng TypeLocator, TypeConverter và OperatorOverloader:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeLocator(typeLocator);
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(operatorOverloader);
~~~

Mỗi setter thay đổi một dịch vụ trong môi trường đánh giá.

Một cấu hình minh họa:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

DefaultConversionService conversionService =
    new DefaultConversionService();

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeLocator(typeLocator);
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);
~~~

Trong ứng dụng thực tế, chỉ cần thay thế thành phần nào có yêu cầu tùy chỉnh. Nếu hành vi mặc định đã đáp ứng nhu cầu, có thể giữ nguyên thành phần mặc định để tránh cấu hình dư thừa.

Cũng cần lưu ý context còn chứa các dịch vụ khác như PropertyAccessor, MethodResolver, ConstructorResolver và BeanResolver. Ba thành phần trong bài chỉ là một phần của toàn bộ EvaluationContext.

## 13. Ba thành phần phối hợp trong một expression

Một biểu thức có thể dùng nhiều cơ chế trong cùng lần đánh giá.

Ví dụ, ứng dụng sử dụng type reference để lấy hằng số, biến Money để thực hiện phép cộng tùy chỉnh và yêu cầu kiểu kết quả cụ thể:

~~~spel
#baseAmount + #extraAmount
~~~

Quá trình:

1. TypeLocator chỉ tham gia nếu expression có T(...), ví dụ khi cần tham chiếu một kiểu.
2. TypeConverter tham gia nếu một thao tác cần chuyển giá trị sang kiểu tương thích.
3. OperatorOverloader được hỏi khi SpEL đánh giá phép cộng và cặp toán hạng thuộc phạm vi mà implementation tùy chỉnh hỗ trợ.
4. Expression trả về kết quả cuối cùng.

Không phải expression nào cũng cần cả ba. Ví dụ, expression chỉ đọc property không nhất thiết cần type reference hoặc operator overloading.

## 14. Phân biệt ba cơ chế với các thành phần EvaluationContext khác

| Thành phần | Trách nhiệm | Không chịu trách nhiệm về |
|---|---|---|
| TypeLocator | Tìm Class từ tên kiểu | Chuyển đổi giá trị hoặc tìm bean |
| TypeConverter | Chuyển giá trị giữa các kiểu | Quyết định property có writable hay không |
| OperatorOverloader | Thực hiện phép toán tùy chỉnh | Tìm class hoặc gọi method tùy ý |
| PropertyAccessor | Đọc/ghi property | Tìm kiểu trong T(...) |
| MethodResolver | Tìm method phù hợp | Định nghĩa phép cộng domain |
| ConstructorResolver | Tìm constructor | Chuyển đổi mọi dữ liệu nghiệp vụ |
| BeanResolver | Tìm bean theo tên | Tìm Class từ type reference |

Sự phân chia này giúp xác định đúng nơi cần cấu hình khi một expression gặp lỗi.

Ví dụ:

- T(java.time.LocalDate) không tìm được lớp: kiểm tra TypeLocator và classloader.
- Gán "abc" vào property Integer thất bại: kiểm tra TypeConverter và dữ liệu đầu vào.
- #left + #right không hỗ trợ kiểu Money: kiểm tra OperatorOverloader.
- customer.name không đọc được: kiểm tra PropertyAccessor và object hiện tại.
- customer.calculate() không tìm được method: kiểm tra MethodResolver.

## 15. Giới hạn và lưu ý khi cấu hình

Các thành phần mở rộng làm SpEL linh hoạt hơn nhưng cũng ảnh hưởng đến hành vi của expression.

### TypeLocator

Nếu dùng allow-list, hãy kiểm tra tên kiểu trước khi delegate tìm Class. Tuy nhiên, giới hạn T(...) không kiểm soát mọi đường truy cập đến object có sẵn trong root, variables hoặc beans.

### TypeConverter

Converter có thể được dùng ở nhiều điểm trong evaluation. Một converter quá rộng hoặc chuyển đổi dữ liệu không chặt chẽ có thể khiến dữ liệu đầu vào được chấp nhận ngoài dự kiến. Hãy định nghĩa rõ định dạng, miền giá trị và hành vi khi chuyển đổi thất bại.

### OperatorOverloader

OperatorOverloader có thể làm thay đổi ý nghĩa của phép toán đối với kiểu domain. Nên giữ implementation nhỏ, xác định rõ kiểu toán hạng và kết quả, đồng thời tránh tác dụng phụ khó dự đoán.

### Vòng đời EvaluationContext

Nếu context được dùng lại giữa nhiều lần đánh giá, cấu hình và trạng thái của nó cũng được dùng lại. Không nên thay đổi dịch vụ hoặc biến trong context dùng chung giữa các request đồng thời nếu chưa có cơ chế đồng bộ và phạm vi dữ liệu phù hợp.

## 16. Ví dụ tổng hợp: context tùy chỉnh cho quy tắc domain

Giả sử ứng dụng có Money và muốn:

- Chỉ cho phép tham chiếu Math.
- Chuyển String sang một kiểu domain thông qua ConversionService.
- Hỗ trợ phép cộng hai Money.

Có thể cấu hình theo từng trách nhiệm:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    CurrencyCode::new
);

StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());
context.setTypeConverter(typeConverter);
context.setOperatorOverloader(
    new MoneyOperatorOverloader()
);

context.setVariable(
    "left",
    new Money(new BigDecimal("100"))
);
context.setVariable(
    "right",
    new Money(new BigDecimal("50"))
);

ExpressionParser parser = new SpelExpressionParser();

Money total = parser.parseExpression(
    "#left + #right"
).getValue(context, Money.class);
~~~

Trong cấu hình này, TypeLocator, TypeConverter và OperatorOverloader không làm cùng một việc. Mỗi thành phần đáp ứng một yêu cầu riêng trong môi trường đánh giá. Việc cấu hình một thành phần không tự động thay thế hoặc mở rộng quyền hạn của hai thành phần còn lại.

## 17. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: TypeLocator chuyển đổi một giá trị thành kiểu Java.**  
TypeLocator tìm Class theo tên. Chuyển đổi object giữa các kiểu là nhiệm vụ của TypeConverter.

**Nhầm lẫn 2: Đăng ký package import là đã giới hạn type reference.**  
Import chỉ rút gọn tên kiểu. Muốn allow-list cần kiểm tra tên trong TypeLocator tùy chỉnh.

**Nhầm lẫn 3: TypeConverter quyết định property có thể ghi hay không.**  
PropertyAccessor và object đích quyết định khả năng ghi. TypeConverter chỉ chuyển đổi giá trị khi cần.

**Nhầm lẫn 4: OperatorOverloader thay đổi cú pháp Java.**  
Nó chỉ cung cấp hành vi cho toán tử SpEL trong EvaluationContext. Nó không làm cho toán tử + của Java tự động hỗ trợ kiểu Money.

**Nhầm lẫn 5: OperatorOverloader cần thiết cho mọi phép cộng.**  
SpEL đã có ngữ nghĩa mặc định cho các kiểu được hỗ trợ. Chỉ dùng overloader khi kiểu domain cần hành vi riêng.

**Nhầm lẫn 6: Tùy chỉnh một trong ba thành phần là đủ để tạo sandbox.**  
TypeLocator, TypeConverter và OperatorOverloader chỉ kiểm soát các khía cạnh tương ứng. Root object, variables, property access, method resolution và bean resolution vẫn cần được giới hạn theo mục tiêu ứng dụng.

## 18. Ghi nhớ

- EvaluationContext cung cấp TypeLocator, TypeConverter và OperatorOverloader cho các nhu cầu khác nhau khi đánh giá SpEL.
- TypeLocator tìm Class từ tên kiểu trong T(...); StandardTypeLocator hỗ trợ classloader và package import.
- TypeConverter kiểm tra và chuyển đổi giá trị theo kiểu nguồn/đích; StandardTypeConverter kết nối với Spring ConversionService.
- TypeDescriptor cung cấp metadata kiểu, bao gồm thông tin generic của collection và map.
- Có thể đăng ký converter domain riêng vào ConversionService rồi dùng StandardTypeConverter trong context.
- OperatorOverloader định nghĩa cách thực hiện các phép toán SpEL trên kiểu dữ liệu tùy chỉnh.
- overridesOperation xác định phép toán và cặp toán hạng mà implementation hỗ trợ; overloadOperation thực hiện phép toán và trả kết quả.
- StandardEvaluationContext cho phép cấu hình từng thành phần bằng setTypeLocator, setTypeConverter và setOperatorOverloader.
- Ba cơ chế không thay thế PropertyAccessor, MethodResolver, ConstructorResolver hoặc BeanResolver.
- Cấu hình tùy chỉnh cần có phạm vi rõ ràng, kết quả dễ dự đoán và được quản lý theo vòng đời EvaluationContext.

Khi mở rộng SpEL, hãy xác định expression cần tìm kiểu, chuyển đổi dữ liệu hay thay đổi ngữ nghĩa toán tử. Sau đó cấu hình đúng thành phần trong EvaluationContext, giữ các trách nhiệm tách biệt và chỉ mở những khả năng thực sự cần cho biểu thức.
