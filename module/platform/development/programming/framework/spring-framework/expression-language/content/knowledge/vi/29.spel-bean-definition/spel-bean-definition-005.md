# Tham chiếu bean trong cấu hình bằng SpEL

## Mục tiêu

Spring Expression Language (SpEL) có thể tham chiếu một bean do Spring quản lý bằng cú pháp @beanName. Khi expression được đánh giá trong Spring container, bean reference cho phép đọc property, gọi method hoặc kết hợp dữ liệu từ bean với các giá trị khác trong biểu thức.

Ví dụ:

~~~spel
@pricingPolicy.defaultRate
@currencyCatalog['USD']
@featurePolicy.enabledFor('checkout')
~~~

Bean reference hữu ích khi cần tính một giá trị cấu hình từ bean khác, hoặc khi một expression cần gọi một phép tính đã được cung cấp bởi application context. Tuy nhiên, nếu mục đích chỉ là inject một dependency vào class để sử dụng trong code Java, constructor injection thường rõ ràng và dễ kiểm thử hơn.

## 1. Cú pháp bean reference

Cú pháp cơ bản là ký hiệu @ theo sau bởi tên bean:

~~~spel
@pricingPolicy
@pricingPolicy.defaultRate
@pricingPolicy.calculateTax(amount)
~~~

- @pricingPolicy tham chiếu instance bean có tên pricingPolicy.
- @pricingPolicy.defaultRate đọc property defaultRate của bean đó.
- @pricingPolicy.calculateTax(amount) gọi method trên bean.

Tên bean phải khớp với bean name hoặc alias đã đăng ký trong BeanFactory. Với tên bean có ký tự đặc biệt hoặc không phù hợp với identifier thông thường, đặt tên trong dấu nháy đơn:

~~~spel
@'legacy.pricing-policy'.defaultRate
~~~

Ký hiệu @ là cú pháp của SpEL. Nó khác với #variable: biến được đăng ký trực tiếp trong EvaluationContext, còn bean reference được phân giải thông qua BeanResolver.

## 2. BeanResolver chịu trách nhiệm phân giải bean

SpEL không tự biết mọi bean trong mọi EvaluationContext. Để biểu thức phân giải được @beanName, context phải có BeanResolver.

Trong Spring ApplicationContext, Spring expression infrastructure thường cấu hình resolver cho expression dùng trong bean definitions và @Value. Khi tự tạo parser và StandardEvaluationContext trong Java, ứng dụng cần đăng ký resolver rõ ràng.

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(beanFactory));

Expression expression = parser.parseExpression("@pricingPolicy.defaultRate");
BigDecimal rate = expression.getValue(context, BigDecimal.class);
~~~

BeanFactoryResolver là adapter nối SpEL với Spring BeanFactory. Khi expression tham chiếu bean, resolver yêu cầu BeanFactory lấy bean theo tên đã chỉ định.

Các import thường dùng:

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
~~~

Nếu StandardEvaluationContext được tạo thủ công nhưng chưa gọi setBeanResolver(...), biểu thức @pricingPolicy sẽ không được phân giải. Việc chỉ tạo SpelExpressionParser không tự kết nối parser với ApplicationContext.

## 3. Dùng bean reference trong @Value

Spring có thể đánh giá SpEL trong annotation @Value. Ví dụ, lấy một property từ bean policy:

~~~java
@Component
public class InvoiceConfiguration {

    @Value("#{ @pricingPolicy.defaultRate }")
    private BigDecimal defaultRate;
}
~~~

Cũng có thể gọi method để tính giá trị được inject:

~~~java
@Component
public class FeatureConfiguration {

    @Value("#{ @featurePolicy.enabledFor('checkout') }")
    private boolean checkoutEnabled;
}
~~~

Trong ví dụ này, Spring đánh giá expression khi xử lý dependency injection cho bean. Method enabledFor được gọi tại thời điểm expression được đánh giá; giá trị đã inject không tự cập nhật mỗi khi property của featurePolicy thay đổi.

Nếu cần dùng policy ở nhiều thời điểm trong vòng đời ứng dụng, constructor injection thường phù hợp hơn:

~~~java
@Service
public class CheckoutService {

    private final FeaturePolicy featurePolicy;

    public CheckoutService(FeaturePolicy featurePolicy) {
        this.featurePolicy = featurePolicy;
    }

    public boolean isCheckoutEnabled() {
        return featurePolicy.enabledFor("checkout");
    }
}
~~~

