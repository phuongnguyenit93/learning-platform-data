# Không dùng new thay cho việc kiểm soát dependency

## Mục tiêu

Spring Expression Language (SpEL) hỗ trợ toán tử **new** để tạo một object bằng cách gọi constructor của class Java. Cú pháp này hữu ích khi biểu thức cần tạo một giá trị hoặc một object nhỏ trong lúc đánh giá. Tuy nhiên, object được tạo bằng new không tự trở thành Spring bean và không được container quản lý vòng đời hay dependency.

Đây là điểm cần phân biệt khi thiết kế ứng dụng Spring: **new là cơ chế tạo object của Java; dependency injection là cơ chế quản lý và cung cấp dependency của Spring**. Không dùng constructor expression để tự tạo service, repository, client hoặc component vốn phải được Spring quản lý.

Sau bài này, bạn có thể:

- Viết constructor expression bằng toán tử new trong SpEL.
- Hiểu cách SpEL phân giải class và constructor.
- Phân biệt object tạo bằng new với Spring-managed bean.
- Nhận biết vì sao tự tạo dependency có thể bỏ qua injection, proxy và lifecycle.
- Dùng constructor injection trong Java và bean reference trong SpEL khi phù hợp.
- Chọn đúng trường hợp dùng new và kiểm thử biểu thức an toàn.

## 1. Constructor invocation trong SpEL

SpEL dùng từ khóa **new** để gọi constructor của một class:

~~~text
new fully.qualified.ClassName(arguments)
~~~

Ví dụ tạo một object Date:

~~~text
new java.util.Date()
~~~

Tạo String:

~~~text
new String('Hello SpEL')
~~~

Tạo một kiểu nghiệp vụ:

~~~text
new com.example.Money(125, 'USD')
~~~

Với class ngoài package java.lang, thông thường cần viết tên class đầy đủ package. SpEL có import prefix mặc định java.lang, vì vậy có thể viết String thay cho java.lang.String.

Constructor expression được phân tích thành một biểu thức SpEL. Khi biểu thức được đánh giá, SpEL tìm class và constructor phù hợp, chuyển đổi đối số nếu cần theo TypeConverter của EvaluationContext, rồi gọi constructor.

Ví dụ đánh giá bằng Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('125.50')");

BigDecimal amount = expression.getValue(context, BigDecimal.class);
~~~

Kết quả là một BigDecimal có giá trị 125.50. Đây là một ví dụ phù hợp vì BigDecimal là kiểu giá trị và constructor chỉ tạo ra giá trị cần dùng trong biểu thức.

## 2. Class name và constructor resolution

Khi gặp new, SpEL cần xác định class được yêu cầu. TypeLocator trong EvaluationContext tham gia phân giải tên class. Sau đó, ConstructorResolver tìm constructor phù hợp với số lượng và kiểu đối số.

Các điểm cần nhớ:

- Dùng fully qualified class name cho class ngoài java.lang.
- Class phải có trên runtime classpath và có thể được class loader mà TypeLocator sử dụng nhìn thấy.
- Constructor phải có thể truy cập theo cơ chế phân giải constructor đang cấu hình; constructor public là lựa chọn thông thường.
- Số lượng và kiểu đối số phải phù hợp với một constructor.
- TypeConverter có thể chuyển đổi một số kiểu đối số, nhưng không nên dựa vào chuyển đổi ngầm nếu hợp đồng dữ liệu không rõ.
- Nếu class có nhiều constructor overload, hãy kiểm thử các kiểu đối số thực tế để xác nhận constructor được chọn.

Ví dụ:

~~~java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Biểu thức:

~~~text
new com.example.Money(125.50, 'USD')
~~~

chỉ hoạt động nếu class thực tế có constructor tương thích với hai đối số mà SpEL phân giải được. Nếu constructor chỉ nhận BigDecimal mà đối số đầu được tạo thành một kiểu số khác, kết quả còn phụ thuộc TypeConverter và quy tắc phân giải constructor. Với kiểu tiền tệ, thường nên truyền hoặc tạo BigDecimal một cách tường minh:

