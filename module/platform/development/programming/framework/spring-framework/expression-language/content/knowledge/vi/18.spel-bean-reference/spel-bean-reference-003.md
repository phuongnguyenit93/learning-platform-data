# BeanFactoryResolver và cơ chế phân giải bean

Trong Spring Expression Language (SpEL), cú pháp **@beanName** cho phép một biểu thức tham chiếu đến bean trong Spring container. Nhờ đó, expression có thể gọi method hoặc đọc property của một service, policy object hay bean cấu hình mà không cần đưa bean đó thành biến thủ công.

Cú pháp này hoạt động thông qua **BeanResolver** được gắn vào **EvaluationContext**. Spring cung cấp implementation **BeanFactoryResolver**, dùng một BeanFactory để tìm bean theo tên. Khi SpEL gặp một bean reference, resolver nhận tên bean và phân giải nó thành object thực tế để expression tiếp tục đánh giá.

Điểm cần nhớ: dấu @ không tự tìm bean trong toàn bộ ứng dụng. EvaluationContext phải được cấu hình với resolver phù hợp, hoặc expression phải được đánh giá trong một integration point của Spring đã thiết lập resolver đó.

## 1. Bean reference trong SpEL

Cú pháp cơ bản:

~~~text
@beanName
~~~

Ví dụ gọi một method của bean:

~~~text
@discountPolicy.calculate(#order)
~~~

Đọc property của bean:

~~~text
@appSettings.region
~~~

Truy cập sâu hơn vào object mà bean trả về:

~~~text
@appSettings.database.connectionTimeout
~~~

Bean reference thường được dùng khi expression cần gọi một quy tắc được đóng gói trong Spring bean. Ví dụ, thay vì viết toàn bộ logic phân quyền hoặc tính giá trong một chuỗi expression, có thể gọi một method có tên rõ ràng trên bean chuyên trách.

~~~java
@Component("discountPolicy")
public class DiscountPolicy {

    public BigDecimal calculate(Order order) {
        // Quy tắc tính chiết khấu của ứng dụng
        return order.getSubtotal().multiply(new BigDecimal("0.05"));
    }
}
~~~

Trong một evaluation context có bean resolver:

~~~text
@discountPolicy.calculate(#order)
~~~

SpEL tìm bean tên discountPolicy, gọi calculate() với biến order và trả về kết quả của method.

Tên sau dấu @ là **bean name** được Spring container quản lý. Với bean khai báo bằng @Component, tên mặc định thường là tên class viết thường ở ký tự đầu; tên có thể được chỉ định tường minh trong annotation hoặc cấu hình bean.

## 2. Phân biệt bean reference, variable và root object

Ba cách truy cập này có ý nghĩa khác nhau:

| Cú pháp | Nguồn dữ liệu | Cách cung cấp |
| --- | --- | --- |
| **#order** | Variable trong EvaluationContext | Đăng ký bằng setVariable() hoặc được integration point cung cấp |
| **@orderService** | Bean trong Spring container | BeanResolver tìm bean theo tên |
| **order** | Property của root object hiện tại | Truyền root object vào getValue() hoặc được context thiết lập |

Ví dụ:

~~~java
context.setVariable("request", request);
~~~

Expression:

~~~text
#request.customerId
~~~

Ở đây request là biến do người tạo context đăng ký.

Nếu ứng dụng có bean tên customerService, expression:

~~~text
@customerService.find(#request.customerId)
~~~

tham chiếu bean do container quản lý rồi gọi method trên bean đó.

Không thể thay @customerService bằng #customerService nếu chưa đăng ký một variable cùng tên. Ngược lại, một bean có tên customerService không tự động xuất hiện dưới dạng variable #customerService.

## 3. BeanResolver là gì?

**BeanResolver** là SPI của Spring Expression cung cấp khả năng phân giải bean reference trong expression.

Interface này nhận EvaluationContext và tên bean cần tìm, rồi trả về object tương ứng. SpEL không cần biết bean được lưu ở singleton registry, thuộc scope nào hay được tạo bởi factory nào; những chi tiết đó thuộc về resolver.

Vai trò của các thành phần:

- **ExpressionParser:** phân tích chuỗi expression và tạo đối tượng Expression.
- **EvaluationContext:** cung cấp root object, variables, functions, property accessors, method resolvers, type converter và các thành phần cần cho đánh giá.
- **BeanResolver:** xử lý cú pháp bean reference bắt đầu bằng @.
- **BeanFactory:** nơi Spring quản lý và tra cứu bean.
- **BeanFactoryResolver:** implementation BeanResolver sử dụng một BeanFactory để tìm bean.

Nếu context không có BeanResolver, expression chứa @beanName không thể được phân giải, dù bean đó vẫn tồn tại trong ApplicationContext.

## 4. BeanFactoryResolver hoạt động như thế nào?

Spring cung cấp class:

~~~java
org.springframework.context.expression.BeanFactoryResolver
~~~

Class này nhận một BeanFactory trong constructor. Khi SpEL yêu cầu phân giải một bean name, BeanFactoryResolver chuyển yêu cầu sang BeanFactory để lấy bean theo tên.

Có thể hình dung luồng xử lý:

~~~text
Expression: @discountPolicy.calculate(#order)
             |
             v
        SpEL parser
             |
             v
       EvaluationContext
             |
             v
         BeanResolver
             |
             v
      BeanFactoryResolver
             |
             v
    BeanFactory.getBean("discountPolicy")
             |
             v
       DiscountPolicy bean
             |
             v
     gọi calculate(order)
             |
             v
       kết quả expression
~~~

Điểm cốt lõi của BeanFactoryResolver là **ủy quyền việc tìm bean cho BeanFactory**. Resolver không tự tạo một registry riêng, không tự quản lý vòng đời bean và không tự thay thế dependency injection.

Do BeanFactory chịu trách nhiệm cung cấp instance, các quy tắc quản lý bean hiện có của Spring tiếp tục được áp dụng: singleton, prototype, request/session scope nếu hợp lệ, lazy initialization, FactoryBean và các proxy do container cung cấp.

## 5. Tự cấu hình BeanFactoryResolver trong Java

Khi tự tạo SpEL parser và EvaluationContext, cần gắn BeanFactoryResolver vào context nếu expression dùng @beanName.

Ví dụ:

~~~java
ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);

ExpressionParser parser = new SpelExpressionParser();

BigDecimal discount = parser
        .parseExpression("@discountPolicy.calculate(#order)")
        .getValue(context, BigDecimal.class);
~~~

ApplicationContext triển khai các contract BeanFactory cần thiết, nên có thể truyền trực tiếp vào BeanFactoryResolver. Nếu đang có một BeanFactory cụ thể, có thể truyền BeanFactory đó thay cho ApplicationContext.

Điều quan trọng là gọi:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Việc tạo StandardEvaluationContext đơn thuần không tự kết nối context với Spring container. Nếu bỏ qua bước gắn resolver, expression có @beanName sẽ không tìm thấy bean.

### 5.1. Dùng bean reference để đọc property

Bean không nhất thiết phải được gọi method. Có thể đọc property của bean:

~~~java
@Component
class AppSettings {

    public String getRegion() {
        return "ap-southeast-1";
    }
}
~~~

Expression:

~~~text
@appSettings.region
~~~

SpEL phân giải bean appSettings, sau đó đọc property region thông qua cơ chế property access của EvaluationContext.

Có thể tiếp tục đọc property lồng nhau:

~~~text
@appSettings.database.connectionTimeout
~~~

Trong trường hợp này, appSettings là bean reference; database và connectionTimeout là các property của object tương ứng.

### 5.2. Dùng bean reference trong biểu thức có biến

Bean reference có thể kết hợp với variables:

~~~text
@permissionService.canRead(#document, #currentUser)
~~~

Ở đây:

- permissionService là bean được tìm trong BeanFactory.
- document và currentUser là variables được cung cấp trong EvaluationContext.
- Kết quả trả về từ canRead() là kết quả của expression.

Cách này giúp tách quy tắc nghiệp vụ thành Java method có thể kiểm thử độc lập, còn SpEL chỉ đóng vai trò kết nối dữ liệu và gọi method.

## 6. Spring tự cấu hình bean resolver ở những integration point nào?

Khi expression được đánh giá bởi Spring container hoặc một module tích hợp, Spring thường tạo EvaluationContext phù hợp và cấu hình BeanResolver để expression có thể tham chiếu bean.

Ví dụ với @Value:

~~~java
@Component
class RuntimeSettings {

    @Value("#{ @appSettings.region }")
    private String region;

    @Value("#{ @discountPolicy.defaultRate }")
    private BigDecimal defaultRate;
}
~~~

Trong quá trình xử lý expression của @Value, Spring sử dụng bean expression resolver gắn với BeanFactory. Vì vậy, bean reference có thể được phân giải mà không cần người dùng tự tạo StandardEvaluationContext.

Một số điểm tích hợp khác cũng cho phép gọi bean từ SpEL, tùy thuộc vào module và thuộc tính annotation:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "@cacheKeyGenerator.forProduct(#product)"
)
public Product find(Product product) {
    // ...
}
~~~

Với method security:

~~~java
@PreAuthorize("@permissionService.canRead(#document)")
public Document read(Document document) {
    // ...
}
~~~

Trong các ví dụ này, Spring Security và Spring Cache tạo context theo quy tắc riêng của module. Không nên giả định root object, variables hoặc method metadata ở các integration point là giống nhau. Tuy nhiên, bean reference vẫn được phân giải thông qua khả năng resolver mà context của module cung cấp.

Nếu một annotation hoặc thuộc tính cụ thể không hỗ trợ bean reference, cú pháp @beanName sẽ không tự hoạt động chỉ vì ứng dụng có bean cùng tên. Cần kiểm tra tài liệu của đúng module và phiên bản đang chạy.

## 7. Bean name, alias và tên có ký tự đặc biệt

BeanFactoryResolver phân giải bean theo tên do Spring container quản lý. Tên đó có thể là tên mặc định, tên khai báo tường minh hoặc alias.

Ví dụ:

~~~java
@Component("discountPolicy")
class DefaultDiscountPolicy {
    // ...
}
~~~

Expression tham chiếu:

~~~text
@discountPolicy
~~~

Nếu bean được khai báo với alias, alias cũng có thể dùng làm tên tra cứu nếu BeanFactory đăng ký alias đó.

Với bean name có ký tự đặc biệt hoặc dấu chấm, có thể đặt tên trong dấu nháy đơn:

~~~text
@'billing.discount-policy'
~~~

Dấu nháy giúp parser hiểu toàn bộ phần tên là bean name. Khi đặt tên bean mới, nên ưu tiên tên đơn giản, ổn định và không chứa ký tự đặc biệt để expression dễ đọc.

Bean reference theo tên cũng có nghĩa là đổi bean name hoặc xóa alias có thể làm expression bị lỗi dù class Java không thay đổi. Vì vậy, tên bean được dùng trong expression là một phần của hợp đồng cấu hình và cần được quản lý khi refactor.

## 8. Bean scope và vòng đời khi resolve bean

BeanFactoryResolver gọi BeanFactory để lấy bean. Vì thế, cách trả về instance phụ thuộc scope và cấu hình của bean.

### 8.1. Singleton

Với singleton bean, các lần resolve thường trả về cùng instance do container quản lý:

~~~text
@discountPolicy.calculate(#order)
~~~

SpEL không tự tạo một DiscountPolicy mới cho mỗi lần đánh giá. BeanFactory áp dụng scope singleton đã cấu hình.

### 8.2. Prototype

Với prototype bean, mỗi lần BeanFactory.getBean() được gọi có thể tạo một instance mới. Do BeanFactoryResolver ủy quyền cho BeanFactory, một lần resolve bean prototype có thể kích hoạt việc tạo instance mới theo quy tắc prototype.

Điều này cần được cân nhắc nếu expression được đánh giá thường xuyên hoặc bean có khởi tạo tốn kém.

### 8.3. Request và session scope

Bean có request/session scope cần một request hoặc session context đang hoạt động. Nếu expression được đánh giá ngoài phạm vi đó, BeanFactory có thể không resolve được bean scoped tương ứng.

Trong ứng dụng web, Spring thường dùng scoped proxy để bean có thể được inject hoặc tham chiếu qua proxy. BeanFactoryResolver lấy bean theo cách BeanFactory cung cấp, nên proxy và quy tắc scope của container vẫn được áp dụng.

### 8.4. Lazy initialization và lỗi khởi tạo

Nếu bean được cấu hình lazy, lần đầu expression tham chiếu bean có thể là thời điểm bean được khởi tạo. Nếu constructor, dependency hoặc quá trình khởi tạo thất bại, lỗi đó xuất hiện khi resolve/evaluate expression.

Vì vậy, bean reference không chỉ là tra một tên trong map. Việc gọi getBean() có thể kích hoạt lifecycle behavior của container.

## 9. Khi nào bean reference không hoạt động?

Có một số lỗi thường gặp khi dùng @beanName.

### 9.1. EvaluationContext chưa có BeanResolver

Ví dụ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("@discountPolicy.calculate(#order)");

expression.getValue(context);
~~~

Context trên chưa được gắn BeanResolver. Dù discountPolicy tồn tại trong ApplicationContext, SpEL không có cơ chế để tìm bean đó.

Cách xử lý:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);
~~~

### 9.2. Bean name không tồn tại

Nếu tên bean hoặc alias không được đăng ký trong BeanFactory, resolver không thể trả về object tương ứng. Hãy kiểm tra tên bean, alias và cấu hình component scan hoặc @Bean method.

Không nên nhầm tên class với bean name. Một class có thể được đăng ký dưới tên khác, và một bean có thể được khai báo mà không dùng tên class làm tên mặc định.

### 9.3. Bean tồn tại nhưng khởi tạo thất bại

BeanFactory có thể tìm thấy định nghĩa bean nhưng không tạo được instance vì dependency thiếu, constructor lỗi hoặc cấu hình sai. Trong trường hợp này, lỗi đến từ quá trình tạo bean, không phải từ cú pháp SpEL.

### 9.4. Resolve thành công nhưng method/property không truy cập được

Sau khi resolver trả về bean, SpEL vẫn phải phân giải method hoặc property tiếp theo:

~~~text
@discountPolicy.calculate(#order)
@appSettings.region
~~~

Nếu method không tồn tại, chữ ký không phù hợp, property không đọc được hoặc một object trung gian là null, expression có thể thất bại ở bước evaluate tiếp theo.

Cần tách ba lớp lỗi:

- **Parse error:** cú pháp expression không hợp lệ.
- **Bean resolution error:** không có resolver hoặc không tìm thấy bean theo tên.
- **Evaluation error:** bean đã được resolve nhưng method/property hoặc dữ liệu đầu vào không đáp ứng yêu cầu.

## 10. Tự viết BeanResolver khi cần quy tắc phân giải riêng

BeanFactoryResolver phù hợp khi muốn dùng trực tiếp quy tắc tìm bean của Spring BeanFactory. Trong một số ứng dụng, có thể cần một resolver khác, ví dụ chỉ cho phép một tập bean được truy cập hoặc ánh xạ tên expression sang một service facade.

BeanResolver là một SPI, nên có thể triển khai resolver riêng:

~~~java
public class RestrictedBeanResolver implements BeanResolver {

    private final Map<String, Object> allowedBeans;

    public RestrictedBeanResolver(Map<String, Object> allowedBeans) {
        this.allowedBeans = Map.copyOf(allowedBeans);
    }

    @Override
    public Object resolve(EvaluationContext context, String beanName)
            throws AccessException {

        Object bean = allowedBeans.get(beanName);

        if (bean == null) {
            throw new AccessException(
                    "Bean is not available to this expression: " + beanName
            );
        }

        return bean;
    }
}
~~~

Sau đó gắn resolver vào context:

~~~java
context.setBeanResolver(
        new RestrictedBeanResolver(allowedBeans)
);
~~~

Resolver tùy chỉnh cần xác định rõ hành vi với bean name không hợp lệ, quyền truy cập và kiểu exception. Nếu mục tiêu là truy cập bean trong Spring container theo cách thông thường, không cần tự viết resolver; BeanFactoryResolver đã cung cấp implementation đó.

## 11. Bean reference và giới hạn bảo mật

Bean reference có thể mở đường cho expression gọi method trên các service trong ứng dụng. Vì vậy, không nên cho phép người dùng bên ngoài gửi một chuỗi SpEL tùy ý rồi đánh giá bằng context có quyền truy cập rộng.

Ví dụ, một context cho phép tham chiếu @paymentService hoặc @accountAdmin có thể mở ra các thao tác mà người nhập expression không nên được quyền gọi.

Một số nguyên tắc:

1. Chỉ đánh giá expression từ nguồn đáng tin cậy hoặc được kiểm soát.
2. Chỉ đăng ký BeanResolver khi tính năng thực sự cần bean reference.
3. Nếu chỉ cần đọc dữ liệu, cân nhắc SimpleEvaluationContext với các accessor được giới hạn. SimpleEvaluationContext không cung cấp bean reference như StandardEvaluationContext.
4. Nếu phải dùng resolver, giới hạn tập bean được phép bằng một facade hoặc resolver tùy chỉnh.
5. Không đưa trực tiếp các bean có quyền ghi dữ liệu, thanh toán, quản trị hoặc truy cập bí mật vào context dành cho expression không tin cậy.
6. Kiểm thử cả trường hợp bean được phép và bean bị từ chối.

Giới hạn resolver là một phần của thiết kế bảo mật expression. Chỉ ẩn tên bean trong tài liệu hoặc giao diện không phải là một biện pháp kiểm soát truy cập.

## 12. Kiểm thử bean resolution

Có thể kiểm tra BeanFactoryResolver bằng một ApplicationContext test:

~~~java
class BeanReferenceExpressionTest {

    @Test
    void resolvesBeanByName() {
        try (AnnotationConfigApplicationContext app =
                     new AnnotationConfigApplicationContext(TestConfig.class)) {

            StandardEvaluationContext context =
                    new StandardEvaluationContext();

            context.setBeanResolver(new BeanFactoryResolver(app));
            context.setVariable("amount", new BigDecimal("100"));

            BigDecimal result = new SpelExpressionParser()
                    .parseExpression("@discountPolicy.apply(#amount)")
                    .getValue(context, BigDecimal.class);

            assertEquals(new BigDecimal("95.00"), result);
        }
    }

    @Configuration
    static class TestConfig {

        @Bean
        DiscountPolicy discountPolicy() {
            return amount -> amount.multiply(new BigDecimal("0.95"));
        }
    }
}
~~~

Ví dụ minh họa ba bước quan trọng:

1. Tạo ApplicationContext có đăng ký bean discountPolicy.
2. Gắn BeanFactoryResolver vào StandardEvaluationContext.
3. Đánh giá expression dùng @discountPolicy.

Trong test thực tế, nên kiểm tra thêm bean name sai, context không có resolver, method không tồn tại và bean có scope đặc biệt nếu ứng dụng phụ thuộc vào scope đó.

Nếu expression được Spring đánh giá tự động qua @Value hoặc một annotation khác, hãy viết integration test ở đúng điểm tích hợp thay vì chỉ kiểm tra parser độc lập. Test đó xác nhận Spring đã cung cấp resolver và context cần thiết.

## 13. Ghi nhớ nhanh

- **@beanName** tham chiếu bean trong Spring container.
- **BeanResolver** là SPI xử lý việc phân giải bean reference của SpEL.
- **BeanFactoryResolver** là implementation dùng BeanFactory để tìm bean theo tên.
- Khi tự tạo StandardEvaluationContext, cần gọi setBeanResolver(new BeanFactoryResolver(beanFactory)).
- Spring tự cấu hình expression context tại các integration point hỗ trợ bean reference, ví dụ @Value; từng module có context riêng.
- **#variable** là biến trong EvaluationContext; **@beanName** là bean trong BeanFactory.
- BeanFactoryResolver ủy quyền cho BeanFactory, vì vậy scope, alias, lazy initialization và lifecycle của container tiếp tục được áp dụng.
- SimpleEvaluationContext được giới hạn và không hỗ trợ bean reference như StandardEvaluationContext.
- Không có resolver, bean name sai, bean khởi tạo lỗi hoặc method/property không truy cập được đều có thể làm expression thất bại ở các giai đoạn khác nhau.
- Không đánh giá expression không tin cậy với resolver có quyền truy cập toàn bộ bean của ứng dụng.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Bean References in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [BeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactory.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
