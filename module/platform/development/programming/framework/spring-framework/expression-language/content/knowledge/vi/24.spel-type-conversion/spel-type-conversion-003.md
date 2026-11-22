# Chuyển chuỗi thành số, Boolean và enum trong SpEL

## 1. Vì sao cần type conversion?

Spring Expression Language (SpEL) đánh giá biểu thức và nhận được một giá trị runtime. Trong nhiều trường hợp, giá trị đó cần được chuyển sang kiểu mà ứng dụng mong đợi: chuỗi thành số, chuỗi thành Boolean hoặc chuỗi thành enum.

SpEL thực hiện chuyển đổi thông qua `TypeConverter` trong `EvaluationContext`. Với cấu hình chuẩn, `StandardTypeConverter` tích hợp với Spring `ConversionService` và sử dụng các converter mặc định của Spring.

Ví dụ, expression tạo ra String `'42'`, nhưng Java code yêu cầu Integer:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

Integer quantity = parser.parseExpression("'42'")
        .getValue(context, Integer.class);

// quantity = 42
```

Khi gọi `getValue(context, Integer.class)`, SpEL biết kiểu đích là Integer và yêu cầu TypeConverter chuyển kết quả sang kiểu đó. Nếu chỉ gọi `getValue(context)`, kết quả tự nhiên vẫn là String `"42"`; SpEL không tự suy đoán kiểu mà caller sẽ cần về sau.

## 2. TypeConverter và ConversionService

Hai thành phần chính:

- `TypeConverter` là abstraction mà SpEL sử dụng để chuyển giá trị giữa kiểu nguồn và kiểu đích.
- `ConversionService` của Spring cung cấp hệ thống converter có thể tái sử dụng cho nhiều phần của ứng dụng.

Trong `StandardEvaluationContext`, TypeConverter mặc định là `StandardTypeConverter`. Converter này dùng shared default ConversionService nếu không truyền ConversionService riêng.

Có thể kiểm tra hoặc thay TypeConverter:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

TypeConverter converter = context.getTypeConverter();
```

Cấu hình ConversionService tùy chỉnh:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

Cách này cho phép ứng dụng thêm converter cho kiểu miền nghiệp vụ, chẳng hạn chuyển alias chuỗi thành enum hoặc chuyển một định dạng dữ liệu riêng thành kiểu domain.

## 3. Chuyển String thành kiểu số

Spring cung cấp converter từ String sang các kiểu số phổ biến, bao gồm:

- `Byte`, `Short`, `Integer`, `Long`.
- `Float`, `Double`.
- `BigInteger`, `BigDecimal`.

SpEL có thể chuyển kết quả String sang kiểu đích khi gọi `getValue()` với Class tương ứng:

```java
Integer count = parser.parseExpression("'42'")
        .getValue(context, Integer.class);

Long population = parser.parseExpression("'1200000'")
        .getValue(context, Long.class);

BigDecimal price = parser.parseExpression("'125.50'")
        .getValue(context, BigDecimal.class);
```

Các chuỗi số được xử lý theo cú pháp số mà Java/Spring hỗ trợ. Converter mặc định loại bỏ khoảng trắng ở đầu và cuối trước khi phân tích. Dấu thập phân dùng dấu chấm trong định dạng số chuẩn, không tự động dựa vào locale hiển thị của người dùng.

Ví dụ:

```text
' 42 '       -> Integer 42
'125.50'     -> BigDecimal 125.50
'1.25E3'     -> Double 1250.0
```

Chuỗi như `'12,50'` không phải định dạng thập phân chuẩn cho converter số mặc định. Nếu ứng dụng nhận số theo locale (ví dụ dấu phẩy là dấu thập phân), hãy đăng ký converter riêng có quy tắc locale rõ ràng.

### 3.1. Chọn kiểu số đích phù hợp

Không nên dùng một kiểu số duy nhất cho mọi trường hợp:

| Kiểu đích | Trường hợp thường dùng |
|---|---|
| `Integer` | Số lượng nhỏ, số lần thử, chỉ số. |
| `Long` | ID số hoặc số lượng có phạm vi lớn. |
| `Double` / `Float` | Tính toán gần đúng, dữ liệu đo lường. |
| `BigInteger` | Số nguyên lớn vượt phạm vi kiểu primitive. |
| `BigDecimal` | Tiền tệ và số thập phân cần độ chính xác. |