~~~text
new com.example.Money(T(java.math.BigDecimal).valueOf(125.50), 'USD')
~~~

## 3. Object tạo bằng new không phải Spring bean

Một object được tạo bằng constructor expression là một object Java mới. Spring container không tự đăng ký object đó thành bean chỉ vì biểu thức được đánh giá trong ứng dụng Spring.

Ví dụ:

~~~text
new com.example.PaymentService()
~~~

Biểu thức này gọi constructor PaymentService trực tiếp. Nó không yêu cầu ApplicationContext tìm bean PaymentService và không kích hoạt quy trình tạo bean như khi container khởi tạo một component.

Một Spring-managed bean có thể được tạo bởi component scanning, Java configuration, XML configuration hoặc cơ chế đăng ký bean khác. Container giữ quyền quản lý việc khởi tạo, dependency injection, post-processing, proxy và lifecycle.

Vì vậy, hai cách sau có ý nghĩa khác nhau:

~~~text
new com.example.PaymentService()
@paymentService
~~~

- **new com.example.PaymentService()** tạo một instance mới bằng constructor.
- **@paymentService** tham chiếu bean có tên paymentService thông qua BeanResolver của EvaluationContext.

Bean reference chỉ hoạt động khi context được cấu hình BeanResolver phù hợp. Trong ứng dụng Spring, cơ chế tích hợp thường dùng BeanFactoryResolver. Không phải mọi EvaluationContext đều tự động có bean resolution.

Không dùng new để thay thế @beanName hoặc constructor injection khi object cần được container quản lý.

## 4. Vì sao tự tạo dependency làm mất kiểm soát?

Một service hoặc repository thường có dependency và hành vi gắn với cấu hình của ứng dụng. Nếu tự gọi new, những dependency đó không tự được Spring cung cấp.

Ví dụ:

~~~java
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu viết:

~~~text
new com.example.InvoiceService()
~~~

biểu thức không thể tự biết cần lấy InvoiceRepository bean nào. Constructor hiện tại còn yêu cầu một đối số, nên biểu thức không có đối số phù hợp sẽ thất bại. Nếu thêm đối số thủ công, object InvoiceService vẫn là object do biểu thức tạo ra, không tự trở thành bean được quản lý.

Việc tự tạo service có thể gây ra các vấn đề sau:

- **Dependency không được inject:** repository, client, configuration hoặc service phụ thuộc không tự xuất hiện.
- **Lifecycle bị bỏ qua:** container không quản lý callback khởi tạo, callback hủy hoặc các bước post-processing như với bean.
- **Proxy không được áp dụng:** các cơ chế dựa trên proxy như transaction, method security, caching hoặc asynchronous interception có thể không hoạt động trên object tự tạo.
- **Scope không được áp dụng:** object không tuân theo singleton, request, session hoặc custom scope của bean.
- **Cấu hình bị phân tán:** việc tạo object và truyền dependency có thể bị lặp trong nhiều biểu thức.
- **Kiểm thử khó hơn:** khó thay dependency bằng mock hoặc test double thông qua cấu hình container quen thuộc.
- **Trạng thái bị nhân bản:** mỗi lần đánh giá expression có thể tạo một instance mới, thay vì dùng instance được quản lý và cấu hình tập trung.

Ngay cả khi constructor nhận được một bean làm đối số, object mới vẫn không tự trở thành Spring bean. Nó chỉ nhận tham chiếu được truyền vào; container không tự quản lý vòng đời của chính object đó.

## 5. Dùng constructor injection cho dependency

Với dependency của ứng dụng, hãy để Spring tạo object và cung cấp dependency qua constructor injection.

Ví dụ:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }

    public Invoice calculate(InvoiceRequest request) {
        // Nghiệp vụ sử dụng repository và taxCalculator.
        return new Invoice();
    }
}
~~~

Spring container tìm các bean phù hợp với kiểu InvoiceRepository và TaxCalculator, rồi truyền chúng vào constructor khi tạo InvoiceService.

Lợi ích:

- Dependency được khai báo rõ trong constructor.
- Object không được tạo thành công nếu dependency bắt buộc chưa có.
- Container quản lý việc khởi tạo và các bước lifecycle.
- Các bean có thể được thay thế trong test bằng cấu hình test hoặc mock bean.
- Các cơ chế proxy và post-processing có thể áp dụng theo cấu hình Spring.
- Quy tắc tạo dependency được tập trung thay vì lặp trong expression.

Trong SpEL, nếu thực sự cần tham chiếu một bean đã được container quản lý, có thể dùng bean reference với một EvaluationContext có BeanResolver:

~~~text
@invoiceService
~~~

Tuy nhiên, bean reference nên được dùng có chủ đích trong biểu thức cấu hình được kiểm soát. Với logic nghiệp vụ thông thường, gọi service từ Java code thông qua dependency injection thường rõ ràng và dễ kiểm thử hơn.

## 6. Khi nào dùng new là phù hợp?

Constructor expression vẫn hữu ích khi object được tạo chỉ là một giá trị trung gian hoặc một object đơn giản không cần Spring quản lý.

Các trường hợp thường phù hợp:

- Tạo kiểu giá trị bất biến như BigDecimal hoặc một value object nhỏ.
- Tạo DTO đơn giản phục vụ phép tính hoặc biểu thức.
- Tạo một object không có dependency vào bean, không cần proxy và không cần lifecycle của Spring.
- Tạo một giá trị mới từ các đối số đã có trong expression.
- Dùng constructor trong một biểu thức nội bộ, cố định và có thể kiểm soát.

Ví dụ:

~~~text
new java.math.BigDecimal('99.95')
~~~

~~~text
new com.example.Range(10, 20)
~~~

~~~text
new java.lang.String('approved')
~~~

Các ví dụ này tạo giá trị từ đối số cụ thể. Chúng không yêu cầu container quản lý object.

Trước khi dùng new, hãy tự hỏi:

1. Object này có cần repository, service, client hoặc dependency khác không?
2. Object có cần transaction, security, caching hoặc proxy không?
3. Object có cần cấu hình, lifecycle callback hoặc scope của Spring không?
4. Object có cần được chia sẻ và quản lý tập trung không?
5. Việc tạo object mới mỗi lần expression được đánh giá có phù hợp không?

Nếu câu trả lời cho một trong các câu hỏi trên là có, hãy xem xét thiết kế lại để Spring quản lý object hoặc thực hiện logic trong service Java.

## 7. Constructor expression và bean reference trong cùng EvaluationContext

StandardEvaluationContext hỗ trợ constructor resolution và có thể được cấu hình thêm TypeLocator, ConstructorResolver và BeanResolver. Tuy nhiên, việc context hỗ trợ nhiều khả năng không có nghĩa là mọi biểu thức đều nên sử dụng tất cả.

Ví dụ tạo context có bean resolution trong ứng dụng Spring:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(applicationContext));
~~~

Khi đó, biểu thức có thể tham chiếu bean:

~~~text
@invoiceService
~~~

Còn constructor expression vẫn tạo object mới:

~~~text
new com.example.Range(10, 20)
~~~

Hai cú pháp không thay thế nhau. Một bên lấy instance do container quản lý; bên kia gọi constructor để tạo instance mới.

Nếu một biểu thức cần cả value object mới và một bean đã tồn tại, có thể kết hợp chúng khi context được cấu hình và nguồn biểu thức đáng tin cậy. Nhưng nếu biểu thức bắt đầu chứa nhiều lời gọi service hoặc logic nghiệp vụ, nên chuyển phần đó vào Java để dependency và luồng thực thi được thể hiện rõ.

## 8. EvaluationContext và giới hạn constructor

StandardEvaluationContext có phạm vi chức năng rộng và hỗ trợ constructor invocation thông qua ConstructorResolver. Cấu hình mặc định thường sử dụng ReflectiveConstructorResolver.

SimpleEvaluationContext được thiết kế cho các trường hợp data binding có phạm vi giới hạn. Nó không cung cấp constructor references, type references hoặc bean references. Vì vậy, biểu thức dùng new cần một EvaluationContext hỗ trợ constructor resolution, chẳng hạn StandardEvaluationContext với cấu hình phù hợp.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('10.25')");

