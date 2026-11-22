# Tham chiếu bean trong annotation và cấu hình với Spring Expression Language (SpEL)

Spring Expression Language (SpEL) cho phép biểu thức tham chiếu trực tiếp đến bean do Spring container quản lý. Nhờ cú pháp tham chiếu bean, một giá trị trong cấu hình hoặc annotation có thể lấy property, gọi phương thức hay kết hợp dữ liệu từ một bean khác tại thời điểm Spring đánh giá biểu thức.

Ví dụ, biểu thức sau lấy thuộc tính defaultCurrency từ bean pricingService:

~~~text
#{@pricingService.defaultCurrency}
~~~

Cú pháp @pricingService xác định bean theo tên. Phần .defaultCurrency truy cập property của bean đó. Khi Spring đánh giá biểu thức trong môi trường container, BeanResolver được cấu hình để tìm bean tương ứng.

Bài này trình bày cú pháp bean reference, cách Spring sử dụng SpEL trong annotation và cấu hình XML/Java, cách cấu hình thủ công EvaluationContext, sự khác nhau giữa SpEL và property placeholder, cùng các lỗi thường gặp khi tham chiếu bean.

## 1. Bean reference là gì?

Bean reference là cách một biểu thức SpEL lấy một bean từ BeanFactory hoặc ApplicationContext bằng tên bean.

Cú pháp cơ bản:

~~~text
@beanName
~~~

Ví dụ:

~~~text
@pricingService
@inventoryService
@featureFlags
~~~

Các biểu thức này trả về chính đối tượng bean được container quản lý. Có thể tiếp tục truy cập property hoặc gọi phương thức:

~~~text
@pricingService.defaultCurrency
@inventoryService.availableQuantity('SKU-100')
@featureFlags.isEnabled('new-checkout')
~~~

Trong ví dụ, @pricingService là tham chiếu bean. Phần .defaultCurrency hoặc lời gọi phương thức phía sau được đánh giá trên bean đó.

Tên bean phải khớp với tên hoặc alias đã đăng ký trong container. Tên bean có phân biệt chữ hoa/chữ thường. Nếu tên bean chứa khoảng trắng hoặc ký tự đặc biệt, có thể đặt tên trong dấu nháy đơn:

~~~text
@'pricing service'.defaultCurrency
~~~

Dùng tên bean rõ ràng giúp biểu thức dễ đọc và giảm nhầm lẫn khi ứng dụng có nhiều bean cùng kiểu.

## 2. BeanResolver và cách SpEL tìm bean

SpEL không tự biết ApplicationContext nào cần dùng chỉ từ chuỗi biểu thức. Để phân giải bean reference, EvaluationContext phải có một BeanResolver.

Spring cung cấp BeanFactoryResolver, một implementation của BeanResolver dùng BeanFactory để tìm bean theo tên.

Khi Spring container đánh giá SpEL trong các cơ chế tích hợp sẵn như @Value, Spring cấu hình môi trường đánh giá phù hợp và cung cấp khả năng phân giải bean. Vì vậy, biểu thức @beanName có thể hoạt động mà không cần ứng dụng tự tạo EvaluationContext.

Nếu tự tạo EvaluationContext trong mã Java, cần đăng ký resolver:

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

StandardEvaluationContext context = new StandardEvaluationContext();

BeanFactoryResolver beanResolver =
        new BeanFactoryResolver(beanFactory);

context.setBeanResolver(beanResolver);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("@pricingService.defaultCurrency");

String currency = expression.getValue(context, String.class);
~~~

Trong ví dụ:

- beanFactory là BeanFactory hoặc ApplicationContext đang quản lý bean.
- BeanFactoryResolver chuyển yêu cầu bean reference của SpEL thành thao tác tra cứu bean trong factory.
- setBeanResolver(...) gắn resolver vào EvaluationContext.
- getValue(context, String.class) đánh giá biểu thức và yêu cầu kết quả kiểu String.

