# Expression object và lời gọi getValue trong Spring Expression Language (SpEL)

Trong SpEL, việc đánh giá một biểu thức thường gồm hai giai đoạn: phân tích chuỗi biểu thức để tạo một đối tượng **Expression**, sau đó gọi **getValue()** trên đối tượng đó để lấy kết quả. Tách hai giai đoạn giúp ứng dụng phân tích biểu thức một lần, tái sử dụng kết quả phân tích và cung cấp ngữ cảnh hoặc đối tượng gốc khác nhau cho từng lần đánh giá.

Bài này tập trung vào đối tượng Expression, các dạng gọi getValue(), vai trò của đối tượng gốc (root object) và EvaluationContext.

## 1. Vị trí của Expression trong quy trình SpEL

Ba thành phần thường gặp là:

- **ExpressionParser**: nhận chuỗi SpEL và phân tích cú pháp. Lớp triển khai phổ biến là **SpelExpressionParser**.
- **Expression**: biểu diễn biểu thức đã được phân tích. Đối tượng này cung cấp các phương thức để đánh giá biểu thức, lấy kiểu kết quả hoặc gán giá trị khi biểu thức cho phép ghi.
- **EvaluationContext**: cung cấp môi trường khi đánh giá, chẳng hạn đối tượng gốc, biến, hàm, bộ truy cập thuộc tính, bộ phân giải phương thức và bộ chuyển đổi kiểu.

Luồng cơ bản:

1. Tạo một ExpressionParser.
2. Gọi parseExpression(...) để chuyển chuỗi thành Expression.
3. Gọi getValue(...) trên Expression, truyền root object hoặc EvaluationContext nếu biểu thức cần chúng.
4. Nhận kết quả và chuyển đổi sang kiểu mong muốn nếu cần.

Ví dụ tối giản:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("1 + 2 * 3");
Integer result = expression.getValue(Integer.class);

// result = 7
~~~

parseExpression(...) thực hiện việc phân tích cú pháp; getValue(...) mới thực sự đánh giá biểu thức. Vì vậy, lỗi cú pháp thường xuất hiện ở bước parse, còn lỗi do dữ liệu hoặc thao tác đánh giá thường xuất hiện ở bước getValue.

## 2. Expression là đối tượng biểu diễn biểu thức đã phân tích

Expression là giao diện trong package org.springframework.expression. Nó không phải chuỗi biểu thức ban đầu và cũng không phải parser. Parser tạo ra Expression để ứng dụng có thể đánh giá cùng một biểu thức nhiều lần.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("'Hello ' + 'Spring'");

String message = expression.getValue(String.class);
~~~

Trong ví dụ trên:

- Chuỗi truyền vào parseExpression(...) là cú pháp SpEL.
- Giá trị trả về của parseExpression(...) được lưu trong biến expression.
- getValue(String.class) đánh giá biểu thức và yêu cầu kết quả có kiểu String.
- message nhận giá trị Hello Spring.

Có thể giữ Expression trong một trường hoặc một cấu trúc cấu hình để tái sử dụng. Khi cùng một biểu thức cần chạy trên nhiều đối tượng dữ liệu, ứng dụng có thể dùng lại Expression và truyền root object tương ứng vào từng lần gọi getValue().

Việc parse một lần và đánh giá nhiều lần giúp tránh lặp lại công việc phân tích cú pháp trong các luồng xử lý lặp. Root object và EvaluationContext vẫn có thể thay đổi giữa các lần đánh giá.

## 3. Các dạng gọi getValue() thường dùng

getValue() có nhiều overload để chọn cách cung cấp dữ liệu đầu vào và kiểu kết quả.

| Cách gọi | Ý nghĩa |
|---|---|
| getValue() | Đánh giá bằng ngữ cảnh mặc định, không truyền root object tường minh; trả về Object. |
| getValue(Class<T>) | Đánh giá bằng ngữ cảnh mặc định và yêu cầu kết quả có kiểu T. |
| getValue(Object rootObject) | Đánh giá với root object được truyền vào; trả về Object. |
| getValue(Object rootObject, Class<T>) | Đánh giá với root object và yêu cầu kết quả có kiểu T. |
| getValue(EvaluationContext context) | Đánh giá bằng EvaluationContext đã cấu hình. |
| getValue(EvaluationContext context, Class<T>) | Dùng EvaluationContext và yêu cầu kiểu kết quả T. |
| getValue(EvaluationContext context, Object rootObject, Class<T>) | Chỉ định cả EvaluationContext, root object cho lần gọi và kiểu kết quả T. |

Ví dụ dùng kiểu kết quả:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("10 * 5");

Integer number = expression.getValue(Integer.class);
~~~

Nếu dùng getValue() không tham số, kết quả có kiểu Object và thường cần ép kiểu trước khi sử dụng. Dạng getValue(Class<T>) thể hiện rõ kiểu mà đoạn mã mong đợi, đồng thời cho phép hệ thống chuyển đổi kiểu thông qua TypeConverter của ngữ cảnh khi có bộ chuyển đổi phù hợp.