BigDecimal result = expression.getValue(context, BigDecimal.class);
~~~

Nếu cùng biểu thức được đánh giá trong SimpleEvaluationContext, không nên kỳ vọng constructor invocation sẽ hoạt động.

Khi ứng dụng có factory tạo EvaluationContext, hãy chọn context dựa trên những tính năng thực sự cần thiết. Không mở rộng quyền chỉ để một expression chạy được nếu có thể biểu diễn logic đó trong Java.

## 9. An toàn khi đánh giá constructor expression

Constructor invocation làm tăng khả năng của một biểu thức: nó có thể tạo instance của class mà TypeLocator tìm được và ConstructorResolver cho phép gọi. Nếu biểu thức do người dùng hoặc nguồn không đáng tin cậy cung cấp, điều này có thể tạo ra object ngoài dự kiến hoặc kích hoạt constructor có tác dụng phụ.

Các nguyên tắc kiểm soát:

- Chỉ đánh giá expression từ nguồn đáng tin cậy hoặc đã qua xác thực.
- Không cho người dùng cuối nhập SpEL tùy ý vào một luồng nghiệp vụ thông thường.
- Giới hạn class có thể được phân giải bằng TypeLocator khi thiết kế cho phép.
- Giới hạn constructor resolution và các khả năng khác của EvaluationContext.
- Không để constructor expression gọi class có constructor ghi file, mở kết nối, thay đổi trạng thái hoặc thực hiện I/O không mong muốn.
- Giới hạn độ dài và độ phức tạp của expression được cấu hình.
- Ghi nhận ID và phiên bản expression để truy vết lỗi.
- Ưu tiên tạo object trong Java code đã được kiểm soát khi cần logic khởi tạo phức tạp.

Fully qualified class name giúp xác định class rõ ràng, nhưng không phải biện pháp bảo mật. Một class được viết tên đầy đủ vẫn có thể có constructor không phù hợp để gọi từ expression.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy class | Sai package, class không có trên runtime classpath hoặc TypeLocator không phân giải được | Kiểm tra tên đầy đủ và class loader |
| Không tìm thấy constructor phù hợp | Sai số lượng hoặc kiểu đối số | Kiểm tra chữ ký constructor và kiểu dữ liệu |
| Constructor overload được chọn ngoài dự kiến | Đối số có kiểu mơ hồ hoặc conversion khác dự kiến | Dùng kiểu đối số rõ ràng và viết test |
| Biểu thức hoạt động trong context này nhưng không ở context khác | Context không hỗ trợ constructor invocation | Kiểm tra ConstructorResolver và loại context |
| Tự tạo service thiếu dependency | Constructor yêu cầu dependency do Spring quản lý | Dùng constructor injection hoặc bean reference có kiểm soát |
| Transaction/security/cache không hoạt động | Instance tự tạo không đi qua proxy của Spring | Dùng Spring-managed bean |
| Mỗi lần đánh giá tạo trạng thái mới | Constructor expression được gọi lại khi expression được đánh giá | Đưa object có trạng thái vào container nếu cần chia sẻ |
| Constructor ném exception | Logic khởi tạo hoặc đối số không hợp lệ | Kiểm tra constructor và dữ liệu đầu vào |

Khi chẩn đoán, tách lỗi parse khỏi lỗi evaluate. Cú pháp new có thể parse thành công nhưng class hoặc constructor chỉ được phân giải khi đánh giá. Nếu constructor đã được gọi, exception có thể đến từ chính logic khởi tạo bên trong class.

## 11. Kiểm thử constructor expression

Kiểm thử nên xác nhận class được phân giải, constructor phù hợp được gọi và kết quả có kiểu mong đợi.

Ví dụ với BigDecimal:

~~~java
@Test
void createsValueObjectWithConstructorExpression() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("new java.math.BigDecimal('10.25')");

    BigDecimal result = expression.getValue(context, BigDecimal.class);

    assertEquals(new BigDecimal("10.25"), result);
}
~~~

Nếu dùng class nghiệp vụ, hãy kiểm thử:

- Constructor có đúng số lượng và kiểu đối số.
- Overload được chọn đúng.
- Conversion của đối số phù hợp với hợp đồng.
- Constructor xử lý null và dữ liệu không hợp lệ đúng cách.
- Expression được đánh giá trong cùng loại EvaluationContext như production.
- Việc đánh giá lặp lại có tạo instance mới theo đúng mong đợi hay không.
- Không có tác dụng phụ ngoài ý muốn trong constructor.

Với dependency của Spring, kiểm thử container riêng: xác nhận bean được tạo, dependency được inject và proxy/lifecycle cần thiết hoạt động. Không dùng một test constructor expression để thay cho kiểm thử dependency injection.

## 12. Quy trình quyết định trước khi dùng new

Khi viết một expression cần tạo object:

1. **Xác định vai trò của object.** Đây là value object/DTO trung gian hay một service/component có dependency?
2. **Kiểm tra dependency.** Nếu object cần repository, client hoặc service khác, xác định bean nào phải cung cấp dependency đó.
3. **Kiểm tra lifecycle.** Xác định object có cần proxy, transaction, security, cache, scope hoặc callback của Spring không.
4. **Chọn cơ chế tạo.** Dùng new cho object đơn giản không cần container; dùng constructor injection để Spring tạo dependency.
5. **Giữ expression nhỏ.** Nếu constructor arguments hoặc logic khởi tạo trở nên phức tạp, chuyển sang Java method có tên rõ.
6. **Kiểm tra context.** Đảm bảo EvaluationContext hỗ trợ constructor invocation nếu thực sự dùng new.
7. **Kiểm thử.** Xác nhận constructor, kiểu đối số, kết quả và hành vi khi đánh giá lặp lại.
8. **Kiểm soát nguồn expression.** Không đánh giá constructor expression tùy ý từ nguồn không đáng tin.

## 13. Thực hành tốt

- Dùng new để tạo value object hoặc object trung gian đơn giản.
- Dùng constructor injection cho service, repository, client và component có dependency.
- Không kỳ vọng object tạo bằng new tự trở thành Spring bean.
- Không kỳ vọng object tự tạo nhận AOP proxy, scope hoặc lifecycle callback.
- Dùng @beanName chỉ khi BeanResolver được cấu hình và biểu thức có nguồn đáng tin cậy.
- Viết tên class đầy đủ package khi cần phân giải rõ ràng.
- Kiểm thử constructor overload và kiểu đối số.
- Tránh constructor có side effect trong expression được đánh giá nhiều lần.
- Chuyển logic khởi tạo phức tạp sang Java.
- Giới hạn constructor resolution và TypeLocator khi expression được cấu hình từ bên ngoài.

## 14. Checklist review

Trước khi chấp nhận constructor expression, hãy kiểm tra:

- [ ] Class name và package chính xác.
- [ ] Class có trên runtime classpath.
- [ ] Constructor có thể truy cập và có chữ ký phù hợp.
- [ ] Kiểu và số lượng đối số đã được xác định.
- [ ] Conversion của đối số được kiểm thử.
- [ ] Object được tạo thực sự không cần Spring lifecycle hoặc proxy.
- [ ] Dependency bắt buộc được cung cấp qua constructor injection.
- [ ] Không dùng new để tự tạo service/repository/client cần container quản lý.
- [ ] EvaluationContext hỗ trợ constructor invocation.
- [ ] Nguồn expression và phạm vi class được kiểm soát.
- [ ] Có test cho kết quả, lỗi constructor và đánh giá lặp lại.

## Kết luận

Toán tử new trong SpEL gọi constructor Java và tạo một instance mới khi biểu thức được đánh giá. Nó phù hợp với value object hoặc object trung gian đơn giản. Object đó không tự trở thành Spring bean, không tự nhận dependency injection và không tự đi qua lifecycle hay proxy của container. Với service, repository, client hoặc component cần dependency, hãy để Spring quản lý việc tạo object qua constructor injection; chỉ dùng bean reference trong SpEL khi context và nguồn biểu thức được kiểm soát.