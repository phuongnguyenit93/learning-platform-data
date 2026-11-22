# Read-only và read-write data binding trong SpEL

Spring Expression Language (SpEL) có thể đọc và cập nhật property của object thông qua một EvaluationContext. Với những tình huống data binding, Spring cung cấp **SimpleEvaluationContext** cùng hai factory method quan trọng:

- **forReadOnlyDataBinding()** tạo context chỉ cho phép đọc property.
- **forReadWriteDataBinding()** tạo context cho phép đọc và ghi property.

Cả hai dùng **DataBindingPropertyAccessor** để truy cập public property theo quy ước data binding. Lựa chọn này giúp giới hạn khả năng của SpEL khi ứng dụng chỉ cần đọc dữ liệu hoặc cập nhật một số thuộc tính của object.

Read-only và read-write ở đây nói về quyền gán giá trị cho property trong expression. Chúng không biến SpEL thành một sandbox an toàn cho expression không đáng tin cậy; việc đọc property vẫn có thể gọi accessor có side effect.

## 1. SimpleEvaluationContext dành cho data binding

SpEL có hai implementation EvaluationContext thường gặp:

- **StandardEvaluationContext** cung cấp đầy đủ tính năng và khả năng tùy chỉnh của SpEL, phù hợp với các tình huống cấu hình nội bộ cần truy cập linh hoạt.
- **SimpleEvaluationContext** chỉ cung cấp một tập con tính năng, hướng đến điều kiện đơn giản, property-based filtering và data binding.

SimpleEvaluationContext yêu cầu ứng dụng chọn rõ mức truy cập property và method cần thiết. Theo mặc định, context này không hỗ trợ type reference, constructor invocation hoặc bean reference. Khả năng gọi method cũng không được bật mặc định.

Khi mục tiêu chỉ là đọc hoặc cập nhật dữ liệu trên object, hai factory method data binding giúp cấu hình context ngắn gọn và thể hiện rõ quyền truy cập mong muốn.

## 2. Read-only data binding

Tạo context chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Factory method này cấu hình DataBindingPropertyAccessor ở chế độ read-only và tắt assignment trong expression.

Có thể đọc property từ root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("customer.address.city");

String city = expression.getValue(
        context,
        order,
        String.class
);
~~~

Trong ví dụ, order là root object được truyền vào getValue(). SpEL đọc lần lượt customer, address và city. Expression không cần quyền ghi để thực hiện các thao tác này.

Cũng có thể đọc một property đơn giản:

~~~text
name
~~~

Hoặc property lồng nhau:

~~~text
customer.address.postalCode
~~~

Read-only data binding phù hợp khi expression dùng để hiển thị dữ liệu, tạo nhãn, lọc object, kiểm tra điều kiện hoặc trích xuất giá trị từ object graph.

### 2.1. Read-only ngăn assignment trong expression

Ví dụ expression có phép gán:

~~~text
name = 'Linh'
~~~

Khi đánh giá bằng context được tạo từ forReadOnlyDataBinding(), assignment bị vô hiệu hóa và expression không thể cập nhật property.

Điều này giúp ngăn expression data binding vô tình thay đổi trạng thái object khi nhiệm vụ chỉ yêu cầu đọc dữ liệu.

Cần phân biệt việc expression không được phép ghi với việc object Java tự nó là immutable. Context read-only không biến object thành immutable và không ngăn code Java khác cập nhật object đó.

### 2.2. Khi nào chọn read-only?

Dùng read-only khi:

1. Expression chỉ cần đọc property để hiển thị hoặc tạo dữ liệu đầu ra.
2. Expression được dùng để đánh giá điều kiện hoặc lọc object.
3. Không có yêu cầu cập nhật object thông qua SpEL.
4. Muốn giảm khả năng expression thay đổi trạng thái dữ liệu.
5. Muốn cấu hình data binding với quyền tối thiểu cần thiết.

Nếu chỉ cần đọc property, hãy ưu tiên read-only thay vì bật read-write rồi dựa vào quy ước rằng expression sẽ không gán giá trị.

## 3. Read-write data binding

Khi cần cập nhật property thông qua SpEL, tạo context bằng:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Factory method này cấu hình DataBindingPropertyAccessor ở chế độ read-write. Assignment được bật theo mặc định.

Ví dụ class có getter và setter:

~~~java
public class Customer {

    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Expression gán giá trị cho property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("name = 'Linh'");

Customer customer = new Customer();

Object result = expression.getValue(context, customer);

System.out.println(customer.getName()); // Linh
~~~

SpEL dùng root object customer, tìm property name và gọi cơ chế ghi tương ứng của DataBindingPropertyAccessor. Giá trị mới được đặt thông qua public setter trong ví dụ này.

Có thể gán property lồng nhau:

~~~text
address.city = 'Ho Chi Minh City'
~~~

Các object trung gian như address phải tồn tại và property đích phải có khả năng ghi. Data binding không tự tạo mọi object lồng nhau nếu chúng đang null.

### 3.1. Điều kiện để ghi được property

DataBindingPropertyAccessor hỗ trợ public property theo quy ước data binding:

- Khi đọc, property có thể được cung cấp qua public getter hoặc public field.
- Khi ghi, property cần public setter hoặc public field có thể ghi.
- Một property chỉ có getter thường đọc được nhưng không ghi được.
- Tên property trong expression phải khớp với property được accessor hỗ trợ.

Ví dụ property chỉ đọc:

~~~java
public String getDisplayName() {
    return displayName;
}
~~~

Expression có thể đọc displayName, nhưng không thể gán nếu class không cung cấp setter hoặc public field có thể ghi.

Nếu expression cần cập nhật nhiều thuộc tính, hãy xác định rõ object có setter tương ứng và trạng thái sau khi gán có hợp lệ theo quy tắc domain hay không.

### 3.2. Khi nào chọn read-write?

Dùng read-write khi:

1. Ứng dụng cần cập nhật property của object thông qua expression.
2. Một biểu mẫu hoặc data binding layer cần ghi giá trị vào model.
3. Expression thực hiện assignment có kiểm soát trên public property.
4. Các property đích có setter hoặc public field phù hợp.
5. Quyền ghi là một phần được dự kiến trong chức năng, không phải tác dụng phụ ngoài ý muốn.

Read-write chỉ mở quyền ghi property theo accessor được cấu hình. Nó không tự mở toàn bộ tính năng của StandardEvaluationContext.

## 4. So sánh read-only và read-write

| Tiêu chí | Read-only | Read-write |
| --- | --- | --- |
| Factory | forReadOnlyDataBinding() | forReadWriteDataBinding() |
| Property accessor | DataBindingPropertyAccessor ở chế độ đọc | DataBindingPropertyAccessor ở chế độ đọc/ghi |
| Đọc public property | Có | Có |
| Gán property trong expression | Bị tắt | Được bật mặc định |
| Setter hoặc public field có thể ghi | Không cần để đọc | Cần cho property đích khi ghi |
| Mục tiêu thường gặp | Hiển thị, lọc, kiểm tra | Form binding, cập nhật model |
| Constructor expression | Không hỗ trợ | Không hỗ trợ |
| Bean reference | Không hỗ trợ | Không hỗ trợ |
| Type reference T() | Không hỗ trợ | Không hỗ trợ |

Hai factory method đều tạo SimpleEvaluationContext. Khác biệt chính là cấu hình property accessor và quyền assignment.

Nếu ứng dụng cần cả khả năng tạo object, tham chiếu bean hoặc các tính năng SpEL đầy đủ khác, hãy xem xét StandardEvaluationContext và giới hạn các chiến lược truy cập theo đúng nhu cầu.

## 5. Root object khi dùng SimpleEvaluationContext

SimpleEvaluationContext thường được tạo mà không có root object mặc định. Cách dùng phổ biến là parse Expression một lần rồi truyền context cùng root object vào mỗi lần gọi getValue().

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("customer.address.city");

String firstCity = expression.getValue(
        context,
        firstOrder,
        String.class
);

String secondCity = expression.getValue(
        context,
        secondOrder,
        String.class
);
~~~

Cùng một expression và context có thể được dùng với các root object khác nhau. Điều này hữu ích khi một quy tắc data binding được áp dụng lặp lại trên nhiều object cùng cấu trúc.

Có thể dùng variable nếu cần cung cấp thêm dữ liệu ngoài root object:

~~~java
context.setVariable("requiredRegion", "APAC");
~~~

Expression:

~~~text
region == #requiredRegion
~~~

Ở đây region là property của root object; requiredRegion là variable được đăng ký trong context.

## 6. DataBindingPropertyAccessor và phạm vi property

Hai factory method data binding sử dụng **DataBindingPropertyAccessor**. Accessor này được thiết kế cho property do ứng dụng khai báo, chẳng hạn property của JavaBean hoặc kiểu dữ liệu có accessor công khai.

Nó không phân giải các technical property trên java.lang.Object hoặc java.lang.Class theo cách rộng như ReflectivePropertyAccessor. Mục tiêu là cung cấp truy cập property phục vụ data binding, thay vì mở toàn bộ reflective property access.

Ví dụ:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Các expression:

~~~text
city
city = 'Da Nang'
~~~

có thể lần lượt đọc và ghi city tùy context được tạo ở chế độ read-only hay read-write.

Với kiểu dữ liệu tùy chỉnh hoặc cấu trúc không theo JavaBean, có thể xây dựng SimpleEvaluationContext bằng factory forPropertyAccessors() và đăng ký PropertyAccessor phù hợp.

## 7. Tùy chỉnh SimpleEvaluationContext

Ngoài hai factory data binding có sẵn, Builder của SimpleEvaluationContext cho phép cấu hình thêm một số khả năng.

### 7.1. Dùng PropertyAccessor tùy chỉnh

Khi dữ liệu có cấu trúc riêng, có thể cung cấp accessor:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .build();
~~~

Có thể kết hợp custom accessor với DataBindingPropertyAccessor nếu cần cả property riêng và property data binding.

### 7.2. Tắt assignment trên builder tùy chỉnh

Context được tạo từ forPropertyAccessors() cho phép assignment theo mặc định. Nếu muốn chỉ đọc, có thể tắt assignment:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .withAssignmentDisabled()
                .build();
~~~

Với nhu cầu data binding chỉ đọc thông thường, forReadOnlyDataBinding() là lựa chọn trực tiếp và dễ hiểu hơn.

### 7.3. Bật instance method invocation khi thực sự cần

SimpleEvaluationContext không bật method resolution mặc định. Builder có thể thêm DataBindingMethodResolver cho instance method:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Cấu hình này bổ sung khả năng gọi instance method được resolver hỗ trợ. Nó không mở static method invocation và không biến context thành StandardEvaluationContext.

Chỉ bật method invocation khi expression thực sự cần. Nếu mục tiêu chỉ là đọc property, không cần thêm khả năng này.

### 7.4. Cấu hình ConversionService

Builder cũng cho phép cung cấp ConversionService tùy chỉnh:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Điều này hữu ích khi dữ liệu đầu vào cần được chuyển đổi theo quy tắc của ứng dụng. Ví dụ, một chuỗi từ form có thể cần chuyển thành kiểu số hoặc kiểu domain trước khi được gán cho property.

ConversionService xử lý chuyển đổi kiểu; nó không thay thế property accessor và cũng không tự tạo setter cho property không có khả năng ghi.

## 8. Phân biệt property assignment và method invocation

Read-write data binding cho phép gán property. Điều đó không đồng nghĩa mọi method của object đều được phép gọi.

SimpleEvaluationContext không bật method resolver mặc định. Nếu cần instance method, phải chủ động thêm resolver phù hợp, chẳng hạn withInstanceMethods().

Ví dụ property assignment:

~~~text
name = 'Linh'
~~~

Đây là thao tác ghi property.

Ví dụ method invocation:

~~~text
changeName('Linh')
~~~

Đây là lời gọi method và cần method resolver được cấu hình, ngoài việc method đó có thể truy cập được.

Không nên nhầm hai khả năng. Một context read-write có thể cho phép gán property nhưng vẫn từ chối lời gọi method vì method invocation chưa được bật.

## 9. Read-only không phải là bảo đảm getter không có side effect

Read-only data binding chỉ kiểm soát việc assignment property trong expression. Nó không chứng minh rằng việc đọc một property là thao tác thuần.

Một getter Java có thể thực hiện hành động trước khi trả về giá trị. Ví dụ, accessor-shaped method có thể ghi log, cập nhật trạng thái, truy cập hệ thống bên ngoài hoặc gây side effect khác.

Vì vậy:

- Chỉ đưa vào root object những kiểu dữ liệu có accessor phù hợp với mục đích expression.
- Không xem SimpleEvaluationContext là sandbox an toàn cho expression do người dùng không tin cậy cung cấp.
- Kiểm tra getter và method có thể truy cập để bảo đảm việc đọc không gây tác động ngoài dự kiến.
- Hạn chế object graph được đưa vào context.
- Không bật method invocation hoặc accessor rộng hơn nhu cầu.

Tài liệu Spring nhấn mạnh rằng SimpleEvaluationContext chỉ giới hạn một tập con cú pháp và tính năng. Việc dùng read-only không tự bảo đảm expression an toàn.

## 10. Ví dụ kiểm thử read-only và read-write

Có thể kiểm tra hai chế độ bằng JUnit:

~~~java
class DataBindingContextTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsPropertyWithReadOnlyContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadOnlyDataBinding()
                        .build();

