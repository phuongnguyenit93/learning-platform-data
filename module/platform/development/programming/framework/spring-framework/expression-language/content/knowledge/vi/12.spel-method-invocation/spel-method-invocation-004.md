# Varargs và chuyển đổi đối số

Khi SpEL gọi một method Java, biểu thức có thể truyền các đối số trực tiếp, kể cả khi method khai báo tham số biến thiên (varargs). SpEL cũng có thể chuyển đổi giá trị đối số sang kiểu mà method yêu cầu thông qua TypeConverter của EvaluationContext.

Hai khả năng này giúp biểu thức ngắn gọn hơn, nhưng cần hiểu cách method được tìm, cách các đối số được ghép vào mảng varargs và thời điểm chuyển đổi kiểu diễn ra. Nếu không, biểu thức có thể gọi nhầm overload, phát sinh lỗi khi đánh giá hoặc che giấu sự không tương thích giữa các kiểu dữ liệu.

## 1. Cách SpEL gọi method

Một lời gọi method trong SpEL có dạng:

~~~java
order.calculateTotal()
customer.findAddress('HOME')
#service.findById(42)
~~~

Method có thể được gọi trên root object hoặc trên biến được đặt trong EvaluationContext. Với biến, cú pháp bắt đầu bằng dấu **#**.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

BigDecimal total = parser
        .parseExpression("calculateTotal()")
        .getValue(context, BigDecimal.class);
~~~

Khi đánh giá lời gọi, SpEL thực hiện các công việc chính:

1. Xác định target object và tên method.
2. Thu thập các đối số trong biểu thức.
3. Tìm method phù hợp thông qua MethodResolver.
4. Xác định cách chuyển đổi đối số nếu kiểu thực tế khác kiểu tham số.
5. Thực thi method và trả về kết quả.

Trong cấu hình thông thường, StandardEvaluationContext sử dụng cơ chế phản chiếu để phân giải và gọi method. Việc tìm method và việc chuyển đổi đối số là hai trách nhiệm khác nhau: MethodResolver tìm method phù hợp, còn TypeConverter chuyển giá trị sang kiểu tham số khi cần.

Lời gọi method được thực hiện ở giai đoạn evaluate. Một biểu thức có thể parse thành công nhưng vẫn thất bại khi method không tồn tại, không có overload phù hợp hoặc method ném exception.

## 2. Varargs trong Java

### 2.1. Khai báo tham số biến thiên

Trong Java, varargs cho phép một method nhận số lượng đối số thay đổi. Tham số varargs được khai báo bằng dấu ba chấm:

~~~java
public String join(String separator, String... values) {
    return String.join(separator, values);
}
~~~

Khi biên dịch Java, tham số varargs được biểu diễn dưới dạng một mảng. Chữ ký method ở mức bytecode có tham số cuối là String[].

Có thể gọi method từ Java với nhiều cách:

~~~java
join(", ", "java", "spring", "spel");
join(", ", "java");
join(", ");
~~~

Các đối số biến thiên được gom thành mảng String. Khi không truyền đối số varargs nào, method nhận một mảng rỗng.

### 2.2. Gọi varargs method từ SpEL

SpEL hỗ trợ gọi method có tham số varargs. Các đối số bổ sung trong biểu thức được gom vào tham số mảng cuối cùng.

Ví dụ, tạo một formatter:

~~~java
public class TagFormatter {

    public String join(String separator, String... tags) {
        return String.join(separator, tags);
    }
}
~~~

Đăng ký đối tượng trong EvaluationContext:

~~~java
TagFormatter formatter = new TagFormatter();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", formatter);
~~~

Gọi method với nhiều đối số:

~~~java
String result = parser
        .parseExpression(
                "#formatter.join(', ', 'java', 'spring', 'spel')"
        )
        .getValue(context, String.class);
~~~

Kết quả:

~~~text
java, spring, spel
~~~

Trong ví dụ, đối số đầu tiên là separator. Các đối số còn lại được gom vào mảng tags.

Có thể gọi không có phần tử varargs:

~~~java
#formatter.join(', ')
~~~

Hoặc chỉ truyền một phần tử:

~~~java
#formatter.join(', ', 'spring')
~~~

### 2.3. Truyền một mảng đã có

Nếu ứng dụng đã có một mảng, có thể đặt mảng vào context và truyền nó cho method:

~~~java
String[] tags = {"java", "spring", "spel"};

context.setVariable("tags", tags);

String result = parser
        .parseExpression("#formatter.join(', ', #tags)")
        .getValue(context, String.class);
~~~

Đối số cuối là một mảng String đã được tạo trong Java. Cách này hữu ích khi danh sách đối số được chuẩn bị từ dữ liệu runtime thay vì viết trực tiếp trong biểu thức.

Không nhầm một mảng được truyền như một đối số với nhiều đối số rời. Nếu method nhận một tham số varargs, Java và reflection đều biểu diễn phần varargs cuối cùng bằng một mảng. Khi tích hợp với method có overload, cần kiểm tra kiểu thực tế của đối số mảng để bảo đảm method được chọn đúng.

## 3. Varargs với kiểu primitive và kiểu tham chiếu

Varargs có thể dùng cả kiểu primitive và kiểu tham chiếu:

~~~java
public long sum(long... values) {
    long total = 0;
    for (long value : values) {
        total += value;
    }
    return total;
}
~~~

Có thể gọi từ SpEL:

~~~java
#calculator.sum(10, 20, 30)
~~~

Kết quả là 60.

Với kiểu tham chiếu:

~~~java
public String describe(Object... values) {
    return Arrays.toString(values);
}
~~~

SpEL có thể truyền các giá trị thuộc nhiều kiểu khác nhau nếu method và cách chuyển đổi cho phép:

~~~java
#formatter.describe('Spring', 3, true)
~~~

Không nên chọn Object... chỉ để tránh định nghĩa kiểu tham số. Một method có kiểu varargs cụ thể thường giúp phát hiện dữ liệu không hợp lệ sớm hơn và làm rõ hợp đồng của API.

Đối với primitive varargs như long..., phần tử cuối cùng phải chuyển được sang kiểu primitive tương ứng. Nếu một giá trị null được truyền vào vị trí cần primitive, việc chuyển đổi không thể tạo ra một giá trị primitive hợp lệ và lời gọi sẽ thất bại.

## 4. Chuyển đổi đối số bằng TypeConverter

### 4.1. Vì sao cần chuyển đổi?

Giả sử method Java yêu cầu một Long:

~~~java
public Customer findById(Long id) {
    // Tra cứu khách hàng
}
~~~

Trong biểu thức, dữ liệu có thể đến từ chuỗi:

~~~java
#customerService.findById('42')
~~~

Giá trị literal '42' là String, trong khi method yêu cầu Long. SpEL có thể sử dụng TypeConverter của EvaluationContext để chuyển String sang Long nếu converter hỗ trợ.

Đây là chuyển đổi đối số trong lúc method invocation. Nó không làm thay đổi kiểu của giá trị ban đầu trong root object hoặc biến context.

### 4.2. StandardTypeConverter

StandardEvaluationContext mặc định cung cấp TypeConverter dựa trên cơ chế chuyển đổi chuẩn của Spring. Có thể sử dụng cấu hình mặc định cho các chuyển đổi thông dụng:

~~~java
public class CustomerService {

    public String findById(Long id) {
        return "Customer-" + id;
    }
}
~~~

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerService", new CustomerService());

String result = parser
        .parseExpression("#customerService.findById('42')")
        .getValue(context, String.class);
~~~

Nếu chuyển đổi String sang Long được hỗ trợ, method nhận giá trị số 42.

Không nên coi mọi cặp kiểu đều có thể chuyển đổi. Khả năng chuyển đổi phụ thuộc ConversionService và TypeConverter đang cấu hình. Chuỗi rỗng, chuỗi không phải số hoặc kiểu miền không có converter phù hợp có thể gây lỗi khi đánh giá.

### 4.3. Cấu hình ConversionService riêng

Nếu ứng dụng cần quy tắc chuyển đổi tùy chỉnh, hãy đăng ký converter trên ConversionService rồi cung cấp cho StandardTypeConverter.

Ví dụ, kiểu định danh miền:

~~~java
public record CustomerCode(String value) {
}
~~~

Method cần CustomerCode:

~~~java
public class CustomerService {

