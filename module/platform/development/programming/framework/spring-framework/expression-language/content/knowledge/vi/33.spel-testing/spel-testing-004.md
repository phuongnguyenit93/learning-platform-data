# Kiểm thử bean reference bằng context tối thiểu

Trong Spring Expression Language (SpEL), biểu thức **@beanName** tham chiếu đến một bean thông qua **BeanResolver** được đăng ký trong **EvaluationContext**. Khi kiểm thử tính năng này, không phải lúc nào cũng cần khởi động toàn bộ Spring ApplicationContext.

Một bài test tập trung vào SpEL có thể dùng:

- **StandardEvaluationContext** để đánh giá expression.
- **BeanFactoryResolver** để nối bean reference với một BeanFactory.
- **StaticListableBeanFactory** để đăng ký sẵn instance cần kiểm thử.
- **SpelExpressionParser** để parse expression có cú pháp @beanName.

Cách này kiểm tra đúng luồng phân giải bean của SpEL, đồng thời giữ test nhỏ và nhanh. Nó phù hợp khi muốn xác nhận expression tìm đúng bean, gọi được method hoặc đọc được property của bean đó.

## 1. Bean reference cần những thành phần nào?

Một expression như:

~~~text
@pricingService.calculate(#amount)
~~~

có ba thành phần cần phân biệt:

1. **@pricingService** là bean reference. SpEL yêu cầu BeanResolver tìm bean theo tên pricingService.
2. **calculate(...)** là method được gọi trên object mà resolver trả về.
3. **#amount** là variable được đọc từ EvaluationContext.

Chỉ có bean trong container là chưa đủ. EvaluationContext dùng để đánh giá expression cũng phải được cấu hình BeanResolver. Khi không có resolver, SpEL không biết cách tra cứu tên bean.

Trong Java, cấu hình cơ bản là:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

BeanFactoryResolver triển khai BeanResolver và ủy quyền việc tra cứu cho BeanFactory được truyền vào constructor. Khi expression yêu cầu pricingService, resolver gọi beanFactory.getBean("pricingService") và trả instance cho SpEL.

## 2. Vì sao dùng StaticListableBeanFactory trong unit test?

**StaticListableBeanFactory** là một BeanFactory nhẹ cho phép đăng ký các instance singleton đã được tạo sẵn bằng addBean(name, bean).

Ví dụ:

~~~java
StaticListableBeanFactory beanFactory =
        new StaticListableBeanFactory();

beanFactory.addBean("pricingService", new PricingService());
~~~

Sau đó nối factory vào EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

Ưu điểm của cách làm này:

- Không cần khởi động ApplicationContext.
- Không cần component scan hoặc cấu hình @Configuration.
- Không cần tạo bean definition cho một service chỉ dùng trong test.
- Có thể thay service thật bằng một instance test hoặc fake.
- Test tập trung vào việc SpEL phân giải tên bean và gọi member tương ứng.

Cần hiểu đúng phạm vi: StaticListableBeanFactory quản lý những instance đã đăng ký. Nó không tạo bean từ định nghĩa, không thực hiện dependency injection, không quản lý prototype scope và không hỗ trợ alias. Vì vậy, đây là lựa chọn tốt cho unit test bean reference, nhưng không thay thế kiểm thử tích hợp Spring container.

## 3. Ví dụ hoàn chỉnh: đăng ký bean và đánh giá expression

Giả sử có service:

~~~java
public class PricingService {

    public BigDecimal calculateDiscount(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.90"));
    }
}
~~~

Có thể kiểm thử bằng SpEL như sau:

~~~java
import java.math.BigDecimal;

import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class BeanReferenceTestExample {

    public static void main(String[] args) {
        PricingService pricingService = new PricingService();

        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        beanFactory.addBean("pricingService", pricingService);

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );
        context.setVariable("amount", new BigDecimal("100.00"));

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression = parser.parseExpression(
                "@pricingService.calculateDiscount(#amount)"
        );

        BigDecimal result = expression.getValue(
                context,
                BigDecimal.class
        );

        System.out.println(result); // 90.0000
    }
}
~~~

Luồng thực thi:

1. Tạo instance PricingService.
2. Đăng ký instance với tên pricingService trong StaticListableBeanFactory.
3. Tạo StandardEvaluationContext.
4. Gắn BeanFactoryResolver cho context.
5. Đăng ký variable amount.
6. Parse expression có @pricingService.
7. Gọi getValue() để SpEL resolve bean, gọi calculateDiscount() và trả kết quả.

Điểm quan trọng là tên trong addBean() phải khớp với tên trong expression. Nếu đăng ký pricingService nhưng expression viết @priceService, việc resolve sẽ thất bại.

## 4. Viết JUnit test cho bean reference