Cách này làm rõ dependency và cho phép gọi method khi cần trong luồng xử lý.

## 4. Dùng bean reference trong bean definition XML

Bean definition có thể chứa SpEL expression trong các giá trị property hoặc constructor argument. Expression được bao bằng #{...}:

~~~xml
<bean id="invoiceConfiguration"
      class="com.example.InvoiceConfiguration">
    <property name="defaultRate"
              value="#{ @pricingPolicy.defaultRate }"/>
</bean>
~~~

Có thể dùng bean reference để tạo giá trị cho constructor argument:

~~~xml
<bean id="reportSettings"
      class="com.example.ReportSettings">
    <constructor-arg
        value="#{ @reportPolicy.defaultFormat }"/>
</bean>
~~~

Nếu chỉ cần gán một bean làm dependency cho property, dùng thuộc tính ref của XML thường rõ ràng hơn:

~~~xml
<property name="pricingPolicy" ref="pricingPolicy"/>
~~~

Dùng SpEL khi cần đọc property, gọi phép tính hoặc kết hợp dữ liệu trong expression. Không cần thay thế dependency wiring thông thường bằng expression nếu chỉ muốn inject nguyên bean.

## 5. Kết hợp bean reference với arguments và phép tính

Bean reference có thể được dùng cùng root property, biến và literal:

~~~spel
@pricingPolicy.rateFor(#order.customer.region)
@discountPolicy.discountFor(customer.tier, #requestedDate)
@currencyCatalog[#currencyCode].symbol
~~~

Ví dụ Java, expression có thể sử dụng root object và variable:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "@pricingPolicy.rateFor(#order.customer.region)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
context.setVariable("order", order);

BigDecimal rate = expression.getValue(context, BigDecimal.class);
~~~

Trong ví dụ này:

- @pricingPolicy được phân giải qua BeanResolver.
- #order là biến do ứng dụng đăng ký.
- customer.region được đọc từ object order.
- Method rateFor được gọi trên bean pricingPolicy.

Tên truyền vào setVariable không có dấu #; dấu # chỉ xuất hiện khi tham chiếu biến trong expression.

## 6. Gọi method và đọc property trên bean

Sau khi phân giải bean, SpEL có thể dùng property access và method invocation theo các quy tắc truy cập của evaluation context:

~~~spel
@taxPolicy.defaultRate
@taxPolicy.rateFor('VN')
@featurePolicy.isEnabled('new-checkout')
@catalog.findProduct(#productCode).displayName
~~~

Property access thường dựa trên getter hoặc property accessor phù hợp. Method invocation cần method có thể truy cập và chữ ký tương thích với các đối số được truyền.

Hãy giữ các method được gọi từ expression ngắn, có kết quả dễ dự đoán và không có tác dụng phụ. Nếu expression được đánh giá nhiều lần, method cũng có thể được gọi nhiều lần. Không nên gọi method gửi email, ghi database, publish message hoặc thực hiện một hành động bên ngoài chỉ vì expression đang đọc một giá trị.

## 7. Phân biệt bean reference, variable và type reference

Ba cách tham chiếu sau có mục đích khác nhau:

| Cú pháp | Nguồn được tham chiếu | Ví dụ |
| --- | --- | --- |
| @pricingPolicy | Bean do BeanFactory quản lý, được phân giải qua BeanResolver. | @pricingPolicy.defaultRate |
| #pricingPolicy | Variable đã đăng ký trong EvaluationContext. | #pricingPolicy.defaultRate |
| T(com.example.PricingPolicy) | Class được TypeLocator tìm thấy. | T(java.lang.Math).max(10, 20) |

Không nhầm @ với #. Nếu ứng dụng gọi context.setVariable("policy", policy), expression dùng #policy. Nếu policy là Spring bean và context có BeanResolver, expression dùng @policy.

Type reference T(...) chỉ ra class, không phải instance bean. Dùng nó để truy cập static method hoặc static field, không phải để lấy một Spring-managed bean.

## 8. FactoryBean và dấu &

Một FactoryBean là một bean đặc biệt tạo ra object khác. Thông thường, khi tham chiếu tên bean, Spring trả về object do FactoryBean tạo ra. Nếu cần tham chiếu chính FactoryBean, thêm dấu & trước bean name trong bean reference:

~~~spel
@&clientFactory
~~~

Ví dụ, nếu clientFactory là FactoryBean tạo ra HTTP client:

- @clientFactory tham chiếu HTTP client do factory cung cấp.
- @&clientFactory tham chiếu chính object factory.

Chỉ dùng dạng dereference khi thật sự cần thao tác với FactoryBean. Trong phần lớn cấu hình ứng dụng, dependency cần dùng là object sản phẩm, nên bean reference thông thường hoặc dependency injection sẽ phù hợp hơn.

## 9. Bean scope và thời điểm phân giải

Bean reference được phân giải khi expression được đánh giá. Kết quả phụ thuộc vào scope của bean:

| Scope | Hành vi khi được phân giải |
| --- | --- |
| singleton | Trả về instance singleton đã được quản lý trong BeanFactory. |
| prototype | Mỗi lần BeanFactory lấy bean có thể tạo một instance mới. |
| request/session | Cần scope tương ứng đang hoạt động; nếu dùng ngoài scope, việc phân giải có thể thất bại. |
| scoped proxy | Expression nhận proxy; proxy chuyển lời gọi tới target phù hợp với scope. |

Cần phân biệt thời điểm expression chạy với thời điểm bean được phân giải:

- Trong @Value hoặc bean definition, expression thường được đánh giá trong quá trình tạo bean hoặc inject property. Giá trị scalar được tính khi đó không tự được tính lại về sau.
- Trong expression được ứng dụng parse và gọi getValue nhiều lần, bean reference được phân giải theo từng lần đánh giá.
- Nếu expression chạm tới một lazy bean, việc phân giải có thể kích hoạt quá trình khởi tạo bean.
- Với prototype bean, một expression được đánh giá lại có thể nhận instance mới; với singleton bean, thường nhận cùng instance singleton.

Nếu cần giá trị thay đổi theo từng request, hãy gọi bean trong luồng xử lý phù hợp hoặc đánh giá expression tại thời điểm cần thiết thay vì inject một scalar cố định lúc khởi tạo.

## 10. Bean reference trong cấu hình khác với dependency injection

Bean reference trong SpEL và dependency injection đều có thể truy cập bean, nhưng cách dùng khác nhau:

| Nhu cầu | Cách nên dùng |
| --- | --- |
| Một class cần sử dụng service trong nhiều method | Constructor injection. |
| Một property cấu hình cần lấy giá trị từ bean khác khi khởi tạo | @Value với SpEL có thể phù hợp. |
| Một bean definition cần tính property từ một bean khác | SpEL trong giá trị #{...} có thể phù hợp. |
| Một expression cần gọi một phép tính từ bean đã được expose | @beanName.method(...) với resolver phù hợp. |
| Cần gọi dependency ở nhiều thời điểm hoặc theo request | Inject bean rồi gọi từ Java. |

Ví dụ constructor injection:

~~~java
@Service
public class InvoiceService {

    private final PricingPolicy pricingPolicy;

    public InvoiceService(PricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    public BigDecimal calculateRate(String region) {
        return pricingPolicy.rateFor(region);
    }
}
~~~

Cách này làm dependency hiển thị trong constructor, dễ mock trong unit test và không phụ thuộc vào việc expression resolver có được cấu hình hay không.

## 11. Vòng đời bean và circular dependency

Một expression trong bean definition hoặc @Value có thể yêu cầu Spring phân giải một bean khác trong lúc bean hiện tại đang được tạo. Nếu hai bean tham chiếu lẫn nhau trong quá trình khởi tạo, ứng dụng có thể gặp circular dependency hoặc truy cập một object chưa sẵn sàng.

Ví dụ thiết kế cần tránh:

- Bean A cần property từ bean B trong lúc khởi tạo.
- Bean B lại cần gọi method trên bean A để tự khởi tạo.
- Expression của A phân giải B, rồi method của B quay lại yêu cầu A.

Để giảm rủi ro:

- Dùng constructor injection và thiết kế dependency graph một chiều khi có thể.
- Tránh gọi method nghiệp vụ trên bean khác trong expression khởi tạo.
- Không dùng bean reference để che giấu dependency giữa nhiều bean.
- Nếu cần giá trị cấu hình, cân nhắc đưa dữ liệu vào configuration properties hoặc một object cấu hình độc lập.
- Giữ các method dùng trong expression không phụ thuộc vào trạng thái khởi tạo dở dang.

## 12. Quyền truy cập và an toàn

Bean reference có thể mở rộng đáng kể những gì expression được phép thực hiện. Nếu context có thể phân giải một service rộng, expression có thể gọi public method của service đó theo các method resolver được cấu hình.

Với expression do người dùng, tenant, file cấu hình bên ngoài hoặc nguồn không hoàn toàn tin cậy cung cấp:

- Không cho phép người dùng tự gửi source SpEL tùy ý rồi đánh giá với toàn bộ ApplicationContext.
- Chỉ expose các bean cần thiết cho use case.
- Ưu tiên facade hoặc policy bean có API nhỏ, chỉ đọc và dễ dự đoán.
- Không expose repository, HTTP client, filesystem service, process runner hoặc bean quản trị nếu expression không cần chúng.
- Tránh method có side effect, thao tác ghi hoặc truy cập tài nguyên bên ngoài.
- Dùng context hạn chế và resolver allowlist nếu cần hỗ trợ expression do bên ngoài kiểm soát.
- Xác thực dữ liệu đầu vào và không nối input vào source expression.

SimpleEvaluationContext không hỗ trợ bean references. Nếu use case cần @beanName, phải dùng một context có BeanResolver phù hợp; hãy giới hạn rõ các bean và method được expose thay vì chuyển sang quyền truy cập rộng không cần thiết.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| @beanName không được phân giải | EvaluationContext chưa có BeanResolver. | Cấu hình BeanFactoryResolver hoặc dùng Spring expression infrastructure đã được cấu hình. |
| Không tìm thấy bean | Sai bean name, alias hoặc bean chưa được đăng ký. | Kiểm tra tên bean và cấu hình BeanFactory. |
| Expression chạy trong @Value nhưng lỗi khi dùng parser thủ công | Spring container đã cấu hình resolver; StandardEvaluationContext tự tạo thì chưa. | Đăng ký BeanResolver rõ ràng trong context thủ công. |
| #beanName trả về null hoặc không có giá trị | Đang dùng cú pháp variable cho một bean reference. | Dùng @beanName cho bean; dùng #name cho variable đã đăng ký. |
| Method trên bean không gọi được | Method không truy cập được, sai số tham số hoặc kiểu đối số không tương thích. | Kiểm tra method signature và method resolver. |
| Bean scope không hoạt động | Request/session scope chưa hoạt động hoặc proxy không được cấu hình. | Đánh giá trong scope hợp lệ hoặc dùng scoped proxy phù hợp. |
| Giá trị @Value không cập nhật sau khi bean thay đổi | Expression đã được đánh giá lúc inject; scalar đã lưu không tự tính lại. | Inject bean và đọc giá trị tại thời điểm sử dụng. |
| Bean khởi tạo thất bại do circular dependency | Expression phân giải bean khác trong lúc dependency graph đang tạo vòng. | Đơn giản hóa dependency graph; tránh gọi method qua bean reference khi khởi tạo. |
| Expression có hành động ngoài ý muốn | Bean được expose có method ghi dữ liệu hoặc truy cập tài nguyên. | Thu hẹp bean allowlist; chỉ expose API thuần đọc và chuyển hành động sang service flow. |

## Ghi nhớ

- @beanName tham chiếu Spring bean qua BeanResolver; #variable tham chiếu biến trong EvaluationContext.
- Tên bean phải đúng với bean name hoặc alias; dùng dạng có nháy đơn nếu tên chứa ký tự đặc biệt.
- Spring expression infrastructure thường cấu hình bean resolver cho bean definitions và @Value.
- Khi tự tạo StandardEvaluationContext, cần đăng ký BeanFactoryResolver để dùng @beanName.
- Có thể đọc property, gọi method hoặc truy cập Map trên bean sau khi bean được phân giải.
- @Value và bean definition expressions thường được đánh giá trong quá trình tạo bean; giá trị scalar không tự cập nhật về sau.
- @&factoryName tham chiếu FactoryBean itself; @factoryName thông thường tham chiếu object do factory tạo ra.
- Scope singleton, prototype, request và session ảnh hưởng instance được phân giải.
- Dùng constructor injection khi class cần dependency để sử dụng trong code Java.
- Tránh circular dependency và method có side effect trong expression khởi tạo.
- Không đánh giá expression không tin cậy với toàn bộ ApplicationContext; giới hạn bean resolver và API được expose.
- SimpleEvaluationContext không hỗ trợ bean references.

## Tài liệu tham khảo

- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework Reference — Expression Support for Defining Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-expression-language.html)
- [Spring Framework Reference — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework API — BeanFactoryResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [Spring Framework API — StandardBeanExpressionResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/StandardBeanExpressionResolver.html)