        Customer customer = new Customer("An");

        String name = parser
                .parseExpression("name")
                .getValue(context, customer, String.class);

        assertEquals("An", name);
    }

    @Test
    void rejectsAssignmentWithReadOnlyContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadOnlyDataBinding()
                        .build();

        Customer customer = new Customer("An");

        assertThrows(EvaluationException.class, () ->
                parser.parseExpression("name = 'Linh'")
                        .getValue(context, customer)
        );
    }

    @Test
    void updatesPropertyWithReadWriteContext() {
        SimpleEvaluationContext context =
                SimpleEvaluationContext
                        .forReadWriteDataBinding()
                        .build();

        Customer customer = new Customer("An");

        parser.parseExpression("name = 'Linh'")
                .getValue(context, customer);

        assertEquals("Linh", customer.getName());
    }
}
~~~

Test đầu xác nhận property được đọc. Test thứ hai xác nhận assignment bị chặn trong read-only context. Test cuối xác nhận read-write context cập nhật property qua accessor phù hợp.

Trong ứng dụng thực tế, hãy kiểm thử cả property chỉ có getter, property có setter, property lồng nhau và các trường hợp object trung gian null nếu dữ liệu có thể ở trạng thái đó.

## 11. Những lỗi thường gặp

1. **Dùng read-only nhưng vẫn viết assignment:** expression như name = 'Linh' không được phép trong context read-only.
2. **Dùng read-write nhưng property không có setter:** accessor không thể ghi property chỉ có getter nếu không có public field có thể ghi.
3. **Nhầm read-write với StandardEvaluationContext:** read-write vẫn là SimpleEvaluationContext và không hỗ trợ constructor, type reference hoặc bean reference.
4. **Cho rằng method invocation tự được bật:** cần thêm method resolver nếu muốn gọi instance method.
5. **Không truyền root object:** SimpleEvaluationContext thường được dùng bằng cách truyền root object vào getValue(context, rootObject).
6. **Object trung gian null:** property path lồng nhau có thể thất bại nếu object ở giữa không tồn tại.
7. **Cho rằng read-only ngăn mọi side effect:** getter vẫn có thể thực hiện hành động.
8. **Dùng accessor không phù hợp:** property tùy chỉnh cần PropertyAccessor tương ứng.
9. **Dùng chung context mutable thiếu kiểm soát:** các variable hoặc cấu hình context có thể ảnh hưởng nhiều lần evaluate.
10. **Coi SimpleEvaluationContext là sandbox:** context hạn chế tính năng nhưng không bảo đảm expression từ nguồn không tin cậy an toàn.

