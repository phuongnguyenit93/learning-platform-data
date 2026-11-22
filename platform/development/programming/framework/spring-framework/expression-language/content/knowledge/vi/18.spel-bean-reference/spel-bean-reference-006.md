# Truy cập property của bean Spring

## 1. Bean reference trong SpEL là gì?

Spring Expression Language (SpEL) có thể truy cập object được quản lý bởi Spring IoC container thông qua **bean reference**. Cú pháp dùng ký hiệu @ đứng trước tên bean:

    @beanName

Sau khi lấy được bean, biểu thức có thể đọc property, truy cập property lồng nhau hoặc gọi method trên bean đó.

Ví dụ:

    @pricingSettings.defaultCurrency

Biểu thức trên yêu cầu SpEL tìm bean có tên pricingSettings, sau đó đọc property defaultCurrency của bean.

Đây là hai bước riêng:

1. BeanResolver tìm bean trong Spring BeanFactory.
2. PropertyAccessor truy cập property trên object được trả về.

Vì vậy, bean reference và property access phối hợp với nhau nhưng không phải cùng một cơ chế.

## 2. Phân biệt bean reference, variable và root object

SpEL có nhiều cách để xác định object bắt đầu cho một đường dẫn:

| Cách viết | Ý nghĩa |
| --- | --- |
| customer.name | Đọc property name từ root object |
| #customer.name | Đọc variable customer trong EvaluationContext rồi lấy name |
| @customerService.name | Tìm bean tên customerService trong Spring container rồi đọc name |

Ba cách có thể trỏ đến các object cùng kiểu, nhưng nguồn cung cấp object khác nhau.

Ví dụ root object:

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

    Expression expression =
        parser.parseExpression("name");

Ví dụ variable:

    context.setVariable("customer", customer);

    Expression expression =
        parser.parseExpression("#customer.name");

Ví dụ bean reference:

    Expression expression =
        parser.parseExpression("@customerService.serviceName");

Không nên dùng @ chỉ vì muốn truy cập một object. Chỉ dùng @ khi object cần lấy là một bean được đăng ký trong BeanFactory. Nếu object được truyền vào theo từng lần đánh giá, root object hoặc variable thường phù hợp hơn.

## 3. Cú pháp truy cập bean và property

Cú pháp cơ bản:

    @beanName.propertyName

Ví dụ:

    @applicationSettings.applicationName
    @applicationSettings.defaultLocale
    @featureFlags.checkoutEnabled

SpEL tìm bean theo tên, sau đó dùng cơ chế property access để đọc giá trị tương ứng.

Với JavaBean thông thường, property được cung cấp qua getter:

    public class ApplicationSettings {
        private String applicationName;
        private String defaultLocale;

        public String getApplicationName() {
            return applicationName;
        }

        public String getDefaultLocale() {
            return defaultLocale;
        }
    }

Khi expression đọc:

    @applicationSettings.applicationName

SpEL sử dụng property accessor để lấy giá trị từ bean. Trong trường hợp JavaBean chuẩn, accessor nhận diện getter getApplicationName() tương ứng với property applicationName.

Property có thể là String, số, boolean, enum, collection hoặc một object khác. Kiểu kết quả của expression phụ thuộc vào giá trị thực tế mà getter trả về.

## 4. Ví dụ đầy đủ với Spring bean

Giả sử ứng dụng có bean cấu hình:

    @Component("applicationSettings")
    public class ApplicationSettings {
        public String getApplicationName() {
            return "Order Service";
        }

        public String getDefaultCurrency() {
            return "VND";
        }
    }

Có thể tham chiếu bean từ một biểu thức SpEL được Spring xử lý:

    @Value("#{ @applicationSettings.applicationName }")
    private String applicationName;

    @Value("#{ @applicationSettings.defaultCurrency }")
    private String currency;

Spring xử lý biểu thức trong quá trình tạo bean và gán kết quả vào các field tương ứng.

Giá trị nhận được:

    applicationName = "Order Service"
    currency = "VND"