Với tiền tệ, nên chuyển trực tiếp từ chuỗi thập phân sang BigDecimal:

```java
BigDecimal amount = parser.parseExpression("'123456.78'")
        .getValue(context, BigDecimal.class);
```

Tránh chuyển chuỗi sang Double rồi mới tạo BigDecimal vì biểu diễn nhị phân của floating point có thể tạo sai số không mong muốn.

## 4. Chuyển String thành Boolean

Converter mặc định của Spring chấp nhận một số cách viết Boolean phổ biến, không phân biệt chữ hoa/chữ thường đối với các từ:

| Chuỗi đầu vào | Kết quả |
|---|---|
| `"true"`, `"TRUE"`, `"on"`, `"yes"`, `"1"` | `true` |
| `"false"`, `"FALSE"`, `"off"`, `"no"`, `"0"` | `false` |

Ví dụ:

```java
Boolean enabled = parser.parseExpression("'yes'")
        .getValue(context, Boolean.class);

Boolean disabled = parser.parseExpression("'OFF'")
        .getValue(context, Boolean.class);

Boolean flag = parser.parseExpression("'1'")
        .getValue(context, Boolean.class);
```

Các chuỗi rỗng sau khi trim có thể được chuyển thành null. Một chuỗi không nằm trong tập giá trị được hỗ trợ, ví dụ `'enabled'` hoặc `'maybe'`, không được tự động coi là true/false; chuyển đổi sẽ thất bại.

Nếu dữ liệu đầu vào đến từ form hoặc file cấu hình, hãy xác thực giá trị trước khi đánh giá expression. Không dùng quy tắc truthiness của ngôn ngữ khác để suy ra hành vi của Spring ConversionService.

## 5. Chuyển String thành enum

Spring hỗ trợ chuyển String thành enum bằng tên constant. Ví dụ:

```java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Có thể yêu cầu kiểu enum khi đánh giá:

```java
OrderStatus status = parser.parseExpression("'PAID'")
        .getValue(context, OrderStatus.class);