## 12. Ghi nhớ nhanh

- **SimpleEvaluationContext.forReadOnlyDataBinding()** tạo context đọc property và tắt assignment.
- **SimpleEvaluationContext.forReadWriteDataBinding()** tạo context đọc/ghi property và bật assignment mặc định.
- Cả hai dùng **DataBindingPropertyAccessor**.
- Đọc property thường cần public getter hoặc public field; ghi cần public setter hoặc public field có thể ghi.
- Read-write chỉ mở quyền ghi property theo accessor; nó không mở toàn bộ tính năng SpEL.
- SimpleEvaluationContext không hỗ trợ type reference, constructor invocation hoặc bean reference.
- Method invocation không bật mặc định; có thể thêm instance method resolver khi thật sự cần.
- SimpleEvaluationContext thường nhận root object qua getValue(context, rootObject).
- Có thể tùy chỉnh PropertyAccessor, assignment và ConversionService qua Builder.
- Read-only không bảo đảm getter không có side effect và không phải sandbox cho expression không tin cậy.
- Chọn read-only nếu chỉ cần đọc; chỉ chọn read-write khi chức năng thực sự cần cập nhật property.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [DataBindingPropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [DataBindingMethodResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingMethodResolver.html)
- [Spring Framework — Security Considerations for EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html#expressions-evaluation-context-security)