Nếu không có BeanResolver phù hợp, biểu thức chứa @pricingService không thể phân giải bean và quá trình đánh giá sẽ thất bại.

## 3. Tham chiếu bean trong annotation @Value

@Value là một trong những nơi thường dùng SpEL. Annotation này cho phép Spring inject giá trị từ property, system property hoặc một biểu thức được đánh giá.

Ví dụ lấy property từ bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CheckoutSettings {

    private final String currency;

    public CheckoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Spring đánh giá biểu thức trong @Value rồi truyền kết quả vào tham số constructor. Bean pricingService phải tồn tại và có thể được phân giải trong ApplicationContext.

Có thể dùng field injection:

~~~java
@Component
public class CheckoutSettings {

    @Value("#{ @featureFlags.checkoutEnabled }")
    private boolean checkoutEnabled;

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }
}
~~~

Hoặc method/parameter injection:

~~~java
@Component
public class ReportSettings {

    private String currency;

    @Value("#{ @pricingService.defaultCurrency }")
    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Trong các ví dụ, biểu thức SpEL nằm trong #{...}. Dấu @ bên trong biểu thức mới là ký hiệu tham chiếu bean. Hai lớp cú pháp này có vai trò khác nhau: #{...} đánh dấu vùng biểu thức cần đánh giá, còn @beanName tìm bean trong container.

### 3.1. Lấy property hoặc gọi phương thức của bean

Bean reference có thể dùng để đọc property:

~~~java
@Value("#{ @pricingService.defaultCurrency }")
private String currency;
~~~

Cũng có thể gọi phương thức nếu phương thức đó có thể truy cập và lời gọi phù hợp với ngữ cảnh:

~~~java
@Value("#{ @pricingService.defaultTaxRate() }")
private BigDecimal taxRate;
~~~

Có thể truyền đối số literal hoặc giá trị khác vào lời gọi:

~~~java
@Value("#{ @pricingService.rateFor('VN') }")
private BigDecimal vietnamRate;
~~~

Không nên dùng @Value để gọi những phương thức có tác dụng phụ hoặc thay đổi trạng thái ứng dụng. Biểu thức cấu hình nên có kết quả xác định, dễ kiểm soát và không phụ thuộc vào thứ tự khởi tạo ngoài dự kiến.

## 4. Bean reference trong XML configuration

Trong XML bean definition, giá trị thuộc tính có thể chứa biểu thức SpEL.

Ví dụ:

~~~xml
<bean id="checkoutSettings"
      class="com.example.CheckoutSettings">
    <property name="currency"
              value="#{@pricingService.defaultCurrency}" />
</bean>
~~~

Spring đánh giá biểu thức và inject kết quả vào property currency của bean checkoutSettings.

Có thể dùng bean reference để tính giá trị:

~~~xml
<bean id="shippingPolicy"
      class="com.example.ShippingPolicy">
    <property name="freeShippingThreshold"
              value="#{@pricingService.defaultFreeShippingThreshold()}" />
</bean>
~~~

Biểu thức được đánh giá trong môi trường bean factory. Bean được tham chiếu cần có mặt trong cùng container hoặc có thể được phân giải qua cơ chế factory đã cấu hình.

Trong XML, dấu # và dấu ngoặc nhọn phải được đặt đúng trong thuộc tính value. Nếu biểu thức có ký tự đặc biệt thuộc cú pháp XML, hãy escape theo quy tắc XML.

## 5. Bean reference trong Java configuration

Trong Java configuration, Spring thường khuyến khích inject dependency trực tiếp qua tham số phương thức @Bean hoặc constructor. Đây là cách rõ ràng khi một bean cần bean khác để khởi tạo.

Ví dụ dependency injection trực tiếp:

~~~java
@Configuration
public class CheckoutConfiguration {