Không phải biểu thức nào cũng có thể đánh giá mà không có dữ liệu gốc. Biểu thức số học hoặc literal có thể tự đánh giá, nhưng biểu thức tham chiếu thuộc tính như name cần một root object có thuộc tính tương ứng.

## 4. Root object: đối tượng mà biểu thức bắt đầu truy cập

Root object là đối tượng được dùng làm điểm bắt đầu khi SpEL phân giải các thuộc tính và phương thức không có tiền tố biến. Ví dụ, với biểu thức name, SpEL tìm thuộc tính name trên root object.

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }
}
~~~

Đánh giá biểu thức trên một đối tượng Customer:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", 25);

Expression greeting =
        parser.parseExpression("'Xin chào ' + name");

String message = greeting.getValue(customer, String.class);

// message = "Xin chào Lan"
~~~

Trong lần gọi này, customer là root object. Tên thuộc tính name trong biểu thức được phân giải từ đối tượng customer. SpEL có thể truy cập thuộc tính Java thông qua cơ chế property accessor; với JavaBean thông thường, getter công khai là cách khai báo dễ hiểu và phổ biến.

Root object có thể được cung cấp trực tiếp cho getValue(...), hoặc được đặt trong EvaluationContext. Nếu biểu thức chỉ dùng literal hay phép toán độc lập, không cần truyền root object.

## 5. EvaluationContext: môi trường đánh giá biểu thức

EvaluationContext chứa các quy tắc và dữ liệu mà SpEL cần trong lúc đánh giá. Tùy loại biểu thức, context có thể cung cấp:

- Root object dùng cho các tham chiếu thuộc tính và phương thức không có tiền tố.
- Biến được tham chiếu bằng cú pháp #tenBien.
- Hàm được đăng ký trong context.
- PropertyAccessor và MethodResolver để kiểm soát cách truy cập thuộc tính hoặc gọi phương thức.
- TypeConverter và TypeLocator phục vụ chuyển đổi và tra cứu kiểu.
- BeanResolver để phân giải tham chiếu bean theo cú pháp @tenBean.

Ví dụ kết hợp root object và biến:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

Customer customer = new Customer("Lan", 25);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);

Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible = eligibility.getValue(context, Boolean.class);

// eligible = true
~~~

Trong ví dụ:

- customer được đặt làm root object của context.
- minimumAge được đăng ký là biến.
- age là thuộc tính của root object.
- #minimumAge là biến trong EvaluationContext.
- getValue(context, Boolean.class) đánh giá biểu thức trong context và yêu cầu kết quả Boolean.

Có thể tạo EvaluationContext không chứa root object rồi truyền root object cho riêng lần gọi:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimumAge", 18);

Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible =
        eligibility.getValue(context, customer, Boolean.class);
~~~

Cách này hữu ích khi muốn giữ phần cấu hình đánh giá, chẳng hạn các biến hoặc bộ chuyển đổi, riêng với dữ liệu của từng lần đánh giá.

### 5.1. StandardEvaluationContext

StandardEvaluationContext cung cấp bộ tính năng đánh giá đầy đủ hơn. Nó phù hợp khi biểu thức cần truy cập thuộc tính, gọi phương thức hoặc sử dụng các khả năng nâng cao của SpEL. Ứng dụng có thể đăng ký biến, hàm, property accessor, method resolver, type converter và bean resolver.

Ví dụ, khi tích hợp với Spring BeanFactory, có thể cấu hình BeanFactoryResolver làm BeanResolver:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Sau khi có BeanResolver, biểu thức có thể tham chiếu bean bằng cú pháp @pricingService. Nếu không cấu hình bean resolver phù hợp, tham chiếu bean không tự động hoạt động chỉ vì ứng dụng đang dùng Spring.

### 5.2. SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho các tình huống cần giới hạn khả năng của SpEL, đặc biệt là data binding. Ứng dụng chọn rõ những khả năng cần cho phép thay vì mặc định mở toàn bộ tính năng như StandardEvaluationContext.

Ví dụ dùng truy cập thuộc tính chỉ đọc:

~~~java
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

String name = parser.parseExpression("name")
        .getValue(context, customer, String.class);
~~~

SimpleEvaluationContext phù hợp khi chỉ cần đọc dữ liệu từ một đối tượng. Nếu biểu thức cần gọi phương thức hoặc tính năng nâng cao khác, cần chọn cấu hình builder tương ứng và cân nhắc phạm vi quyền truy cập.

## 6. Yêu cầu kiểu kết quả và chuyển đổi kiểu

Các overload nhận Class<T> cho phép khai báo kiểu mà ứng dụng mong đợi:

~~~java
Expression expression = parser.parseExpression("1 + 2");
Integer result = expression.getValue(Integer.class);
~~~

