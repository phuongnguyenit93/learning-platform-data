# SimpleEvaluationContext như một lựa chọn giới hạn quyền

Spring Expression Language (SpEL) có thể đọc property, gọi method, tham chiếu kiểu, tạo object và truy cập bean tùy theo cấu hình EvaluationContext. Những khả năng này hữu ích cho biểu thức do ứng dụng kiểm soát, nhưng có thể quá rộng khi expression được tạo từ dữ liệu do người dùng cung cấp.

**SimpleEvaluationContext** là một lựa chọn giới hạn hơn StandardEvaluationContext. Nó cho phép ứng dụng chọn cách truy cập property, có thể bật method invocation một cách có chủ đích và cấu hình chuyển đổi kiểu. Context này không cung cấp các khả năng như tham chiếu Java type, gọi constructor và bean reference.

SimpleEvaluationContext giúp giảm bề mặt truy cập của expression, đặc biệt trong các trường hợp data binding hoặc rule đơn giản. Tuy nhiên, nó không phải sandbox hoàn chỉnh: getter hoặc method được cho phép vẫn có thể tốn tài nguyên hay tạo side effect. Ứng dụng vẫn phải kiểm soát root object, dữ liệu đầu vào, quyền nghiệp vụ và chi phí đánh giá.

## 1. Vì sao cần SimpleEvaluationContext?

### 1.1. StandardEvaluationContext có nhiều khả năng

StandardEvaluationContext là context đầy đủ tính năng thường dùng với SpEL. Tùy cấu hình, nó có thể hỗ trợ:

- Đọc và ghi property thông qua PropertyAccessor.
- Gọi method thông qua MethodResolver.
- Phân giải Java type bằng TypeLocator và cú pháp T(...).
- Tạo object bằng constructor expression new.
- Tham chiếu Spring bean thông qua BeanResolver.
- Dùng biến và các dịch vụ chuyển đổi kiểu.
- Đăng ký resolver hoặc accessor tùy chỉnh.

Các tính năng này phù hợp khi expression là một phần của cấu hình tin cậy hoặc khi ứng dụng cần toàn bộ khả năng của SpEL. Nếu expression do người dùng nhập, mỗi khả năng bổ sung có thể mở thêm một con đường truy cập object hoặc hành vi của ứng dụng.

### 1.2. Mục tiêu của SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho các tình huống chỉ cần một tập con SpEL, thường là data binding và đánh giá biểu thức trên object dữ liệu.

Nó cho phép ứng dụng chọn một trong các cách xây dựng context, ví dụ:

- Chỉ đọc property theo cơ chế data binding.
- Đọc và ghi property theo cơ chế data binding.
- Cung cấp PropertyAccessor tùy chỉnh cho mô hình dữ liệu riêng.

Method invocation không được bật mặc định trong các cấu hình builder thông dụng. Nếu thật sự cần gọi method instance, ứng dụng phải bật rõ ràng bằng cấu hình builder tương ứng hoặc cung cấp MethodResolver được kiểm soát.

SimpleEvaluationContext không hỗ trợ các tính năng tham chiếu Java type, constructor và bean reference của StandardEvaluationContext. Vì vậy, expression không thể sử dụng các cú pháp như T(java.lang.Runtime), new java.util.Date() hoặc @someBean theo cách thông thường của context đầy đủ.

### 1.3. Khi nào nên chọn?

SimpleEvaluationContext thường phù hợp khi:

- Biểu thức chỉ cần đọc property của DTO hoặc view object.
- Cần binding dữ liệu vào object với phạm vi property được kiểm soát.
- Cần một rule Boolean đơn giản trên dữ liệu đã chuẩn bị.
- Không cần tạo object bằng constructor expression.
- Không cần tra cứu bean từ ApplicationContext.
- Muốn tránh vô tình cho expression dùng type reference hoặc các khả năng SpEL rộng hơn.

Nếu biểu thức cần truy cập nhiều service, gọi constructor hoặc tham chiếu type, hãy xem lại thiết kế. Có thể chuẩn bị dữ liệu trong Java rồi đưa các giá trị cần thiết vào context giới hạn.

