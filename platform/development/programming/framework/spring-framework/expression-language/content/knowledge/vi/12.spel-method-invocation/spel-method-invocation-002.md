# Method overload và lựa chọn chữ ký phù hợp trong SpEL

## Mục tiêu

Java cho phép một class khai báo nhiều method cùng tên nhưng khác danh sách tham số. Đây là method overloading. Khi biểu thức SpEL gọi method, parser cần xác định method nào trên object đích phù hợp với các đối số được truyền vào.

SpEL hỗ trợ method invocation bằng cú pháp quen thuộc như `customer.findById('C-17')`. Việc chọn overload phụ thuộc vào method có sẵn trên runtime class của object, kiểu thực tế của các đối số và khả năng chuyển đổi kiểu của evaluation context. Nếu nhiều chữ ký cùng phù hợp hoặc đối số không đủ thông tin kiểu, lời gọi có thể thất bại hoặc trở nên khó đoán. Cách tốt nhất là truyền đối số có kiểu rõ ràng và thiết kế API biểu thức tránh các overload mơ hồ.

## 1. Overload là gì?

Overload là nhiều method cùng tên trong cùng class hoặc hệ phân cấp class nhưng có danh sách tham số khác nhau. Ví dụ:

```java
public class CustomerLookup {
    public Customer find(String customerId) {
        // ...
    }

    public Customer find(Long numericId) {
        // ...
    }

    public Customer find(String region, String customerId) {
        // ...
    }
}
```

Ba method đều tên `find`, nhưng có hai kiểu tham số hoặc số lượng tham số khác nhau. Trong SpEL, cú pháp gọi method vẫn là:

```spel
find('C-17')
```

hoặc gọi trên một property/biến:

```spel
customerLookup.find('C-17')
#lookup.find('C-17')
```

Method override là trường hợp khác: subclass thay thế implementation của method cùng chữ ký. Overload được lựa chọn khi phân giải lời gọi; override được JVM dispatch theo runtime object sau khi method signature đã được chọn.

## 2. SpEL tìm method như thế nào?

Với `StandardEvaluationContext`, SpEL mặc định dùng reflective method resolution. `ReflectiveMethodResolver` tìm method phù hợp trên runtime class của object đích, dựa trên tên method, số lượng đối số và kiểu đối số. Method được chọn sau đó được gọi bằng reflection.

Khi đánh giá một lời gọi, các yếu tố chính gồm:

1. **Tên và số lượng tham số:** method phải có tên phù hợp và nhận được số đối số của biểu thức, tính cả cách xử lý varargs nếu có.
2. **Kiểu runtime của đối số:** một đối số `String`, `Integer`, `Long` hoặc một class cụ thể cung cấp thông tin để phân biệt overload.
3. **Khả năng gán kiểu:** method nhận đúng kiểu hoặc kiểu tham số tương thích có thể được ưu tiên.
4. **Chuyển đổi kiểu:** `TypeConverter` của evaluation context có thể chuyển đối số sang kiểu tham số mà method yêu cầu.
5. **Tính duy nhất của kết quả:** nếu không có method phù hợp hoặc có nhiều ứng viên không thể phân biệt rõ, SpEL có thể báo lỗi phân giải method.

Quy tắc chuyển đổi khiến một số lời gọi hợp lệ dù kiểu đối số ban đầu không trùng kiểu tham số. Tuy nhiên, không nên dựa vào chuyển đổi ngầm khi class có nhiều overload có thể nhận cùng một giá trị.

## 3. Kiểu đối số quyết định overload

Giả sử class có các method:

```java
public class SearchService {
    public String search(String key) {
        return "string:" + key;
    }

    public String search(Integer key) {
        return "integer:" + key;
    }

    public String search(Number key) {
        return "number:" + key;
    }
}
```

Với root object là `SearchService`, các biểu thức sau cung cấp kiểu đối số khác nhau:

| Biểu thức | Kiểu đối số | Chữ ký phù hợp mong đợi |
| --- | --- | --- |
| `search('A-10')` | `String` | `search(String)` |
| `search(10)` | Numeric literal kiểu `Integer` trong trường hợp thông thường | `search(Integer)` là match cụ thể nhất. |
| `search(T(java.lang.Long).valueOf('10'))` | `Long` | `search(Number)` nếu không có overload nhận `Long`. |

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(new SearchService());

String byText = parser.parseExpression("search('A-10')")
        .getValue(context, String.class);

String byInteger = parser.parseExpression("search(10)")
        .getValue(context, String.class);

String byLong = parser.parseExpression(
        "search(T(java.lang.Long).valueOf('10'))")
        .getValue(context, String.class);
