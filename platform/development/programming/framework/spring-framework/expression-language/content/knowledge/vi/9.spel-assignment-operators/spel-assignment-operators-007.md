# Giới hạn gán trong SimpleEvaluationContext

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Spring Expression Language (SpEL) giới hạn thao tác gán trong SimpleEvaluationContext; phân biệt việc gán thuộc tính, gán biến và gọi API setValue; chọn cấu hình chỉ đọc hoặc đọc ghi phù hợp; và xử lý lỗi khi biểu thức cố thay đổi dữ liệu mà context không cho phép.

## 1. Vì sao cần giới hạn thao tác gán?

SpEL không chỉ đọc giá trị. Tùy biểu thức và EvaluationContext, nó còn có thể thay đổi thuộc tính của đối tượng:

~~~text
name = 'An'
~~~

Một biểu thức có quyền ghi có thể thay đổi trạng thái của object mà ứng dụng truyền vào. Nếu biểu thức được lấy từ cấu hình hoặc nguồn bên ngoài, quyền ghi quá rộng có thể dẫn đến việc dữ liệu bị sửa ngoài ý muốn.

SimpleEvaluationContext được thiết kế cho những trường hợp chỉ cần một phần khả năng của SpEL, chẳng hạn data binding và lọc dữ liệu theo thuộc tính. Ứng dụng phải chọn rõ phạm vi truy cập thuộc tính và phương thức. Nhờ đó, việc đọc và ghi có thể được giới hạn theo nhu cầu.

Điểm cần nhớ: SimpleEvaluationContext không phải lúc nào cũng cấm mọi thao tác ghi. Khả năng ghi phụ thuộc vào loại context và PropertyAccessor được cấu hình.

## 2. Ba khái niệm cần phân biệt

Trong SpEL có ba cách dễ bị nhầm lẫn:

1. **Gán thuộc tính trong biểu thức:** dùng toán tử dấu bằng để thay đổi thuộc tính của root object hoặc một đối tượng có thể truy cập.
2. **Gán biến trong biểu thức:** dùng toán tử dấu bằng với biến có tiền tố dấu thăng, ví dụ cập nhật biến trong EvaluationContext.
3. **Gán từ Java:** ứng dụng gọi setVariable hoặc Expression.setValue trực tiếp qua API.

Ba cách này đi qua những cơ chế khác nhau. Việc context cho phép một loại thao tác không có nghĩa là tất cả các loại thao tác còn lại cũng được phép.

## 3. Gán thuộc tính trong biểu thức

Giả sử có một JavaBean đơn giản:

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

Có thể dùng biểu thức sau để thay đổi thuộc tính:

~~~text
name = 'An'
~~~

Khi đánh giá biểu thức với root object là một Customer, SpEL cần một PropertyAccessor có khả năng ghi thuộc tính name.

Nếu tạo context chỉ đọc:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

context này sử dụng DataBindingPropertyAccessor ở chế độ chỉ đọc và tắt toán tử gán trong biểu thức. Do đó, biểu thức yêu cầu ghi thuộc tính sẽ không được chấp nhận.

Nếu ứng dụng thực sự cần data binding hai chiều, có thể tạo context đọc ghi:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name = 'An'");

Customer customer = new Customer();

String assignedName =
    expression.getValue(context, customer, String.class);
~~~

Sau khi đánh giá, thuộc tính name của customer được cập nhật thành An. Khả năng ghi đến từ DataBindingPropertyAccessor ở chế độ đọc ghi.

Chỉ dùng cấu hình này khi nghiệp vụ thật sự cần biểu thức thay đổi thuộc tính. Với bộ lọc hoặc quy tắc chỉ cần đọc dữ liệu, context chỉ đọc phù hợp hơn.

## 4. Gán biến khác với gán thuộc tính

Một biến trong EvaluationContext thường được tham chiếu bằng tiền tố dấu thăng:

~~~text
#currentName
~~~

Ứng dụng có thể đăng ký biến từ Java:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

context.setVariable("currentName", "An");
~~~

Sau đó biểu thức có thể đọc biến:

~~~text
#currentName
~~~

Tuy nhiên, SimpleEvaluationContext không hỗ trợ gán biến bên trong biểu thức. Ví dụ:

~~~text
#currentName = 'Binh'
~~~

sẽ bị từ chối. Đây là giới hạn riêng của SimpleEvaluationContext, kể cả khi context được cấu hình đọc ghi thuộc tính.

Nếu cần cập nhật biến, hãy thực hiện từ mã Java:

~~~java
context.setVariable("currentName", "Binh");
~~~

Vì vậy, cần phân biệt:

| Thao tác | SimpleEvaluationContext |
|---|---|
| Đọc biến bằng #name | Có |
| Đăng ký hoặc cập nhật biến bằng context.setVariable từ Java | Có |
| Gán biến bằng biểu thức #name = value | Không hỗ trợ |
| Đọc thuộc tính qua data binding chỉ đọc | Có |
| Ghi thuộc tính bằng biểu thức với read-only data binding | Không |
| Ghi thuộc tính với read-write data binding | Có, nếu thuộc tính có thể ghi |