// OrderStatus.PAID
```

Converter enum mặc định dùng tên constant của enum. Việc so khớp tên có phân biệt chữ hoa/chữ thường:

```text
'PAID'  -> OrderStatus.PAID
'paid'  -> không khớp tên constant mặc định
```

Chuỗi được trim trước khi chuyển đổi; chuỗi rỗng có thể chuyển thành null. Một tên không tồn tại như `'COMPLETED'` sẽ gây lỗi chuyển đổi nếu enum không có constant đó.

Khi dùng enum trong expression, có thể kết hợp type reference để lấy constant trực tiếp:

```text
T(com.example.OrderStatus).PAID
```

Đây là cách tham chiếu enum constant bằng `T(...)`, không phải chuyển String thành enum. Hai cách khác nhau:

- `'PAID'` với target type `OrderStatus.class`: TypeConverter chuyển String sang enum.
- `T(com.example.OrderStatus).PAID`: SpEL phân giải enum type và truy cập static constant.

## 6. Chuyển đổi khi gán vào property có kiểu

Type conversion không chỉ xảy ra khi lấy kết quả bằng `getValue(context, TargetType.class)`. SpEL cũng chuyển đổi giá trị khi gán vào property hoặc phần tử có kiểu đích xác định.

Ví dụ class cấu hình:

```java
public class AppSettings {
    private Integer retryCount;
    private Boolean enabled;
    private OrderStatus status;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

Gán chuỗi vào các property có kiểu khác nhau:

```java
AppSettings settings = new AppSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

parser.parseExpression("retryCount").setValue(context, "5");
parser.parseExpression("enabled").setValue(context, "yes");
parser.parseExpression("status").setValue(context, "PAID");

// retryCount = 5
// enabled = true
// status = OrderStatus.PAID
```

Khi xử lý `setValue()`, SpEL biết kiểu đích thông qua metadata của property và dùng TypeConverter để chuyển chuỗi trước khi gán. Nếu converter không thể chuyển đổi, thao tác gán thất bại và giá trị không được gán theo kiểu đích mong muốn.

## 7. Generic metadata khi chuyển đổi phần tử collection

Spring ConversionService có thể dùng metadata generic của property đích để chuyển đổi phần tử trong collection.

Ví dụ property `List<Boolean>`:

```java
public class FeatureSettings {
    private List<Boolean> enabledFlags =
            new ArrayList<>(List.of(true, true));

    public List<Boolean> getEnabledFlags() {
        return enabledFlags;
    }

    public void setEnabledFlags(List<Boolean> enabledFlags) {
        this.enabledFlags = enabledFlags;
    }
}
```

Có thể gán chuỗi vào phần tử:

```java
FeatureSettings settings = new FeatureSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

parser.parseExpression("enabledFlags[0]")
        .setValue(context, "false");

Boolean firstFlag = settings.getEnabledFlags().get(0);
// Boolean.FALSE
```

SpEL và ConversionService có thể xác định phần tử đích là Boolean từ generic metadata của List. Do đó, chuỗi `"false"` được chuyển thành Boolean thay vì giữ nguyên String.

Điều này phụ thuộc metadata kiểu của property. Nếu collection chỉ được khai báo là `List<Object>` hoặc metadata generic không có, framework có thể không biết kiểu phần tử mong muốn. Khi cần chuyển đổi rõ ràng, hãy dùng kiểu đích cụ thể hoặc chuyển đổi từng phần tử trong Java.

## 8. Chuyển đổi tường minh bằng getValue()

Nếu expression tạo ra một giá trị có kiểu khác với kiểu caller cần, dùng overload `getValue()` nhận target Class:

```java
Integer retryCount = parser.parseExpression("'3'")
        .getValue(context, Integer.class);

Boolean active = parser.parseExpression("'on'")
        .getValue(context, Boolean.class);

OrderStatus status = parser.parseExpression("'SHIPPED'")
        .getValue(context, OrderStatus.class);
```

Target type phải tương thích với giá trị hoặc có converter phù hợp. Nếu không có converter, SpEL không tự ép kiểu tùy ý.

Ví dụ không nên giả định một chuỗi bất kỳ có thể chuyển thành số:

```java
Integer invalid = parser.parseExpression("'three'")
        .getValue(context, Integer.class);
```

Biểu thức này phát sinh lỗi chuyển đổi vì `"three"` không phải dạng số nguyên hợp lệ.

Nếu cần kiểm tra kết quả mà không làm luồng ứng dụng thất bại, bắt exception ở ranh giới Java và đưa ra thông báo validation phù hợp.

## 9. Đăng ký converter tùy chỉnh

Converter mặc định phù hợp với các kiểu phổ biến. Với quy tắc miền nghiệp vụ riêng, có thể đăng ký converter tùy chỉnh trong ConversionService.

Ví dụ chấp nhận alias `COMPLETED` như một cách viết khác của enum `PAID`:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        OrderStatus.class,
        source -> switch (source.trim().toUpperCase(Locale.ROOT)) {
            case "COMPLETED" -> OrderStatus.PAID;
            case "NEW" -> OrderStatus.NEW;
            case "PAID" -> OrderStatus.PAID;
            case "SHIPPED" -> OrderStatus.SHIPPED;
            case "CANCELLED" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown order status: " + source);
        });

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));

OrderStatus status = parser.parseExpression("'completed'")
        .getValue(context, OrderStatus.class);

// OrderStatus.PAID
```

Converter tùy chỉnh nên:

- Chuẩn hóa đầu vào nhất quán, ví dụ trim và dùng `Locale.ROOT` cho chuyển chữ hoa/chữ thường.
- Chỉ chấp nhận các giá trị được nghiệp vụ cho phép.
- Báo lỗi rõ ràng khi đầu vào không hợp lệ.
- Không thực hiện side effect hoặc truy cập hệ thống ngoài trong quá trình convert.
- Có unit test cho giá trị hợp lệ, alias và giá trị không hợp lệ.

Có thể dùng một ConversionService đã cấu hình chung cho nhiều context nếu các converter phù hợp với cùng quy tắc ứng dụng.

## 10. Dùng TypeConverter trong SimpleEvaluationContext

SimpleEvaluationContext cũng hỗ trợ type conversion. Context này giới hạn một số tính năng SpEL như constructor/type/bean reference, nhưng việc chuyển đổi giá trị vẫn có thể được cấu hình.

Ví dụ:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService))
                .build();
```