## 2. Tạo SimpleEvaluationContext

### 2.1. Chỉ đọc property

Cách xây dựng phổ biến cho biểu thức chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Builder này cấu hình cơ chế data binding chỉ đọc. Expression có thể đọc property mà accessor được cung cấp hỗ trợ, nhưng không được dùng context này để ghi property.

Ví dụ:

~~~java
public class OrderView {

    private final String status;
    private final BigDecimal total;

    public OrderView(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Đánh giá:

~~~java
ExpressionParser parser = new SpelExpressionParser();

OrderView order = new OrderView(
        "PAID",
        new BigDecimal("125.50")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Boolean eligible = parser
        .parseExpression("status == 'PAID' && total >= 100")
        .getValue(context, order, Boolean.class);
~~~

Overload getValue nhận root object riêng cho lần đánh giá, nên không cần đặt object vào context từ trước. Cách này hữu ích khi tái sử dụng một cấu hình context chỉ đọc cho nhiều object có cùng kiểu dữ liệu.

### 2.2. Đọc và ghi property

Nếu use case cần data binding hai chiều, có thể dùng:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

Ví dụ ghi property:

~~~java
Expression expression =
        parser.parseExpression("status");

expression.setValue(context, orderForm, "REVIEWED");
~~~

Thao tác chỉ thành công nếu property có thể ghi theo accessor và object đích hỗ trợ việc cập nhật. Một property chỉ có getter hoặc thuộc object bất biến không thể được ghi chỉ vì context được tạo theo chế độ read-write.

Chọn read-only khi không cần cập nhật. Chỉ dùng read-write cho luồng binding có mục đích rõ ràng và object đích đã được giới hạn.

### 2.3. Cung cấp PropertyAccessor riêng

Nếu mô hình dữ liệu không phải JavaBean thông thường, có thể cung cấp PropertyAccessor tùy chỉnh:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .build();
~~~

Builder sẽ dùng các accessor được cung cấp để truy cập property. Đây là cách hữu ích khi ứng dụng chỉ muốn expression nhìn thấy một tập property cụ thể của một loại object.

PropertyAccessor nên khai báo đúng target class và chỉ hỗ trợ các property cần thiết. Không tạo accessor tổng quát cho mọi object nếu expression chỉ cần đọc một vài trường.

Khi cần cả nhiều accessor, có thể truyền chúng vào builder theo API của phiên bản Spring đang dùng. Hãy kiểm tra thứ tự và khả năng hỗ trợ target của từng accessor để tránh xung đột.

## 3. Property access là trung tâm của context giới hạn

### 3.1. DataBindingPropertyAccessor

Các builder forReadOnlyDataBinding() và forReadWriteDataBinding() sử dụng cơ chế property access phù hợp cho data binding. Accessor này cho phép đọc hoặc ghi JavaBean property theo chế độ đã chọn và có các giới hạn riêng so với accessor phản chiếu tổng quát.

Ví dụ biểu thức:

~~~java
customer.active
customer.address.city
order.total
~~~

SpEL truy cập property thông qua accessor được context cung cấp. Với nested path, từng bước đều cần property tương ứng có thể truy cập được.

### 3.2. Property không tồn tại

SimpleEvaluationContext không tự biến property sai tên thành null. Nếu expression tham chiếu một property mà accessor không thể giải quyết, evaluation có thể thất bại.

Ví dụ:

~~~java
customer.unknownField
~~~

Nếu customer không có property unknownField hoặc accessor không hỗ trợ nó, biểu thức có thể ném lỗi đánh giá.

Hãy giữ tên property đồng nhất với DTO và kiểm thử expression trên đúng loại object được phép.

### 3.3. Property null và nested path

Nếu một property trung gian null, truy cập sâu hơn có thể thất bại:

~~~java
customer.address.city
~~~

Có thể kiểm tra null trước:

~~~java
customer.address != null && customer.address.city == 'Hanoi'
~~~

Hoặc dùng safe navigation ở phiên bản Spring hỗ trợ:

~~~java
customer.address?.city == 'Hanoi'
~~~

SimpleEvaluationContext không làm cho mọi nested path tự an toàn. Việc xử lý null vẫn thuộc trách nhiệm của expression và mô hình dữ liệu.

### 3.4. Property có thể ghi

Chế độ read-write cho phép ghi qua accessor khi property đích có thể thay đổi. Hãy nhớ rằng việc setValue có thể cập nhật trực tiếp object trong bộ nhớ.

Nếu root object là object dùng chung hoặc được chia sẻ giữa request, một expression ghi có thể làm thay đổi trạng thái mà luồng khác đang sử dụng. Dùng DTO riêng cho binding, validate kết quả rồi mới chuyển dữ liệu hợp lệ sang domain object.

## 4. Method invocation không tự bật

### 4.1. Mặc định không cần method resolver

Một ưu điểm quan trọng của SimpleEvaluationContext là method invocation không được bật mặc định trong builder thông dụng.

Ví dụ expression:

~~~java
isEligible()
~~~

sẽ không tự động có quyền gọi method chỉ vì root object có method đó. Nếu ứng dụng không cấu hình method resolver, lời gọi method không được hỗ trợ và evaluation sẽ thất bại.

Điều này giúp expression chỉ đọc property theo cấu hình mà không vô tình gọi mọi method public trên root object.

### 4.2. Bật instance method có chủ đích

Nếu một use case cần gọi instance method, builder có thể bật khả năng này:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Cấu hình này thêm hỗ trợ gọi instance method thông qua resolver phản chiếu của Spring. Nó không có nghĩa expression được phép gọi static method, constructor hoặc bean reference.

Chỉ bật khi method được cung cấp có hợp đồng rõ ràng, chi phí thấp và không tạo side effect ngoài dự kiến.

### 4.3. Chọn method resolver tùy chỉnh

Trong trường hợp cần chính sách gọi method riêng, builder hỗ trợ cấu hình MethodResolver phù hợp. Resolver tùy chỉnh có thể giới hạn target class, tên method và chữ ký được phép.

Không dùng resolver tổng quát để cho phép gọi mọi method trên mọi object. Nếu chỉ cần một vài hành vi, hãy tạo facade hoặc một object biểu diễn rule với method nhỏ, dễ kiểm thử.

### 4.4. Getter cũng là lời gọi code

Property access thường đi qua getter. Dù expression không dùng cú pháp method call, getter vẫn là Java code và có thể thực hiện công việc.

Ví dụ getter không nên thực hiện truy vấn database hoặc gọi mạng:

~~~java
public List<Order> getOrders() {
    return orderRepository.findAll();
}
~~~

Nếu expression đọc orders trên mỗi lần đánh giá, getter có thể kích hoạt truy vấn. SimpleEvaluationContext không thể tự xác định getter nào thuần hoặc có chi phí thấp.

Hãy dùng DTO/view chứa dữ liệu đã chuẩn bị và giữ getter nhẹ, xác định.

## 5. Những khả năng bị loại khỏi SimpleEvaluationContext

SimpleEvaluationContext không cung cấp đầy đủ khả năng của StandardEvaluationContext. Những nhóm tính năng quan trọng bị loại trừ gồm:

| Khả năng | SimpleEvaluationContext | Ý nghĩa |
|---|---|---|
| Đọc property qua accessor được cấu hình | Có | Phạm vi phụ thuộc accessor |
| Ghi property | Có điều kiện | Chỉ với builder/accessor hỗ trợ ghi |
| Instance method invocation | Không mặc định | Có thể bật rõ ràng |
| Java type reference T(...) | Không | Không dùng để lấy Class tùy ý |
| Constructor expression new | Không | Không tạo object tùy ý bằng constructor |
| Bean reference @beanName | Không | Không tra cứu bean Spring qua BeanResolver |
| TypeLocator đầy đủ | Không | Không cung cấp type lookup như context đầy đủ |
| Custom PropertyAccessor | Có | Phải chủ động cung cấp |
| ConversionService/TypeConverter | Có | Có thể cấu hình chuyển đổi kiểu |

Các giới hạn này giúp thu hẹp ngôn ngữ expression được hỗ trợ. Nếu expression dùng cú pháp bị loại trừ, nó sẽ không được đánh giá thành công như với StandardEvaluationContext.

Không nên cố khắc phục bằng cách chuyển sang StandardEvaluationContext rộng quyền mà chưa xác định chính xác tính năng nào thực sự cần. Hãy cân nhắc thay đổi biểu thức hoặc chuẩn bị dữ liệu trong Java.

## 6. Cấu hình chuyển đổi kiểu

### 6.1. ConversionService

SimpleEvaluationContext có thể dùng ConversionService để chuyển đổi giá trị khi property binding hoặc các thao tác đánh giá cần kiểu đích.

Ví dụ:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

ConversionService cung cấp các converter thông dụng và có thể được mở rộng bằng converter riêng của ứng dụng.

### 6.2. Converter tùy chỉnh

Giả sử ứng dụng có kiểu CustomerCode:

~~~java
public record CustomerCode(String value) {
}
~~~

Đăng ký converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Dùng trong context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Khi gán một giá trị String vào property có kiểu CustomerCode, converter có thể được sử dụng nếu property accessor hỗ trợ thao tác ghi và conversion phù hợp.

Converter phải kiểm tra dữ liệu không hợp lệ. Việc chuyển kiểu thành công không thay thế validation nghiệp vụ.

### 6.3. TypeConverter riêng

Nếu ứng dụng đã có một TypeConverter cụ thể, builder có thể nhận TypeConverter thay vì ConversionService. Chọn một nguồn cấu hình chuyển đổi thống nhất để tránh hành vi khác nhau giữa các context.

Hãy kiểm thử cả trường hợp chuyển đổi thành công và thất bại. canConvert chỉ kiểm tra khả năng chuyển đổi theo kiểu; giá trị runtime vẫn có thể sai định dạng.

## 7. Biến và root object

### 7.1. Truyền root object

Có thể cung cấp root object trực tiếp khi đánh giá:

~~~java
Boolean result = parser
        .parseExpression("active && total >= 100")
        .getValue(context, orderView, Boolean.class);
~~~

Root object nên là DTO hoặc view object nhỏ, chỉ chứa dữ liệu mà expression cần đọc.

### 7.2. Dùng biến context

Có thể đăng ký biến và tham chiếu bằng dấu #:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Expression:

~~~java
total >= #minimumTotal
~~~

Biến giúp tách dữ liệu khỏi source expression. Nếu dữ liệu do người dùng cung cấp, hãy validate kiểu và miền giá trị trước khi đưa vào context.

### 7.3. #root và #this

Trong biểu thức, #root tham chiếu root object của lần đánh giá. #this tham chiếu object hiện tại và có thể thay đổi trong các thao tác như selection hoặc projection.

Ví dụ:

~~~java
orders.?[#this.total >= #root.minimumTotal]
~~~

Nếu root object là view chứa orders và minimumTotal, #this trong predicate là từng order còn #root vẫn là view gốc.

Hãy kiểm thử scope của hai biến đặc biệt khi expression lồng nhiều thao tác collection.

## 8. SimpleEvaluationContext và StandardEvaluationContext

Hai context phục vụ các mức nhu cầu khác nhau:

| Tiêu chí | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Mục tiêu | Tập con SpEL có giới hạn | SpEL đầy đủ tính năng |
| Property access | Chọn accessor theo builder | Có accessor mặc định và khả năng tùy chỉnh |
| Property write | Chọn read-only hoặc read-write | Phụ thuộc accessor |
| Method invocation | Tắt mặc định, bật có chủ đích | Có resolver mặc định |
| Type reference | Không hỗ trợ như context đầy đủ | Hỗ trợ qua TypeLocator |
| Constructor | Không hỗ trợ | Hỗ trợ qua ConstructorResolver |
| Bean reference | Không hỗ trợ | Có thể hỗ trợ qua BeanResolver |
| Mức kiểm soát | Chọn tập tính năng nhỏ | Cần cấu hình cẩn thận các quyền rộng |

Không nên chọn SimpleEvaluationContext chỉ vì tên gọi có chữ “simple”. Hãy dựa trên cú pháp và hành vi mà ứng dụng thực sự cần.

Nếu expression cần một tính năng không có trong SimpleEvaluationContext, trước tiên hãy xem có thể thay thế bằng dữ liệu đã chuẩn bị hoặc method Java được gọi ở tầng application hay không.

## 9. SimpleEvaluationContext không phải sandbox hoàn chỉnh

### 9.1. Getter có thể tốn tài nguyên

Expression có thể đọc property mà getter thực hiện truy vấn hoặc xử lý lớn. Context giới hạn không thể tự đánh giá chi phí của getter.

Dùng DTO chứa dữ liệu đã nạp, tránh getter có I/O và giới hạn kích thước collection trước khi đưa vào context.

### 9.2. Instance method có thể tạo side effect

Nếu bật withInstanceMethods(), expression có thể gọi các method mà resolver cho phép trên object. Một method có thể thay đổi trạng thái, ghi database hoặc gọi dịch vụ bên ngoài.

Chỉ bật instance methods cho object có API nhỏ, rõ ràng. Ưu tiên method thuần, không có side effect và không phụ thuộc dữ liệu bên ngoài.

### 9.3. Không tự giới hạn thời gian hoặc bộ nhớ

SimpleEvaluationContext không đặt giới hạn CPU, heap, độ dài expression hoặc số phần tử collection. Một biểu thức vẫn có thể duyệt collection lớn hoặc kích hoạt getter tốn tài nguyên.

Ứng dụng cần giới hạn riêng:

- Độ dài source expression trước khi parse.
- Kích thước chuỗi và collection đầu vào.
- Độ sâu cấu trúc lồng nhau.
- Số lần đánh giá theo người dùng hoặc tenant.
- Chi phí và thời gian của method được phép gọi.
- Kích thước kết quả trước khi đưa vào bước tiếp theo.

Timeout ở tầng chờ kết quả không tự động dừng được Java method đang chạy. Không dựa vào timeout đơn lẻ để cô lập biểu thức không tin cậy.

### 9.4. Không thay thế authorization

Context giới hạn không xác nhận người dùng có quyền truy cập dữ liệu. Nếu root object chứa thông tin của nhiều tenant hoặc người dùng, expression có thể đọc mọi property mà accessor cho phép.

Hãy giới hạn dữ liệu root theo principal và tenant ở tầng service trước khi tạo context. Authorization vẫn phải được thực hiện ở tầng nghiệp vụ.

### 9.5. Không cấp object có quyền rộng

Không đặt ApplicationContext, BeanFactory, repository tổng quát hoặc service quản trị làm root object. Dù context không hỗ trợ bean reference, object được đưa vào root vẫn có thể công khai property hoặc method.

Chỉ cung cấp một DTO/view có phạm vi nhỏ và các biến cần thiết.

## 10. Ví dụ: đánh giá rule chỉ đọc

Giả sử rule chỉ cần biết trạng thái và tổng tiền:

~~~java
public record OrderRuleView(
        String status,
        BigDecimal total,
        boolean customerActive
) {
}
~~~

Tạo context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

context.setVariable(
        "minimumTotal",
        new BigDecimal("100")
);
~~~

Đánh giá:

~~~java
OrderRuleView order = new OrderRuleView(
        "PAID",
        new BigDecimal("125.50"),
        true
);

ExpressionParser parser = new SpelExpressionParser();

Boolean eligible = parser
        .parseExpression(
                "status == 'PAID' " +
                "&& customerActive " +
                "&& total >= #minimumTotal"
        )
        .getValue(context, order, Boolean.class);
~~~

Expression chỉ đọc ba property và một biến. Nó không cần bean reference, constructor expression hoặc type reference.

Đây là kiểu use case phù hợp với SimpleEvaluationContext: dữ liệu đã được chuẩn bị trong Java, còn SpEL chỉ diễn đạt một điều kiện nhỏ.

## 11. Ví dụ: bật instance method có kiểm soát

Giả sử view object có một predicate thuần:

~~~java
public class OrderRuleView {

    private final BigDecimal total;
    private final String status;

    public OrderRuleView(BigDecimal total, String status) {
        this.total = total;
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public boolean isHighValue() {
        return total.compareTo(new BigDecimal("1000")) >= 0;
    }
}
~~~

Tạo context có instance method:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Expression:

~~~java
isHighValue() && status == 'PAID'
~~~

Đánh giá:

~~~java
Boolean eligible = parser
        .parseExpression("isHighValue() && status == 'PAID'")
        .getValue(context, orderView, Boolean.class);
~~~

Method isHighValue chỉ tính toán từ dữ liệu có sẵn và không thực hiện I/O. Đây là dạng method phù hợp hơn để cho phép expression gọi.

Không nên expose method như sendPayment(), deleteCustomer() hoặc executeQuery() chỉ vì builder có thể bật instance method invocation.

## 12. Ví dụ: read-write binding và validation

Giả sử form có property có thể ghi:

~~~java
public class SearchForm {

    private String keyword;
    private Integer pageSize;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Tạo context read-write:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Gán giá trị:

~~~java
SearchForm form = new SearchForm();

parser.parseExpression("keyword")
        .setValue(context, form, "spring");

parser.parseExpression("pageSize")
        .setValue(context, form, "20");
~~~

Nếu converter hỗ trợ String sang Integer và accessor có thể ghi pageSize, giá trị "20" có thể được chuyển thành Integer trước khi gán.

Sau binding, vẫn cần validate:

- keyword có độ dài phù hợp.
- pageSize nằm trong miền cho phép.
- Các trường bắt buộc có giá trị.
- Không có field ngoài allowlist được cập nhật.

SimpleEvaluationContext kiểm soát tập tính năng SpEL; nó không thay thế validation của form hoặc authorization.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không đọc được property | Chưa cấu hình accessor phù hợp hoặc property không tồn tại | Dùng builder/accessor phù hợp và kiểm tra model |
| Không ghi được property | Context read-only hoặc property không hỗ trợ write | Dùng read-write khi cần và kiểm tra setter |
| Method invocation thất bại | Chưa bật instance methods hoặc chưa có resolver phù hợp | Chỉ bật resolver khi use case cần |
| T(...) không hoạt động | SimpleEvaluationContext không hỗ trợ type reference | Dùng dữ liệu/logic đã chuẩn bị trong Java |
| Constructor expression không hoạt động | Context không hỗ trợ constructor invocation | Tạo object trong Java rồi truyền vào context |
| @beanName không phân giải | SimpleEvaluationContext không cung cấp bean reference | Gọi bean trong Java hoặc thiết kế facade dữ liệu |
| Conversion thất bại | Không có converter hoặc dữ liệu sai định dạng | Cấu hình ConversionService và validate input |
| Nested path bị null | Property trung gian null | Kiểm tra null hoặc chuẩn bị object graph |
| Expression chạy chậm | Getter/method hoặc collection tốn tài nguyên | Dùng view nhỏ, giới hạn dữ liệu và method |
| Vẫn có rủi ro truy cập dữ liệu | Root object chứa quá nhiều thông tin | Thu hẹp dữ liệu và kiểm tra authorization |

Khi một expression thất bại, phân biệt lỗi cú pháp, lỗi property access, lỗi method resolution và lỗi conversion. Không bắt mọi exception rồi trả về false hoặc null vì có thể che giấu lỗi cấu hình.

## 14. Quy trình chọn và cấu hình context

Trước khi triển khai, hãy trả lời các câu hỏi:

1. Expression chỉ đọc property hay cần ghi dữ liệu?
2. Có cần gọi instance method không?
3. Có cần Java type reference, constructor hoặc bean reference không?
4. Root object có chứa đúng dữ liệu tối thiểu không?
5. Có cần converter riêng cho kiểu miền không?
6. Getter và method được phép gọi có thuần, nhẹ và xác định không?
7. Độ dài expression, kích thước dữ liệu và tần suất đánh giá đã được giới hạn chưa?
8. Kết quả có được validate trước khi dùng trong nghiệp vụ không?

Nếu chỉ cần đọc property, bắt đầu bằng forReadOnlyDataBinding(). Nếu cần binding ghi, dùng forReadWriteDataBinding() với object đích có phạm vi nhỏ. Nếu cần accessor riêng, cung cấp PropertyAccessor cụ thể. Chỉ bật instance methods khi có lý do rõ ràng và API được phép gọi đã được kiểm soát.

Nếu cần constructor, type reference hoặc bean reference, hãy xem lại liệu logic đó có thể thực hiện trong Java trước khi đánh giá expression hay không. Chỉ chuyển sang StandardEvaluationContext khi thực sự cần các khả năng đầy đủ và đã xác định được chính sách quyền tương ứng.

## 15. Kiểm thử SimpleEvaluationContext

Nên kiểm thử cả khả năng được phép và cú pháp bị giới hạn:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

OrderRuleView order = new OrderRuleView(
        new BigDecimal("125.50"),
        "PAID"
);

assertEquals(
        "PAID",
        parser.parseExpression("status")
                .getValue(context, order, String.class)
);
~~~

Kiểm thử rằng method invocation không được bật mặc định:

~~~java
assertThrows(
        EvaluationException.class,
        () -> parser.parseExpression("isHighValue()")
                .getValue(context, order)
);
~~~

Sau đó tạo context có instance methods và xác nhận method thuần được gọi:

~~~java
SimpleEvaluationContext methodContext =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("isHighValue()")
                .getValue(methodContext, order, Boolean.class)
);
~~~

Các trường hợp nên kiểm thử thêm:

- Đọc property hợp lệ và property không tồn tại.
- Nested property null.
- Ghi property trong read-write và thất bại trong read-only.
- Chuyển đổi kiểu bằng ConversionService.
- Method invocation khi tắt và khi bật.
- Method không tồn tại hoặc argument không phù hợp.
- Cú pháp type reference, constructor và bean reference bị giới hạn.
- Root object chứa dữ liệu tối thiểu.
- Collection lớn sát ngưỡng và expression dài sát giới hạn.
- Getter/method có lỗi để xác nhận exception được xử lý đúng.

Hãy kiểm thử trên phiên bản Spring thực tế của ứng dụng, vì API builder và chi tiết accessor có thể khác giữa các phiên bản.

## 16. Tổng kết

SimpleEvaluationContext cung cấp một tập con SpEL để ứng dụng kiểm soát property access và các năng lực được bật thêm.

- Dùng forReadOnlyDataBinding() cho expression chỉ đọc.
- Dùng forReadWriteDataBinding() khi cần cập nhật property có thể ghi.
- Dùng forPropertyAccessors(...) khi cần một mô hình truy cập property tùy chỉnh.
- Method invocation không được bật mặc định; withInstanceMethods() có thể bật gọi instance method khi thực sự cần.
- Có thể cấu hình ConversionService hoặc TypeConverter.
- Không hỗ trợ type reference, constructor expression và bean reference như StandardEvaluationContext.
- Không tự giới hạn CPU, bộ nhớ, độ dài expression hoặc quyền nghiệp vụ.
- Getter và method vẫn là code có thể tốn tài nguyên hoặc tạo side effect.

Hãy ưu tiên root object nhỏ, property accessor cụ thể, expression chỉ đọc và dữ liệu đã được xác thực. SimpleEvaluationContext là một lớp giảm quyền hữu ích cho rule và data binding, còn giới hạn tài nguyên, authorization và kiểm soát hành vi vẫn phải được thực hiện ở tầng ứng dụng.