Dấu @ bên trong biểu thức là cú pháp bean reference của SpEL. Nó không phải annotation Java độc lập. Annotation @Value chỉ là một điểm tích hợp yêu cầu Spring đánh giá expression.

## 5. Truy cập property lồng nhau

Bean có thể chứa các object khác. SpEL cho phép truy cập nhiều cấp bằng dấu chấm.

Ví dụ:

    @shopSettings.checkout.currency.code

Đường dẫn được xử lý theo thứ tự:

1. Tìm bean shopSettings.
2. Đọc property checkout.
3. Từ object checkout, đọc property currency.
4. Từ object currency, đọc property code.

Một object model đơn giản:

    public class ShopSettings {
        private CheckoutSettings checkout;

        public CheckoutSettings getCheckout() {
            return checkout;
        }
    }

    public class CheckoutSettings {
        private CurrencySettings currency;

        public CurrencySettings getCurrency() {
            return currency;
        }
    }

    public class CurrencySettings {
        private String code;

        public String getCode() {
            return code;
        }
    }

Expression:

    @shopSettings.checkout.currency.code

có thể trả về VND nếu các object trung gian tồn tại và code có giá trị VND.

Mỗi bước truy cập property phụ thuộc vào object trả về từ bước trước. Nếu một object trung gian null, đường dẫn thông thường có thể phát sinh evaluation error.

## 6. Xử lý property trung gian có thể null

Nếu property lồng nhau có thể null, hãy dùng safe navigation ở đúng bước có receiver có thể null.

Ví dụ:

    @shopSettings.checkout?.currency?.code

Nếu checkout là null, thao tác truy cập currency trả về null. Nếu currency là null, thao tác truy cập code tiếp theo cũng trả về null.

Có thể kết hợp Elvis để chọn giá trị mặc định:

    @shopSettings.checkout?.currency?.code ?: 'VND'

Nếu code là null hoặc chuỗi rỗng, Elvis trả về VND. Nếu code có giá trị, kết quả đó được giữ nguyên.

Cần nhớ safe navigation bảo vệ thao tác ngay sau nó. Không nên chỉ đặt một dấu ?. ở đầu đường dẫn rồi giả định mọi property phía sau đều an toàn.

## 7. Bean name có ký tự đặc biệt

Tên bean đơn giản có thể tham chiếu trực tiếp:

    @pricingService

Nếu tên bean chứa dấu chấm hoặc ký tự đặc biệt, hãy đặt tên bean trong dấu nháy đơn:

    @'order.service'.baseUrl

Ví dụ:

    @'billing.gateway'.timeout

Dấu nháy đơn giúp parser nhận diện toàn bộ nội dung bên trong là tên bean, thay vì hiểu dấu chấm như một phần của đường dẫn property.

Khi có thể, nên đặt tên bean theo quy ước đơn giản và ổn định để expression dễ đọc. Nếu phải tham chiếu bean có tên đặc biệt, hãy dùng dạng quoted bean name.

## 8. Truy cập bean trong Java code với BeanResolver

Khi dùng SpEL trong một điểm tích hợp Spring như @Value, Spring cấu hình cơ chế phân giải bean cho expression.

Nhưng nếu tự tạo parser và StandardEvaluationContext trong Java, việc tạo SpelExpressionParser không tự động kết nối nó với ApplicationContext.

Cần đăng ký BeanResolver:

    ApplicationContext applicationContext = ...;

    ExpressionParser parser =
        new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    String currency = parser
        .parseExpression("@applicationSettings.defaultCurrency")
        .getValue(context, String.class);

BeanFactoryResolver là implementation chuẩn của BeanResolver. Nó sử dụng BeanFactory được truyền vào để tìm bean theo tên.

Các import chính:

    import org.springframework.context.ApplicationContext;
    import org.springframework.context.expression.BeanFactoryResolver;
    import org.springframework.expression.ExpressionParser;
    import org.springframework.expression.spel.standard.SpelExpressionParser;
    import org.springframework.expression.spel.support.StandardEvaluationContext;