    public String lookup(CustomerCode code) {
        return "Customer code: " + code.value();
    }
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

Cấu hình EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", new CustomerService());
~~~

Biểu thức có thể truyền String literal:

~~~java
#customerService.lookup('C-1024')
~~~

TypeConverter sử dụng ConversionService đã đăng ký để tạo CustomerCode trước khi gọi method.

Converter nên kiểm tra dữ liệu đầu vào và ném lỗi rõ ràng nếu chuỗi không thể biểu diễn một CustomerCode hợp lệ. Không nên chuyển đổi tùy tiện để lời gọi method chỉ chạy được về mặt kỹ thuật nhưng tạo ra dữ liệu miền sai.

## 5. Chuyển đổi từng phần tử của varargs

Vì tham số varargs được biểu diễn bằng mảng, mỗi phần tử cần tương thích với kiểu phần tử của mảng đó.

Ví dụ method:

~~~java
public long sum(long... values) {
    return Arrays.stream(values).sum();
}
~~~

Biểu thức truyền các literal số:

~~~java
#calculator.sum(10, 20, 30)
~~~

Nếu dữ liệu đầu vào là String và TypeConverter hỗ trợ chuyển sang kiểu số, có thể cấu hình để các argument được chuyển đổi theo kiểu tham số. Ví dụ:

~~~java
#calculator.sum('10', '20', '30')
~~~

Khả năng này phụ thuộc converter và cách method được phân giải. Với dữ liệu quan trọng, nên kiểm thử bằng đúng phiên bản Spring và ConversionService của ứng dụng thay vì giả định mọi phần tử luôn tự chuyển đổi thành công.

Nếu một phần tử không chuyển được, lời gọi method không thể hoàn tất bình thường. Không nên tự bỏ qua phần tử lỗi hoặc thay bằng 0 nếu nghiệp vụ chưa định nghĩa cách xử lý đó.

Với varargs kiểu miền, có thể đăng ký converter cho từng phần tử:

~~~java
public Money total(Money... values) {
    // Tính tổng theo quy tắc tiền tệ của domain
}
~~~

Khi đó, mỗi giá trị cần được chuyển sang Money theo quy tắc được đăng ký và các ràng buộc nghiệp vụ phải được kiểm tra trong method.

## 6. Chuyển đổi đối số và overload resolution

### 6.1. Có nhiều method cùng tên

Một class có thể khai báo nhiều overload:

~~~java
public String format(String value) {
    return "text:" + value;
}

public String format(Long value) {
    return "number:" + value;
}
~~~

Khi SpEL đánh giá:

~~~java
#formatter.format('42')
~~~

SpEL phải tìm method phù hợp với kiểu đối số String. Nếu có thể chuyển đổi đối số sang kiểu tham số của overload khác, khả năng chuyển đổi cũng tham gia vào quá trình phân giải method.

Vì vậy, không nên dựa vào suy đoán đơn giản rằng method có kiểu tham số gần giống literal nhất luôn được chọn trong mọi tình huống. Kết quả còn phụ thuộc các overload đang tồn tại, TypeConverter và resolver được cấu hình.

### 6.2. Overload với varargs

Overload varargs có thể làm việc phân giải phức tạp hơn:

~~~java
public String render(String label, String... values) {
    return label + Arrays.toString(values);
}

public String render(String label, Object... values) {
    return label + Arrays.toString(values);
}
~~~

Khi nhiều method cùng có khả năng nhận đối số, resolver cần chọn method phù hợp nhất. Nếu các ứng viên không thể phân biệt rõ, SpEL có thể báo lỗi method không phù hợp hoặc nhiều method cùng phù hợp.

Để tránh mơ hồ:

- Không khai báo nhiều overload varargs chỉ khác nhau ở kiểu tổng quát nếu không thật sự cần.
- Dùng tên method riêng cho các hành vi khác nhau.
- Truyền đối số có kiểu rõ ràng từ Java khi cần phân biệt overload.
- Đăng ký MethodResolver riêng chỉ khi ứng dụng thực sự cần chính sách phân giải đặc biệt.
- Kiểm thử các trường hợp số lượng đối số bằng 0, 1 và nhiều phần tử.

Một API có method name và kiểu tham số rõ ràng thường giúp biểu thức dễ đọc và ổn định hơn.

## 7. Khác biệt giữa chuyển đổi đối số và chuyển đổi kết quả

TypeConverter có thể được dùng ở nhiều vị trí trong quá trình đánh giá. Cần phân biệt:

1. **Argument conversion:** chuyển các đối số sang kiểu tham số của method trước khi thực thi.
2. **Result conversion:** chuyển kết quả trả về của Expression sang kiểu mà caller yêu cầu.

Ví dụ:

~~~java
String result = parser
        .parseExpression("#service.findById('42')")
        .getValue(context, String.class);
~~~

Ở đây có thể có hai chuyển đổi độc lập:

- String '42' sang Long để gọi findById(Long).
- Kết quả trả về sang String nếu kiểu kết quả thực tế không phải String và TypeConverter hỗ trợ.

Nếu method đã trả về String thì không cần chuyển đổi kết quả.

Có thể lấy kết quả dưới kiểu Object để kiểm tra kiểu runtime:

~~~java
Object result = parser
        .parseExpression("#service.findById('42')")
        .getValue(context);
~~~

Cách này hữu ích khi debug vì nó giúp tách lỗi ở argument conversion khỏi lỗi ở result conversion.

## 8. Những trường hợp chuyển đổi thất bại

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy method | Không có method phù hợp với tên và số đối số | Kiểm tra tên, arity và chữ ký method |
| String không chuyển được sang số | Chuỗi sai định dạng hoặc converter không hỗ trợ | Kiểm tra dữ liệu và ConversionService |
| Không chuyển được kiểu miền | Chưa đăng ký converter | Thêm Converter/GenericConverter phù hợp |
| Null truyền vào primitive | Primitive không nhận null | Dùng wrapper hoặc kiểm tra null trước |
| Nhiều overload cùng phù hợp | Resolver không phân biệt được ứng viên | Làm rõ kiểu đối số hoặc đổi tên method |
| Varargs có phần tử sai kiểu | Một hoặc nhiều phần tử không chuyển được | Kiểm tra từng giá trị và kiểu phần tử |
| Method ném exception | Logic bên trong method thất bại | Xử lý nguyên nhân trong method hoặc tầng Java |
| Kết quả không chuyển được sang kiểu yêu cầu | getValue(context, Target.class) không có converter phù hợp | Lấy Object trước hoặc bổ sung converter |

Lỗi ở các trường hợp này xuất hiện khi đánh giá biểu thức. Parse thành công không bảo đảm rằng method sẽ được tìm thấy hoặc argument sẽ chuyển đổi được.

## 9. Thiết kế method được gọi từ SpEL

Các method được đưa vào biểu thức nên có hợp đồng rõ ràng:

- Ưu tiên method public với tên thể hiện đúng hành vi.
- Giữ số lượng overload vừa phải để tránh mơ hồ.
- Dùng varargs khi số lượng đối số thực sự không cố định.
- Xác định rõ kiểu phần tử varargs và cách xử lý danh sách rỗng.
- Kiểm tra null và dữ liệu không hợp lệ trong method hoặc trước khi gọi.
- Giữ method thuần (pure) khi có thể để biểu thức dễ dự đoán.
- Không dùng method được gọi từ SpEL để thực hiện I/O hoặc thay đổi trạng thái không cần thiết.

Nếu method cần quá nhiều đối số, đó có thể là dấu hiệu nên tạo một command object hoặc request object trong Java thay vì truyền một danh sách varargs dài.

Ví dụ, thay vì:

~~~java
#reportService.create('Q4', 'VI', true, 100, 'FINANCE')
~~~

có thể tạo một object ReportRequest ở Java rồi đặt object đó vào context:

~~~java
#reportService.create(#request)
~~~

Cách này giúp hợp đồng method rõ hơn khi số lượng tham số và quy tắc nghiệp vụ tăng lên.

## 10. Bảo mật khi gọi method từ biểu thức

StandardEvaluationContext hỗ trợ khả năng truy cập method thông qua resolver và reflection. Vì vậy, không nên đánh giá biểu thức do người dùng không tin cậy gửi lên trong context có thể gọi mọi method của các object nhạy cảm.

Một số nguyên tắc:

- Chỉ đưa các object cần thiết vào EvaluationContext.
- Hạn chế method có tác dụng phụ hoặc quyền truy cập dữ liệu nhạy cảm.
- Kiểm soát MethodResolver và MethodExecutor nếu cần chính sách gọi method riêng.
- Không xem TypeConverter là một cơ chế kiểm tra quyền.
- Không cho phép converter thực hiện truy cập hệ thống hoặc thao tác bên ngoài chỉ để chuyển kiểu.
- Giới hạn số lượng đối số và kích thước dữ liệu varargs nếu đầu vào do người dùng kiểm soát.

Chuyển đổi kiểu thành công chỉ cho biết dữ liệu có thể được biểu diễn theo kiểu đích. Nó không chứng minh rằng người gọi có quyền thực hiện method đó hoặc dữ liệu đã hợp lệ về mặt nghiệp vụ.

## 11. Kiểm thử varargs và chuyển đổi

Nên kiểm thử riêng các trường hợp về số lượng đối số, kiểu dữ liệu và converter.

Ví dụ kiểm thử varargs:

~~~java
TagFormatter formatter = new TagFormatter();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", formatter);

assertEquals(
        "java, spring",
        parser.parseExpression(
                "#formatter.join(', ', 'java', 'spring')"
        ).getValue(context, String.class)
);

assertEquals(
        "",
        parser.parseExpression(
                "#formatter.join(', ')"
        ).getValue(context, String.class)
);
~~~

Kiểm thử chuyển đổi String sang Long:

~~~java
CustomerService service = new CustomerService();

context.setVariable("customerService", service);

assertEquals(
        "Customer-42",
        parser.parseExpression(
                "#customerService.findById('42')"
        ).getValue(context, String.class)
);
~~~

Với converter tùy chỉnh, hãy kiểm thử:

- Giá trị hợp lệ có thể chuyển đổi.
- Chuỗi rỗng hoặc null.
- Giá trị sai định dạng.
- Giá trị nằm ngoài miền hợp lệ.
- Method nhận một argument và method nhận nhiều argument varargs.
- Overload có cùng tên.
- Lời gọi với mảng đã được tạo sẵn.

Các kiểm thử này xác nhận cả quy tắc chuyển đổi lẫn hành vi phân giải method trong cấu hình thực tế.

## 12. Tổng kết

SpEL hỗ trợ gọi method Java có tham số varargs và sử dụng TypeConverter để chuyển đối số sang kiểu tham số khi cần.

- Varargs cho phép truyền số lượng đối số biến thiên; phần cuối được gom vào mảng theo chữ ký method.
- TypeConverter và ConversionService quyết định những chuyển đổi kiểu nào được hỗ trợ.
- MethodResolver lựa chọn method phù hợp dựa trên tên, số lượng và kiểu đối số cùng khả năng chuyển đổi.
- Overload varargs có thể gây mơ hồ; hãy thiết kế API rõ ràng và kiểm thử các trường hợp biên.
- Chuyển đổi đối số khác với chuyển đổi kết quả của getValue.
- Lỗi chuyển đổi và lỗi gọi method xảy ra khi evaluate, không phải lúc parse.

Hãy giữ method được gọi từ SpEL nhỏ gọn, có kiểu tham số rõ ràng và ít tác dụng phụ. Khi quy tắc gọi method trở nên phức tạp, hãy chuẩn bị dữ liệu hoặc thực hiện logic trong Java rồi truyền kết quả vào EvaluationContext.## 13. Checklist khi triển khai

Trước khi đưa một biểu thức gọi method vào ứng dụng, hãy xác nhận:

- Method có tên và chữ ký rõ ràng, phù hợp với số lượng đối số.
- Tham số varargs có kiểu phần tử cụ thể và quy tắc xử lý khi không có phần tử.
- Các đối số runtime có thể chuyển sang kiểu tham số bằng TypeConverter đang cấu hình.
- Converter tùy chỉnh đã được đăng ký trên đúng ConversionService được dùng bởi context.
- Overload không tạo ra trường hợp mơ hồ khi đối số có kiểu khác nhau.
- Null và dữ liệu sai định dạng được xử lý theo quy tắc nghiệp vụ.
- Method không thực hiện tác dụng phụ ngoài dự kiến khi biểu thức được đánh giá.
- EvaluationContext chỉ cung cấp các object và method mà biểu thức cần truy cập.

Nếu một biểu thức cần quá nhiều bước chuẩn bị, hãy chuyển phần xử lý đó sang Java. SpEL phù hợp để gọi một API có hợp đồng ổn định, còn việc xác thực dữ liệu, phân quyền và điều phối nghiệp vụ nên được giữ ở nơi có thể kiểm thử và kiểm soát rõ ràng.