## 5. Toán tử gán, tăng và giảm

Trong những phiên bản Spring có hỗ trợ cờ assignment của EvaluationContext, khi isAssignmentEnabled trả về false, các toán tử sau bị vô hiệu hóa trong biểu thức:

- Gán: dấu bằng đơn.
- Tăng: toán tử hai dấu cộng.
- Giảm: toán tử hai dấu trừ.

Ví dụ:

~~~text
#counter = #counter + 1
#counter++
#counter--
~~~

Các biểu thức trên không thể dùng để cập nhật biến của SimpleEvaluationContext. Đối với gán thuộc tính, việc cho phép còn phụ thuộc vào quyền ghi của PropertyAccessor.

SimpleEvaluationContext.forReadOnlyDataBinding() tạo context chỉ đọc và tắt assignment. SimpleEvaluationContext.forReadWriteDataBinding() cho phép ghi thuộc tính theo data binding và mặc định bật assignment cho biểu thức. Có thể tắt assignment trên builder của các context phù hợp bằng withAssignmentDisabled().

Ví dụ:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadWriteDataBinding()
        .withAssignmentDisabled()
        .build();
~~~

Cấu hình này giữ accessor data binding đọc ghi nhưng tắt các toán tử gán, tăng và giảm trong biểu thức. Khi cần chính sách chỉ đọc toàn diện cho thuộc tính, nên chọn forReadOnlyDataBinding() ngay từ đầu.

Lưu ý về phiên bản: API isAssignmentEnabled và Builder.withAssignmentDisabled được bổ sung từ Spring Framework 5.3.38. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra Javadoc của đúng phiên bản trước khi sử dụng phương thức này.

## 6. Gán qua Expression.setValue

Ngoài toán tử gán nằm trong chuỗi biểu thức, SpEL cung cấp API Expression.setValue để ứng dụng chủ động ghi giá trị vào một thuộc tính:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Customer customer = new Customer();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.setValue(context, customer, "Binh");
~~~

Ở đây, biểu thức chỉ xác định thuộc tính name. Mã Java gọi setValue để yêu cầu SpEL ghi giá trị Binh vào thuộc tính đó.

Đây là thao tác ghi được khởi tạo từ Java, không phải biểu thức tự gán biến. Nó vẫn cần PropertyAccessor hỗ trợ ghi và thuộc tính phải có thể được cập nhật.

Không nên suy luận rằng việc SimpleEvaluationContext cấm gán biến trong biểu thức cũng làm mất API setVariable hoặc mọi API setValue. Hãy xét đúng thao tác đang được gọi và quyền mà accessor cung cấp.

## 7. Gán qua PropertyAccessor tùy chỉnh

SimpleEvaluationContext cho phép ứng dụng cung cấp PropertyAccessor riêng để kiểm soát cách đọc và ghi dữ liệu.

Ví dụ tạo context từ accessor tùy chỉnh:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(customPropertyAccessor)
        .build();
~~~

Với factory forPropertyAccessors, assignment được bật mặc định trong biểu thức. Nếu không muốn biểu thức tự thay đổi thuộc tính, có thể tắt:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(customPropertyAccessor)
        .withAssignmentDisabled()
        .build();
~~~

Accessor tùy chỉnh quyết định thuộc tính nào có thể đọc hoặc ghi và cách thực hiện thao tác. Đây là lựa chọn hữu ích khi dữ liệu không phải JavaBean thông thường, ví dụ một cấu trúc key-value hoặc một mô hình dữ liệu chuyên biệt.

Không nên đưa một ReflectivePropertyAccessor thông thường vào SimpleEvaluationContext. SimpleEvaluationContext được thiết kế để dùng DataBindingPropertyAccessor hoặc accessor tùy chỉnh có phạm vi rõ ràng.

## 8. Cách xử lý khi phép gán bị từ chối

Nếu biểu thức cố gắng ghi vào thuộc tính chỉ đọc hoặc thực hiện một phép gán không được hỗ trợ, SpEL có thể ném SpelEvaluationException hoặc một lỗi đánh giá tương ứng.

Ví dụ, ứng dụng nên bắt lỗi ở lớp gọi biểu thức:

~~~java
try {
    expression.getValue(context, customer);
}
catch (EvaluationException ex) {
    // Ghi log phù hợp và xử lý lỗi theo quy tắc ứng dụng.
}
~~~

Không nên bắt mọi ngoại lệ rồi âm thầm coi phép gán thất bại là thành công. Ứng dụng cần phân biệt lỗi do context không cho phép ghi, thuộc tính không tồn tại, chuyển đổi kiểu không thành công hoặc setter tự ném lỗi.

Nếu thao tác ghi là bắt buộc, hãy kiểm tra cấu hình context và accessor trước khi đưa biểu thức vào sử dụng. Nếu thao tác ghi không được phép, hãy giữ context chỉ đọc và xử lý biểu thức không hợp lệ như một lỗi cấu hình.

## 9. SimpleEvaluationContext không phải StandardEvaluationContext

Hai context có phạm vi khả năng khác nhau:

| Khả năng | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Đọc thuộc tính | Có, cần chọn accessor | Có, cấu hình linh hoạt |
| Ghi thuộc tính | Có thể bật bằng read-write accessor | Có, nếu accessor cho phép |
| Gán biến bên trong biểu thức | Không hỗ trợ | Có |
| Gán biến từ Java qua setVariable | Có | Có |
| Tham chiếu kiểu Java bằng T(...) | Không hỗ trợ | Có thể cấu hình |
| Tạo đối tượng bằng new | Không hỗ trợ | Có thể cấu hình |
| Tham chiếu bean bằng @beanName | Không hỗ trợ | Có thể cấu hình |
| Tùy chỉnh property accessor | Có | Có |
| Cấu hình method resolver | Có, theo cơ chế opt-in | Có, linh hoạt hơn |

Nếu chỉ cần lọc dữ liệu hoặc binding một số thuộc tính, SimpleEvaluationContext giúp thu hẹp khả năng của biểu thức. Nếu cần đầy đủ tính năng SpEL, StandardEvaluationContext có thể phù hợp hơn, nhưng phải kiểm soát chặt root object, accessor, resolver và nguồn của biểu thức.

Việc chọn StandardEvaluationContext chỉ để né một giới hạn của SimpleEvaluationContext sẽ mở rộng đáng kể quyền mà biểu thức có thể sử dụng. Hãy xác định rõ nhu cầu trước khi thay đổi context.

## 10. Giới hạn quyền ghi không đồng nghĩa với sandbox an toàn tuyệt đối

SimpleEvaluationContext giảm phạm vi ngôn ngữ và quyền truy cập, nhưng không bảo đảm biểu thức từ nguồn không đáng tin cậy sẽ an toàn tuyệt đối.

Ngay cả khi chỉ đọc thuộc tính, một getter hoặc phương thức có hình dạng accessor vẫn có thể gây tác dụng phụ. Ví dụ, một phương thức không nhận tham số nhưng xóa file hoặc lấy phần tử khỏi queue có thể trông giống một thuộc tính khi được truy cập qua SpEL.

Vì vậy:

1. Chỉ cung cấp root object và biến thực sự cần thiết.
2. Ưu tiên kiểu dữ liệu chuyên biệt, chỉ phơi bày các thuộc tính đơn giản.
3. Ưu tiên object bất biến khi chỉ cần đọc.
4. Kiểm tra getter và accessor có thể được gọi.
5. Chỉ bật read-write khi có yêu cầu nghiệp vụ rõ ràng.
6. Không xem SimpleEvaluationContext là cơ chế cho phép chạy tùy ý biểu thức do người dùng gửi lên.

Read-only chỉ kiểm soát việc gán thuộc tính. Nó không chứng minh rằng mọi thao tác đọc đều không có tác dụng phụ.

## 11. Ví dụ tổng hợp: chọn chế độ đọc hoặc ghi

~~~java
ExpressionParser parser = new SpelExpressionParser();
Customer customer = new Customer();

// Trường hợp chỉ đọc
EvaluationContext readOnly =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression readName = parser.parseExpression("name");
String currentName =
    readName.getValue(readOnly, customer, String.class);

// Trường hợp cho phép ghi thuộc tính
EvaluationContext readWrite =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

Expression assignName =
    parser.parseExpression("name = 'An'");

String assignedName =
    assignName.getValue(readWrite, customer, String.class);

// Cập nhật biến context từ Java
readWrite.setVariable("operator", "admin");
~~~

Trong ví dụ, context chỉ đọc dùng để lấy tên. Context đọc ghi dùng để đánh giá biểu thức gán thuộc tính. Biến operator được đăng ký trực tiếp bằng Java.

Nếu thay biểu thức gán thuộc tính bằng một biểu thức gán biến như #operator = 'guest', SimpleEvaluationContext vẫn không hỗ trợ thao tác đó. Hãy dùng setVariable từ Java để cập nhật biến.

## 12. Ghi nhớ

SimpleEvaluationContext giới hạn việc gán theo cấu hình và loại thao tác. forReadOnlyDataBinding() cung cấp quyền đọc thuộc tính và tắt assignment trong biểu thức. forReadWriteDataBinding() cho phép đọc ghi thuộc tính qua DataBindingPropertyAccessor. Accessor tùy chỉnh cũng có thể quyết định quyền ghi; builder có thể tắt assignment khi cần.

Gán biến trong biểu thức không được SimpleEvaluationContext hỗ trợ, kể cả khi context cho phép ghi thuộc tính. Tuy nhiên, ứng dụng vẫn có thể đăng ký hoặc cập nhật biến bằng setVariable từ Java. Expression.setValue là một API ghi thuộc tính riêng và cần accessor hỗ trợ ghi.

Hãy chọn quyền đọc hoặc ghi theo nhu cầu thực tế, phân biệt gán thuộc tính với gán biến, và xử lý lỗi đánh giá rõ ràng. SimpleEvaluationContext giúp thu hẹp quyền của SpEL, nhưng vẫn cần kiểm soát những đối tượng và phương thức mà biểu thức có thể truy cập.

## Tài liệu tham khảo

- [Spring Framework Reference — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework Reference — Assignment Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)