SpEL dùng TypeConverter gắn với EvaluationContext để chuyển kết quả sang kiểu được yêu cầu khi có quy tắc chuyển đổi phù hợp. Vì thế, kiểu yêu cầu không chỉ là thao tác ép kiểu Java thông thường. Nếu không thể chuyển đổi, quá trình đánh giá có thể phát sinh EvaluationException.

Nên chọn kiểu kết quả cụ thể khi ứng dụng biết mình cần Boolean, String, Integer hoặc một kiểu miền nghiệp vụ. Cách này làm rõ hợp đồng giữa biểu thức và mã Java, đồng thời tránh ép kiểu Object ở nhiều nơi.

Nếu biểu thức trả về một kiểu phức tạp, hãy yêu cầu đúng kiểu đó hoặc nhận Object rồi kiểm tra kiểu một cách có chủ đích. Không nên giả định mọi biểu thức đều trả về một kiểu cố định nếu nội dung biểu thức có thể thay đổi.

## 7. Lỗi ở bước parse và bước getValue

Hai giai đoạn có nhóm lỗi khác nhau:

- **ParseException**: biểu thức không hợp lệ về cú pháp hoặc parser không thể phân tích chuỗi đầu vào.
- **EvaluationException**: biểu thức đã được phân tích nhưng không thể đánh giá trong context hiện tại. Ví dụ: thuộc tính không tồn tại, phương thức không phù hợp, biến chưa được đăng ký hoặc không chuyển đổi được kiểu kết quả.

Ví dụ, biểu thức name có thể parse thành công nhưng vẫn thất bại khi getValue() nếu root object không có thuộc tính name hoặc context không có cơ chế truy cập phù hợp.

~~~java
try {
    Expression expression = parser.parseExpression("age >= #minimumAge");
    Boolean result = expression.getValue(context, Boolean.class);
} catch (ParseException ex) {
    // Xử lý lỗi cú pháp của biểu thức.
} catch (EvaluationException ex) {
    // Xử lý lỗi trong lúc đánh giá biểu thức.
}
~~~

Khi chẩn đoán lỗi, hãy xác định lỗi xảy ra ở parseExpression(...) hay getValue(...). Sau đó kiểm tra chuỗi biểu thức, root object, biến trong context, khả năng truy cập thuộc tính/phương thức và kiểu kết quả được yêu cầu.

## 8. Lưu ý khi thiết kế và sử dụng

1. **Parse một lần, đánh giá nhiều lần:** giữ lại Expression nếu cùng một biểu thức được dùng lặp lại. Không cần tạo parser và parse lại chuỗi trong mỗi lần xử lý nếu biểu thức không thay đổi.
2. **Chọn đúng root object:** các tên thuộc tính không có tiền tố được phân giải từ root object hiện hành. Hãy truyền root object hoặc đặt nó trong EvaluationContext.
3. **Phân biệt thuộc tính và biến:** name thường là thuộc tính trên root object; #name là biến được đăng ký trong EvaluationContext.
4. **Dùng kiểu kết quả rõ ràng:** ưu tiên getValue(Class<T>) hoặc overload tương ứng khi biết kiểu kết quả mong muốn.
5. **Chọn context theo phạm vi tính năng:** dùng StandardEvaluationContext khi cần các khả năng đầy đủ; dùng SimpleEvaluationContext và cấu hình giới hạn khi chỉ cần truy cập dữ liệu.
6. **Không đánh giá tùy tiện biểu thức không đáng tin cậy:** StandardEvaluationContext có thể cho phép truy cập thuộc tính và gọi phương thức bằng cơ chế phản chiếu. SpEL còn có các cú pháp nâng cao như tham chiếu kiểu, tạo đối tượng và tham chiếu bean khi môi trường hỗ trợ. Nếu người dùng có thể tự nhập biểu thức, hãy giới hạn tính năng, dữ liệu và đối tượng được phép truy cập; không xem chuỗi SpEL là dữ liệu vô hại.
7. **Tách lỗi cú pháp khỏi lỗi dữ liệu:** parse trước để phát hiện cú pháp sai, sau đó xử lý EvaluationException tại ranh giới đánh giá.

## 9. Ghi nhớ

- parseExpression(String) biến chuỗi SpEL thành một đối tượng Expression.
- Expression đại diện cho biểu thức đã phân tích và cung cấp getValue(...) để đánh giá.
- getValue() trả về Object; các overload có Class<T> thể hiện kiểu kết quả mong muốn.
- Root object là điểm bắt đầu để phân giải thuộc tính và phương thức.
- EvaluationContext cung cấp root object, biến, hàm, bộ truy cập, bộ phân giải và chuyển đổi kiểu.
- StandardEvaluationContext hỗ trợ nhiều tính năng; SimpleEvaluationContext giúp giới hạn bề mặt đánh giá.
- Có thể tái sử dụng Expression với dữ liệu hoặc context khác nhau, nhưng cần kiểm soát quyền truy cập khi biểu thức đến từ nguồn không đáng tin cậy.