```

Trong ví dụ này, `T(java.lang.Long)` là type reference của SpEL; `valueOf` tạo ra một đối tượng `Long` trước khi gọi overload `search`. Cách tạo đối số có kiểu cụ thể giúp lời gọi rõ ràng hơn so với việc để parser tự chuyển một chuỗi hoặc số sang nhiều kiểu ứng viên.

## 4. Chuyển đổi kiểu có thể ảnh hưởng việc chọn overload

Evaluation context có một `TypeConverter`. Với context mặc định, SpEL có thể chuyển đổi một số kiểu thông dụng khi gọi method. Ví dụ, nếu class chỉ có `setLimit(Integer)`, giá trị chuỗi `'25'` có thể được chuyển thành `Integer` trong lúc thực thi:

```java
public class QueryOptions {
    private Integer limit;

    public void setLimit(Integer limit) {
        this.limit = limit;
    }
}
```

```spel
setLimit('25')
```

Nhưng nếu class có cả `setLimit(String)` và `setLimit(Integer)`, một chuỗi đầu vào đã khớp trực tiếp với `String`. Không nên mong rằng SpEL sẽ tự suy ra ý định muốn chuyển chuỗi thành số. Hãy chuyển kiểu rõ ràng:

```spel
setLimit(T(java.lang.Integer).valueOf('25'))
```

Chuyển đổi kiểu có thể phụ thuộc vào `ConversionService` hoặc `TypeConverter` được cấu hình trong context. Nếu ứng dụng thay converter mặc định, tập kiểu chuyển đổi hợp lệ và khả năng phân giải overload cũng có thể thay đổi.

## 5. Tránh lời gọi mơ hồ với null

`null` không mang runtime class cụ thể. Vì vậy, nếu class có nhiều overload nhận các kiểu tham chiếu khác nhau, một lời gọi với đối số null có thể không đủ thông tin để chọn đúng method:

```java
public class NotificationService {
    public String sendTo(String email) {
        return "email";
    }

    public String sendTo(Integer userId) {
        return "user-id";
    }
}
```

```spel
sendTo(null)
```

Không nên dựa vào lời gọi này để chọn một trong hai overload. Hãy kiểm tra null trước và gọi một method có tên riêng cho trường hợp thiếu dữ liệu:

```spel
recipient == null ? sendToDefault() : sendTo(recipient)
```

Nếu cần giữ cùng tên method, hãy đổi thiết kế API để không có nhiều overload tham chiếu cạnh tranh cho trường hợp null, hoặc cung cấp một wrapper/helper có kiểu và ý nghĩa rõ ràng.

## 6. Kiểu trả về không chọn overload

Kiểu đích truyền cho `getValue`, ví dụ `getValue(context, String.class)`, được dùng để chuyển đổi kết quả của biểu thức sau khi biểu thức đã được đánh giá. Nó không phải chỉ dẫn để chọn method overload.

Ví dụ, nếu `calculate(Integer)` và `calculate(String)` cùng tồn tại, viết:

```java
String result = parser.parseExpression("calculate(10)")
        .getValue(context, String.class);
```

không có nghĩa là yêu cầu SpEL chọn overload trả về `String`. Overload được quyết định từ lời gọi `calculate(10)` và kiểu đối số; sau đó kết quả mới được chuyển đổi sang kiểu yêu cầu nếu cần.

Vì vậy, muốn điều khiển overload, hãy điều khiển kiểu đối số hoặc thay đổi tên method. Không dùng kiểu trả về mong muốn như một cách ép chọn chữ ký.

## 7. Gọi overload trên object và static method

Overload có thể xuất hiện trên object thông thường, object trong biến context hoặc static method.

```spel
customer.format('Lan')
#formatter.format(100)
T(java.lang.Math).max(10, 20)
```

- `customer.format('Lan')` tìm method trên runtime class của `customer`.
- `#formatter.format(100)` tìm method trên object được đăng ký trong evaluation context bằng biến `formatter`.
- `T(java.lang.Math).max(10, 20)` gọi static method `max` trên class `Math`; các numeric argument giúp resolver chọn overload số phù hợp.

Type reference `T(...)` cần type locator cho phép class tương ứng. Trong context bị giới hạn hoặc ứng dụng có chính sách bảo mật chặt, không phải class nào cũng được phép tham chiếu.

## 8. Tùy chỉnh method resolution và type conversion

`StandardEvaluationContext` cho phép cấu hình cách SpEL tìm method và chuyển đổi giá trị:

- **MethodResolver:** xác định cách tìm method. Resolver mặc định là reflective; ứng dụng có thể thêm resolver riêng hoặc thay danh sách resolver để chỉ cho phép những method đã định trước.
- **TypeConverter:** chuyển đối số sang kiểu tham số khi cần. Có thể cấu hình converter riêng phù hợp với quy tắc dữ liệu của ứng dụng.
- **MethodFilter:** với reflective resolver, có thể giới hạn các method được phép trên một type cụ thể.

Ví dụ đăng ký một `MethodFilter` để giới hạn các method có thể gọi trên một class:

```java
StandardEvaluationContext context = new StandardEvaluationContext(service);
context.registerMethodFilter(SearchService.class, methods ->
        methods.stream()
                .filter(method -> method.getName().equals("search"))
                .toList());
```

Đây là ví dụ minh họa ý tưởng allowlist; trong ứng dụng thực tế cần kiểm tra class đích, chữ ký tham số và phiên bản Java đang sử dụng. `registerMethodFilter` làm việc với reflective method resolver; nếu thay resolver mặc định, cần bảo đảm resolver mới tôn trọng chính sách lọc tương ứng.

Nếu biểu thức đến từ người dùng hoặc nguồn không tin cậy, không nên cung cấp một `StandardEvaluationContext` có toàn bộ quyền reflection một cách mặc định. Hãy dùng context giới hạn, resolver allowlist và chỉ expose các object/method cần thiết. Không coi việc ẩn một vài overload là biện pháp sandbox đầy đủ.

## 9. Thiết kế API dễ dùng từ SpEL

SpEL thường được dùng trong cấu hình, rule, template hoặc biểu thức do ứng dụng lưu trữ. Những API có quá nhiều overload cùng tên sẽ làm biểu thức khó đọc và khó kiểm soát.

Ưu tiên các cách sau:

- Dùng tên method khác nhau khi ý nghĩa đầu vào khác nhau, ví dụ `findByCode(String)` và `findById(Long)`.
- Nếu phải giữ overload, truyền đối số có kiểu rõ ràng thay vì dựa vào conversion ngầm.
- Tránh overload nhận nhiều kiểu tham chiếu không liên quan nếu lời gọi có thể nhận null.
- Không dựa vào kiểu kết quả của `getValue` để ép chọn overload.
- Tách kiểm tra null khỏi lời gọi method; dùng một method riêng cho trường hợp không có giá trị.
- Với rule quan trọng, tạo helper method nhỏ có chữ ký ổn định thay vì expose cả một API phức tạp cho SpEL.

Ví dụ API có ý nghĩa rõ ràng hơn:

```java
public class CustomerLookup {
    public Customer findByCode(String code) {
        // ...
    }

    public Customer findByNumericId(Long id) {
        // ...
    }

    public Customer findDefault() {
        // ...
    }
}
```

Biểu thức tương ứng dễ hiểu và không cần suy luận overload:

```spel
findByCode('C-17')
findByNumericId(T(java.lang.Long).valueOf('17'))
recipient == null ? findDefault() : findByCode(recipient)
```

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy method | Sai tên, sai số tham số, method không truy cập được hoặc không có chữ ký tương thích. | Kiểm tra runtime class, tên method, số đối số và kiểu tham số. |
| Lời gọi với chuỗi không chọn overload số | `String` khớp trực tiếp với overload nhận String; chuyển đổi sang số không phải ý định rõ ràng. | Dùng `T(Integer).valueOf(...)` hoặc truyền sẵn đối tượng có kiểu từ context. |
| Lời gọi `method(null)` thất bại hoặc mơ hồ | Null không có runtime type để phân biệt nhiều overload tham chiếu. | Kiểm tra null trước hoặc gọi method riêng cho trường hợp null. |
| Một biểu thức chạy được ở môi trường này nhưng lỗi ở môi trường khác | TypeConverter, MethodResolver hoặc runtime class khác nhau. | Kiểm tra cấu hình evaluation context và kiểu thực tế của đối số. |
| Kết quả không có kiểu mong muốn | `getValue(..., TargetType.class)` chỉ chuyển đổi kết quả sau evaluation. | Điều chỉnh biểu thức/đối số và kiểm tra kiểu trả về của method được chọn. |
| Method không được phép gọi trong context giới hạn | Resolver hoặc policy chỉ expose một tập method cụ thể. | Bổ sung method vào allowlist có kiểm soát hoặc tạo helper API phù hợp. |

## Ghi nhớ

- Overload là các method cùng tên nhưng khác danh sách tham số; override là thay implementation của cùng chữ ký.
- SpEL chọn method dựa trên runtime target class, tên, số lượng và kiểu đối số, cùng khả năng chuyển đổi của context.
- Đối số có kiểu cụ thể giúp resolver phân biệt overload rõ ràng hơn.
- Chuyển đổi kiểu có thể làm một lời gọi hợp lệ, nhưng nhiều overload có thể khiến ý định trở nên mơ hồ.
- `null` không có runtime class; tránh gọi overload tham chiếu khác nhau bằng `method(null)`.
- Kiểu đích của `getValue` dùng cho kết quả, không dùng để chọn overload.
- Có thể tùy chỉnh `MethodResolver`, `MethodFilter` và `TypeConverter` để kiểm soát khả năng gọi method.
- Với rule quan trọng hoặc biểu thức không tin cậy, expose một API helper nhỏ, rõ ràng và có giới hạn.

## Tài liệu tham khảo

- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ReflectiveMethodResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveMethodResolver.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)