    @Bean
    public CheckoutService checkoutService(
            PricingService pricingService) {
        return new CheckoutService(pricingService);
    }
}
~~~

Nếu một tham số cần giá trị được tính bằng SpEL, có thể dùng @Value tại tham số:

~~~java
@Configuration
public class CheckoutConfiguration {

    @Bean
    public CheckoutSettings checkoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        return new CheckoutSettings(currency);
    }
}
~~~

Ở đây, Spring xử lý @Value và đánh giá bean reference trong container. Phần thân phương thức Java vẫn là mã Java thông thường.

Không phải mọi thuộc tính của mọi annotation đều là SpEL expression. Chỉ những annotation hoặc thuộc tính được Spring hay thư viện tích hợp tài liệu hóa là hỗ trợ SpEL mới được đánh giá như biểu thức. Ví dụ, không thể tự động đặt @pricingService vào bất kỳ annotation nào rồi mong Spring phân giải nó.

## 6. Bean reference trong Spring Security method annotations

Spring Security hỗ trợ SpEL trong các annotation bảo vệ method như @PreAuthorize và @PostAuthorize. Bean reference giúp gọi một service chuyên trách kiểm tra quyền.

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize("@documentAuthorization.canRead(authentication, #documentId)")
    public Document readDocument(String documentId) {
        // Tải và trả về tài liệu.
        return loadDocument(documentId);
    }
}
~~~

Biểu thức @documentAuthorization tham chiếu bean documentAuthorization. Phương thức canRead nhận authentication và documentId để quyết định người gọi có được phép đọc tài liệu hay không.

Để dùng method security, ứng dụng cần bật cấu hình phù hợp, ví dụ:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Tên tham số như #documentId phải được Spring Security nhận diện. Cấu hình biên dịch lưu tên tham số hoặc annotation tham số theo hướng dẫn của phiên bản Spring Security đang dùng sẽ giúp việc tham chiếu biến ổn định.

Có thể dùng bean reference trong @PostAuthorize để kiểm tra kết quả trả về:

~~~java
@PostAuthorize("@documentAuthorization.canReadResult(returnObject, authentication)")
public Document findDocument(String documentId) {
    return loadDocument(documentId);
}
~~~

Method security là một điểm tích hợp cụ thể của SpEL. Cú pháp và các biến có sẵn phụ thuộc vào loại annotation và cấu hình Spring Security; không nên giả định mọi annotation có cùng evaluation context.

## 7. Bean reference và FactoryBean

Một FactoryBean là bean đặc biệt tạo ra một đối tượng khác. Khi tra cứu tên FactoryBean thông thường, container thường trả về đối tượng do factory tạo ra.

Nếu cần tham chiếu chính FactoryBean, có thể dùng tiền tố & trước tên bean:

~~~text
&reportFactory
~~~

Trong ngữ cảnh tra cứu bean, cú pháp này yêu cầu factory bean thay vì sản phẩm của nó. Điều này hữu ích khi cần truy cập metadata hoặc hành vi của factory.

Hãy phân biệt hai đối tượng:

- Bean được tạo ra bởi FactoryBean: đối tượng sản phẩm mà ứng dụng thường sử dụng.
- Chính FactoryBean: đối tượng chịu trách nhiệm tạo sản phẩm.

Chỉ dùng &beanName khi thực sự cần factory. Với dependency thông thường, dùng bean reference theo tên hoặc cơ chế inject dependency tiêu chuẩn.

## 8. Phân biệt SpEL và property placeholder

Spring thường dùng hai cú pháp nhìn khá giống nhau nhưng có mục đích khác nhau:

| Cú pháp | Mục đích |
|---|---|
| \${property.name} | Lấy giá trị từ property source hoặc cấu hình bên ngoài |
| #{spelExpression} | Đánh giá một biểu thức SpEL |

Ví dụ placeholder:

~~~java
@Value("\${app.checkout.currency}")
private String currency;
~~~