Nếu context chưa đăng ký BeanResolver, expression có thể parse thành công nhưng thất bại khi evaluation với lỗi cho biết chưa có bean resolver.

Đây là lỗi cấu hình EvaluationContext, không phải lỗi cú pháp @beanName.

## 9. Gọi method trên bean

Sau khi tham chiếu bean, SpEL có thể gọi method trên bean đó.

Ví dụ:

    @pricingService.calculateTotal(#order)

Hoặc:

    @customerService.findById(#customerId)

Trong đó:

- @pricingService hoặc @customerService lấy bean từ BeanResolver.
- Tên method xác định thao tác cần gọi.
- Các đối số có thể là literal, variable hoặc expression khác.

Ví dụ trong Java:

    context.setVariable("amount", 1_000_000);

    Expression expression =
        parser.parseExpression(
            "@pricingService.calculateTax(#amount)"
        );

    BigDecimal tax =
        expression.getValue(context, BigDecimal.class);

Method được tìm và gọi thông qua cơ chế MethodResolver của EvaluationContext. Method phải truy cập được và có tham số tương thích với các giá trị truyền vào.

Không nên dùng method call thay cho property access khi chỉ cần đọc một giá trị đơn giản. Dùng:

    @applicationSettings.applicationName

thay vì gọi một method getter tường minh nếu mục tiêu chỉ là đọc JavaBean property.

## 10. Bean reference và FactoryBean

Spring có khái niệm FactoryBean: một bean đặc biệt dùng để tạo hoặc cung cấp một object khác.

Khi tham chiếu:

    @someFactoryBean

SpEL lấy object do FactoryBean cung cấp thông qua BeanFactory.

Nếu cần lấy chính FactoryBean thay vì object do nó tạo ra, thêm ký hiệu & trước tên bean:

    &someFactoryBean

Ví dụ:

    @myClientFactory

lấy object do factory cung cấp.

    &myClientFactory

lấy chính factory bean.

Cú pháp này hữu ích khi cần kiểm tra hoặc thao tác với FactoryBean. Với bean thông thường không triển khai FactoryBean, không cần dùng tiền tố &.

## 11. Bean scope và thời điểm truy cập

Bean reference được giải quyết khi expression được đánh giá. BeanFactory chịu trách nhiệm trả về bean theo cấu hình scope của bean đó.

Ví dụ:

- Singleton: các lần lookup thông thường trả về cùng instance singleton.
- Prototype: mỗi lần lookup có thể tạo instance mới theo quy tắc prototype.
- Request hoặc session scope: instance phụ thuộc scope hiện hành và yêu cầu scope đã được kích hoạt hợp lệ.
- Bean được bọc bằng proxy: expression nhận object mà BeanFactory trả về, thường là proxy nếu bean được cấu hình như vậy.

Điều này có nghĩa expression không tự quản lý vòng đời bean. Nó chỉ yêu cầu BeanResolver tìm bean theo tên tại thời điểm evaluation.

Nếu expression được giữ lại và đánh giá nhiều lần, bean reference vẫn được giải quyết theo BeanResolver và BeanFactory tương ứng của context. Không nên giả định object được giữ cố định chỉ vì expression đã được parse trước đó.

## 12. Sử dụng bean reference trong annotation Spring

SpEL bean reference thường xuất hiện trong các annotation có hỗ trợ expression.

Ví dụ:

    @Value("#{ @applicationSettings.defaultCurrency }")
    private String currency;

Một ví dụ khác:

    @Value("#{ @featureFlags.checkoutEnabled }")
    private boolean checkoutEnabled;

Có thể kết hợp bean reference với variable hoặc root object nếu điểm tích hợp cung cấp chúng:

    @Value("#{ @pricingService.calculate(#root.amount) }")
    private BigDecimal total;

Cú pháp và dữ liệu root/variable cụ thể phụ thuộc vào annotation hoặc thành phần Spring đang xử lý expression. Không phải mọi annotation có dấu # hoặc @ đều dùng cùng một EvaluationContext.

Khi biểu thức chạy trong @Value, Spring bean expression resolver tích hợp với BeanFactory. Khi tự parse trong Java, phải cấu hình BeanResolver như phần trước.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| No bean resolver registered | EvaluationContext chưa có BeanResolver | Đăng ký BeanFactoryResolver hoặc resolver phù hợp |
| No bean named ... | Tên bean sai hoặc bean không tồn tại trong BeanFactory | Kiểm tra bean name và cấu hình component/bean |
| Property cannot be read | Getter hoặc PropertyAccessor không hỗ trợ property | Kiểm tra tên property, getter và accessor |
| NullPointerException ở property lồng nhau | Một object trung gian null | Dùng safe navigation tại từng bước có thể null |
| Method cannot be found | Tên method hoặc tham số không phù hợp | Kiểm tra chữ ký method và MethodResolver |
| Bean name có dấu chấm bị parse sai | Tên bean chưa được quote | Dùng @'order.service' |
| Lấy nhầm FactoryBean | Cần factory nhưng expression lấy product hoặc ngược lại | Dùng & trước tên khi cần FactoryBean |

Hãy tách quá trình debug thành hai câu hỏi:

1. BeanResolver có tìm được đúng bean không?
2. Sau khi lấy bean, PropertyAccessor hoặc MethodResolver có thực hiện được thao tác tiếp theo không?

Việc phân tách hai bước giúp xác định lỗi nằm ở lookup bean hay ở thao tác trên object.

## 14. Giới hạn quyền truy cập và bảo mật

Bean reference cho phép expression tiếp cận object do ứng dụng quản lý. Tùy các accessor và resolver được cấu hình, expression có thể đọc property hoặc gọi method trên bean đó.

Vì vậy:

- Không đánh giá expression tùy ý do người dùng không tin cậy cung cấp trong context có quyền truy cập toàn bộ bean.
- Chỉ đăng ký hoặc cho phép các bean mà biểu thức thực sự cần.
- Tránh đưa service có side effect hoặc quyền quản trị rộng vào context của expression không tin cậy.
- Giới hạn method và property access theo mục tiêu nghiệp vụ.
- Kiểm tra nguồn expression trước khi đưa vào các điểm đánh giá.

SimpleEvaluationContext được thiết kế cho tập tính năng giới hạn và không hỗ trợ bean references. Nếu nghiệp vụ yêu cầu @beanName, cần một EvaluationContext có BeanResolver phù hợp, thường là StandardEvaluationContext.

Việc dùng StandardEvaluationContext không tự động khiến expression an toàn. Quyền truy cập thực tế phụ thuộc vào object và resolver được cấp.

## 15. Những điểm cần nhớ

- Bean reference dùng cú pháp @beanName.
- Sau bean reference có thể đọc property, property lồng nhau hoặc gọi method.
- BeanResolver chịu trách nhiệm tìm bean; PropertyAccessor chịu trách nhiệm đọc property.
- StandardEvaluationContext tự tạo không tự kết nối với Spring container.
- Dùng BeanFactoryResolver để nối EvaluationContext với BeanFactory.
- Trong @Value và các điểm tích hợp Spring, Spring cấu hình cơ chế bean resolution cho expression.
- Bean name có dấu chấm hoặc ký tự đặc biệt cần được đặt trong dấu nháy đơn.
- Dùng &beanName khi cần lấy chính FactoryBean thay vì object do factory cung cấp.
- Safe navigation cần đặt ở từng bước có thể nhận receiver null.
- Bean scope và proxy vẫn do Spring container quản lý.
- Không đánh giá expression không tin cậy với quyền truy cập bean rộng.

Khi viết SpEL truy cập bean, hãy xác định rõ tên bean, property cần đọc, các object trung gian và EvaluationContext đang được dùng. Phân biệt lookup bean với property access giúp expression dễ debug, dễ bảo trì và kiểm soát quyền truy cập tốt hơn.

## Tài liệu tham khảo

- Spring Framework Reference — Bean References: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html
- Spring Framework Reference — Understanding EvaluationContext: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — BeanFactoryResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html
- Spring Framework Javadoc — BeanResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html