Ví dụ sau minh họa một test tập trung vào hành vi quan trọng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class BeanReferenceSpelTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void resolvesBeanAndInvokesItsMethod() {
        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        beanFactory.addBean(
                "pricingService",
                new PricingService()
        );

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );
        context.setVariable("amount", new BigDecimal("100.00"));

        BigDecimal result = parser
                .parseExpression(
                    "@pricingService.calculateDiscount(#amount)"
                )
                .getValue(context, BigDecimal.class);

        assertEquals(
                0,
                new BigDecimal("90.00").compareTo(result.setScale(2))
        );
    }

    public static class PricingService {

        public BigDecimal calculateDiscount(BigDecimal amount) {
            return amount.multiply(new BigDecimal("0.90"));
        }
    }
}
~~~

Test xác nhận ba việc cùng lúc:

- Bean name pricingService được resolve.
- Method calculateDiscount() được gọi trên instance đã đăng ký.
- Variable amount được lấy từ EvaluationContext và truyền vào method.

Trong dự án thực tế, nên đặt service test ở class riêng hoặc dùng fixture chung để các test dễ đọc. Ví dụ trên đặt service lồng trong test class để minh họa độc lập.

## 5. Tách bean reference khỏi root object và variable

Một lỗi phổ biến là nhầm ba cách truy cập sau:

| Cú pháp | Ý nghĩa | Nguồn |
| --- | --- | --- |
| **@pricingService** | Bean reference | BeanResolver / BeanFactory |
| **#amount** | Variable | EvaluationContext |
| **total** | Property trên root object hiện tại | Root object truyền vào getValue() |

Có thể kiểm tra cả ba trong cùng expression:

~~~java
Order order = new Order(new BigDecimal("100.00"));

context.setRootObject(order);
context.setVariable("minimumTotal", new BigDecimal("50.00"));
~~~

Expression:

~~~text
@pricingService.calculateDiscount(total + #minimumTotal)
~~~

Ở đây total được đọc từ root object Order, minimumTotal là variable và pricingService là bean reference.

Khi test thất bại, hãy xác định lỗi nằm ở đúng nguồn dữ liệu nào. BeanResolver không đăng ký variable, còn setVariable() cũng không tạo bean trong BeanFactory.

## 6. Kiểm thử trường hợp không tìm thấy bean

Một test tốt nên kiểm tra cả trường hợp bean tồn tại và trường hợp tên bean sai.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.EvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class MissingBeanReferenceTest {

    @Test
    void reportsFailureWhenBeanDoesNotExist() {
        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );

        assertThrows(EvaluationException.class, () ->
                new SpelExpressionParser()
                        .parseExpression("@missingService")
                        .getValue(context)
        );
    }
}
~~~

BeanFactoryResolver yêu cầu BeanFactory tìm bean theo tên. Nếu không có bean tương ứng, lỗi tra cứu được chuyển thành lỗi phân giải bean của SpEL.

Không nên phụ thuộc vào toàn bộ message text của exception trong assertion vì chi tiết thông báo có thể thay đổi theo phiên bản Spring. Hãy kiểm tra exception family hoặc nguyên nhân gốc nếu test cần xác nhận loại lỗi cụ thể.

## 7. Kiểm tra trường hợp thiếu BeanResolver

Bean có thể đã đăng ký trong factory nhưng EvaluationContext chưa được gắn resolver. Trường hợp này cũng phải thất bại:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        new SpelExpressionParser().parseExpression("@pricingService");

assertThrows(EvaluationException.class, () ->
        expression.getValue(context)
);
~~~

Test này giúp xác nhận rằng bean reference cần cấu hình resolver trong context. Chỉ tạo BeanFactory hoặc đăng ký bean không tự động liên kết factory đó với mọi EvaluationContext.

Trong ứng dụng Spring thực tế, các integration point như @Value hoặc module khác có thể tự cấu hình resolver cho expression context của chúng. Test parser độc lập cần tự cấu hình những thành phần đó.

## 8. Khi nào dùng SimpleEvaluationContext?

Không thể thay StandardEvaluationContext bằng SimpleEvaluationContext nếu expression cần cú pháp @beanName.

SimpleEvaluationContext được thiết kế cho một tập con tính năng SpEL và loại trừ bean references, type references và constructor invocation. Vì vậy, expression sau không phù hợp với context đó:

~~~text
@pricingService.calculateDiscount(#amount)
~~~

Với bean reference, hãy dùng StandardEvaluationContext và chỉ đăng ký BeanResolver cần thiết.

Nếu mục tiêu chỉ là đọc property hoặc lọc dữ liệu, SimpleEvaluationContext có thể phù hợp hơn. Hãy chọn context dựa trên tính năng expression thực sự sử dụng.

## 9. Khi nào cần ApplicationContext thật?

StaticListableBeanFactory đủ cho một unit test chỉ cần tra cứu một instance có sẵn. Tuy nhiên, nó không kiểm tra toàn bộ hành vi của Spring container.

Dùng AnnotationConfigApplicationContext, GenericApplicationContext hoặc context test của Spring khi cần xác nhận:

- Component scanning hoặc @Bean method đăng ký đúng bean name.
- Constructor injection và setter injection hoạt động.
- Bean được tạo từ BeanDefinition.
- Scope, lazy initialization hoặc FactoryBean hoạt động đúng.
- AOP proxy hoặc transaction proxy được trả về như mong muốn.
- Cấu hình thực tế của ứng dụng tạo ra đúng BeanResolver.
- Integration point như @Value, Cache hoặc Method Security cung cấp context phù hợp.

Một integration test có thể khởi tạo context thật, lấy BeanFactory từ context rồi gắn BeanFactoryResolver vào StandardEvaluationContext. Nếu mục tiêu chỉ là xác nhận cú pháp @beanName và method invocation, hãy giữ test ở mức tối thiểu để tránh chi phí khởi tạo không cần thiết.

## 10. Dùng custom BeanResolver khi không cần BeanFactory

SpEL không bắt buộc phải dùng BeanFactoryResolver. EvaluationContext chỉ yêu cầu một implementation BeanResolver.

Nếu test muốn kiểm tra riêng parser và expression, có thể cung cấp resolver nhỏ ánh xạ tên sang instance:

~~~java
BeanResolver resolver = (evaluationContext, beanName) -> {
    if ("pricingService".equals(beanName)) {
        return pricingService;
    }
    throw new AccessException("Unknown bean: " + beanName);
};

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(resolver);
~~~

Cách này phù hợp khi muốn cô lập SpEL khỏi BeanFactory. Tuy nhiên, nếu mục tiêu của test là kiểm tra chính BeanFactoryResolver, hãy dùng StaticListableBeanFactory như ví dụ trước.

Custom resolver cần xác định rõ tên nào được phép, cách xử lý tên không tồn tại và loại exception được ném ra. Không nên viết resolver chỉ trả về một object bất kể beanName, vì test khi đó không kiểm tra hành vi phân giải theo tên.

## 11. Tên bean đặc biệt và FactoryBean

Nếu bean name chứa dấu chấm hoặc ký tự đặc biệt, SpEL yêu cầu đặt tên trong string literal:

~~~text
@'billing.pricing-service'
~~~

Tên này phải khớp với tên mà resolver có thể tra cứu.

Nếu bean là FactoryBean và cần lấy chính factory thay vì object do factory tạo ra, SpEL hỗ trợ prefix **&**:

~~~text
@&pricingFactory
~~~

Khả năng này chỉ có ý nghĩa khi BeanFactory và cấu hình bean thực tế hỗ trợ FactoryBean. StaticListableBeanFactory phù hợp với instance singleton thông thường và không phải lựa chọn để kiểm thử đầy đủ FactoryBean lifecycle.

## 12. Những lỗi thường gặp khi kiểm thử bean reference

1. **Quên setBeanResolver():** expression dùng @beanName nhưng EvaluationContext không có resolver.
2. **Tên bean không khớp:** tên trong addBean() khác tên sau ký hiệu @.
3. **Dùng SimpleEvaluationContext:** context này không hỗ trợ bean reference.
4. **Nhầm bean với variable:** #pricingService là variable, còn @pricingService là bean reference.
5. **Method không truy cập được:** bean đã resolve nhưng method không có, không public hoặc đối số không tương thích.
6. **Đăng ký nhầm instance:** factory chứa object khác với object mà test đang kỳ vọng.
7. **Kỳ vọng StaticListableBeanFactory tạo bean:** factory này chỉ giữ instance đã đăng ký sẵn.
8. **Kiểm thử quá nhiều thứ trong một test:** lỗi DI, proxy, scope và lỗi SpEL có thể bị trộn lẫn nếu khởi động cả ứng dụng cho một assertion nhỏ.
9. **Assert message exception quá chặt:** message có thể thay đổi theo phiên bản Spring.
10. **Cho rằng unit test thay thế integration test:** resolver test không chứng minh component scan, bean lifecycle hoặc proxy production đã được cấu hình đúng.

## 13. Ghi nhớ nhanh

- Bean reference trong SpEL dùng cú pháp **@beanName**.
- EvaluationContext phải có BeanResolver để phân giải bean reference.
- **BeanFactoryResolver** kết nối SpEL với BeanFactory và gọi getBean() theo tên.
- **StaticListableBeanFactory** cho phép đăng ký instance singleton có sẵn bằng addBean().
- Kết hợp StaticListableBeanFactory, BeanFactoryResolver và StandardEvaluationContext để viết unit test gọn.
- Đăng ký variable bằng setVariable() nếu expression cần đối số như #amount.
- SimpleEvaluationContext không hỗ trợ bean reference.
- Test bean không tồn tại và context thiếu resolver để kiểm tra lỗi cấu hình.
- StaticListableBeanFactory không kiểm tra dependency injection, bean definitions, prototype scope, aliases hoặc ApplicationContext lifecycle.
- Dùng ApplicationContext thật cho integration test cần component scan, proxy, scope hoặc wiring của ứng dụng.
- Dùng custom BeanResolver nếu muốn cô lập expression khỏi BeanFactory.
- Không đặt side effect hoặc thao tác production thật trong test bean reference; dùng fake hoặc instance test có hành vi xác định.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Bean References in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [StaticListableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/support/StaticListableBeanFactory.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