Ví dụ SpEL bean reference:

~~~java
@Value("#{ @pricingService.defaultCurrency }")
private String currency;
~~~

Placeholder lấy giá trị cấu hình theo key. SpEL đánh giá biểu thức, có thể truy cập bean, property, toán tử và phương thức được cho phép.

Hai cơ chế có thể được phối hợp trong một số biểu thức, nhưng hãy giữ ranh giới rõ ràng: placeholder dùng để lấy cấu hình, còn SpEL dùng để tính hoặc truy cập đối tượng qua biểu thức. Khi giá trị có thể thay đổi theo môi trường, property externalized thường dễ cấu hình và kiểm thử hơn việc hard-code tên bean trong biểu thức.

## 9. Bean reference và dependency injection thông thường

Bean reference trong SpEL không thay thế mọi trường hợp của @Autowired hoặc constructor injection.

Dùng dependency injection trực tiếp khi một class cần một dependency để thực hiện chức năng:

~~~java
@Service
public class CheckoutService {

    private final PricingService pricingService;

    public CheckoutService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
~~~

Dùng SpEL bean reference khi cần một giá trị được tính hoặc lấy từ bean ngay trong một vị trí hỗ trợ biểu thức, chẳng hạn @Value hoặc method-security annotation.

Các khác biệt thực tế:

- Constructor injection làm dependency hiện rõ trong chữ ký constructor.
- @Value với SpEL phù hợp với giá trị cấu hình được tính từ bean hoặc biểu thức.
- Bean reference trong security expression hữu ích khi muốn chuyển logic phân quyền sang một bean chuyên trách.
- Lạm dụng bean reference trong cấu hình có thể làm dependency khó nhận ra khi đọc mã và khó phát hiện vòng phụ thuộc.

Ưu tiên injection trực tiếp cho quan hệ dependency cốt lõi. Dùng SpEL ở nơi biểu thức thực sự làm cấu hình hoặc chính sách dễ diễn đạt hơn.

## 10. Vòng đời bean và phụ thuộc khởi tạo

Một biểu thức bean reference chỉ có thể được đánh giá khi bean được tham chiếu có thể được phân giải. Nếu biểu thức trong @Value tham chiếu một bean chưa thể khởi tạo do vòng phụ thuộc, quá trình tạo bean có thể thất bại.

Ví dụ về quan hệ dễ gây vòng phụ thuộc:

- CheckoutSettings cần pricingService để inject currency.
- PricingService lại cần CheckoutSettings trong constructor.

Cả hai bean phụ thuộc lẫn nhau trong giai đoạn khởi tạo. Việc dùng SpEL không tự giải quyết được vòng phụ thuộc đó.

Khi gặp vấn đề:

1. Xác định bean nào đang tham chiếu bean nào.
2. Kiểm tra constructor, field, setter và @Value có tạo chu trình hay không.
3. Tách phần cấu hình dùng chung thành một bean độc lập nếu phù hợp.
4. Dùng dependency injection trực tiếp khi có thể để quan hệ dễ quan sát.
5. Tránh gọi phương thức có tác dụng phụ trong biểu thức khởi tạo.

Biểu thức nên đọc giá trị hoặc tính kết quả cần thiết, không nên trở thành một cơ chế ẩn để điều khiển toàn bộ vòng đời bean.

## 11. Lỗi thường gặp khi tham chiếu bean

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy bean | Tên bean hoặc alias sai, hoặc bean không nằm trong container đang đánh giá. | Kiểm tra tên và ApplicationContext/BeanFactory. |
| Bean reference không hoạt động trong EvaluationContext tự tạo | Chưa cấu hình BeanResolver. | Đăng ký BeanFactoryResolver. |
| @Value không đánh giá biểu thức | Giá trị không nằm trong dạng biểu thức hoặc annotation processing chưa được cấu hình đúng. | Kiểm tra cú pháp #{...} và cơ chế xử lý annotation của container. |
| Nhầm placeholder với SpEL | Placeholder và SpEL có mục đích khác nhau. | Dùng placeholder cho property key, SpEL cho biểu thức. |
| Truy cập property không tồn tại | Bean không có property hoặc accessor phù hợp. | Kiểm tra getter, property accessor và tên property. |
| Gọi phương thức không hợp lệ | Sai tên, tham số hoặc kiểu trả về. | Kiểm tra chữ ký phương thức và kiểu kết quả mong đợi. |
| Method-security không nhận ra tham số | Tên tham số không được phát hiện hoặc biểu thức dùng sai biến. | Kiểm tra metadata tham số và cấu hình Spring Security. |
| Vòng phụ thuộc khi khởi tạo | Các bean tham chiếu lẫn nhau trong constructor hoặc @Value. | Tách dependency hoặc thay đổi cấu trúc khởi tạo. |
| Dùng bean name sai chữ hoa/thường | Tra cứu bean theo tên không khớp. | Dùng đúng bean name hoặc alias. |
| Nghĩ mọi annotation đều hỗ trợ SpEL | Chỉ một số điểm tích hợp có cơ chế đánh giá biểu thức. | Kiểm tra tài liệu của annotation và thư viện tương ứng. |

Khi chẩn đoán lỗi, phân biệt lỗi cú pháp SpEL với lỗi phân giải bean và lỗi đánh giá property/phương thức. Kiểm tra thông báo lỗi, tên bean, context đang sử dụng và thời điểm biểu thức được đánh giá.

## 12. Lưu ý bảo mật

Bean reference có thể mở ra khả năng gọi phương thức trên bean. Nếu biểu thức được lấy từ người dùng hoặc nguồn cấu hình không đáng tin cậy, một context quá rộng có thể cho phép truy cập các bean hoặc hành vi không dự kiến.

Một số nguyên tắc:

1. Chỉ cung cấp bean cần thiết cho mục đích của biểu thức.
2. Không đánh giá tùy tiện SpEL do người dùng gửi lên bằng một StandardEvaluationContext đầy đủ quyền.
3. Dùng SimpleEvaluationContext khi bài toán phù hợp với tập tính năng giới hạn, đồng thời hiểu rõ các khả năng mà context này cho phép.
4. Với method security, giữ logic phân quyền trong các service chuyên trách và kiểm tra đầu vào của chúng.
5. Không dùng biểu thức để lách qua ranh giới phân quyền của ứng dụng.
6. Tránh cho phép biểu thức truy cập bean có thao tác phá hủy hoặc thay đổi trạng thái nếu không cần thiết.

Bean reference là một cơ chế tích hợp hữu ích, nhưng quyền truy cập thực tế phụ thuộc vào BeanResolver, EvaluationContext và các khả năng khác được bật.

## 13. Ghi nhớ

- @beanName tham chiếu bean theo tên trong Spring container.
- Có thể truy cập property hoặc gọi phương thức sau bean reference.
- BeanFactoryResolver kết nối SpEL với BeanFactory trong EvaluationContext tự tạo.
- @Value với #{...} là điểm tích hợp phổ biến để inject kết quả biểu thức.
- XML bean definition có thể dùng SpEL trong thuộc tính value.
- Java configuration có thể dùng @Value trên tham số phương thức @Bean; dependency cốt lõi thường nên inject trực tiếp.
- Spring Security hỗ trợ bean reference trong các method-security expression như @PreAuthorize.
- &beanName dùng khi cần tham chiếu chính FactoryBean.
- Placeholder theo dạng dollar-brace lấy property; #{...} đánh giá SpEL.
- Không phải mọi annotation đều hỗ trợ SpEL.
- Kiểm tra BeanResolver, tên bean, vòng đời khởi tạo và phạm vi quyền truy cập khi gặp lỗi.