Nếu chỉ cần chuyển String sang số, Boolean hoặc enum khi đọc/ghi property, không cần bật constructor invocation hay type reference. Chọn context theo các khả năng expression thực sự cần dùng.

## 11. Lỗi chuyển đổi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| String không chuyển thành Integer | Chuỗi chứa ký tự không phải số hoặc vượt phạm vi kiểu. | Kiểm tra đầu vào và chọn Integer/Long/BigInteger phù hợp. |
| Số thập phân bị lỗi | Đầu vào dùng dấu phẩy theo locale trong khi converter mặc định mong đợi cú pháp số chuẩn. | Chuẩn hóa định dạng hoặc đăng ký converter theo locale. |
| String rỗng thành null | Converter chuẩn có thể xem chuỗi rỗng sau trim là null. | Xác thực chuỗi rỗng trước khi chuyển hoặc dùng kiểu wrapper/nullable phù hợp. |
| Boolean không nhận giá trị | Chuỗi không thuộc true/on/yes/1 hoặc false/off/no/0. | Chuẩn hóa và xác thực tập giá trị đầu vào. |
| Enum không tìm thấy constant | Tên enum sai hoặc khác chữ hoa/chữ thường. | Dùng đúng tên constant hoặc đăng ký converter xử lý alias/case. |
| setValue() không gán được | Giá trị không chuyển được sang kiểu property đích. | Kiểm tra setter/property type và TypeConverter đang dùng. |
| Collection giữ phần tử dạng String | Generic metadata của collection không cho biết kiểu phần tử đích. | Khai báo generic type cụ thể hoặc chuyển đổi phần tử rõ ràng. |
| getValue() trả String thay vì Number | Không truyền target type vào getValue(). | Dùng `getValue(context, Integer.class)` hoặc kiểu đích cần thiết. |
| Converter tùy chỉnh không được gọi | Converter chưa được đăng ký vào ConversionService gắn với context. | Dùng đúng ConversionService khi tạo StandardTypeConverter và setTypeConverter(). |
| Lỗi chỉ xảy ra với dữ liệu null | Kiểu đích là primitive hoặc không cho phép null. | Dùng wrapper type hoặc xử lý null trước khi gán. |

## 12. Quy trình kiểm thử type conversion

1. Xác định kiểu nguồn của expression, thường là String.
2. Xác định kiểu đích rõ ràng: Integer, Long, BigDecimal, Boolean hoặc enum.
3. Kiểm thử giá trị hợp lệ đại diện cho định dạng thực tế.
4. Kiểm thử khoảng trắng đầu/cuối, chuỗi rỗng và null nếu có thể xuất hiện.
5. Với Boolean, kiểm tra các token được chấp nhận và một token không hợp lệ.
6. Với enum, kiểm tra tên constant, khác chữ hoa/chữ thường và alias nếu có.
7. Với số, kiểm tra số nguyên, thập phân, số mũ, biên phạm vi và định dạng locale.
8. Kiểm tra cả `getValue(context, Target.class)` và `setValue()` nếu ứng dụng dùng cả hai.
9. Kiểm tra generic metadata khi gán vào collection hoặc property lồng nhau.
10. Đảm bảo EvaluationContext đang dùng đúng TypeConverter/ConversionService như môi trường ứng dụng.

## 13. Ghi nhớ

- SpEL dùng TypeConverter để chuyển giá trị sang kiểu đích; StandardTypeConverter tích hợp Spring ConversionService.
- `getValue(context, Target.class)` yêu cầu chuyển kết quả sang Target; `getValue(context)` giữ kiểu tự nhiên của expression.
- String có thể chuyển sang kiểu số phổ biến như Integer, Long, Double, BigInteger và BigDecimal.
- Boolean mặc định nhận true/on/yes/1 và false/off/no/0; giá trị khác không tự suy đoán.
- String thành enum dựa trên tên constant; converter mặc định phân biệt chữ hoa/chữ thường.
- `setValue()` cũng chuyển đổi theo kiểu property đích.
- Generic metadata giúp chuyển đổi phần tử collection như List<Boolean>.
- Có thể thêm converter tùy chỉnh vào DefaultConversionService và gắn vào StandardTypeConverter.
- Xác thực null, chuỗi rỗng, định dạng số, enum không hợp lệ và locale trước khi đưa dữ liệu vào nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type Conversion with Generics](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardTypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeConverter.html)
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [DefaultConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
