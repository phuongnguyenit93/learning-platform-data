# Bean name có ký tự đặc biệt và cú pháp tham chiếu

## Mục tiêu

Sau bài này, bạn có thể tham chiếu một Spring bean trong Spring Expression Language (SpEL); phân biệt cú pháp bean reference với biến và thuộc tính thông thường; viết đúng tên bean có dấu chấm hoặc ký tự đặc biệt bằng string literal; cấu hình BeanResolver khi tự tạo EvaluationContext; và hiểu cách tham chiếu FactoryBean. Bạn cũng sẽ biết cách xử lý lỗi phân giải bean và giới hạn những bean mà biểu thức được phép truy cập.

## 1. Bean reference trong SpEL là gì?

SpEL có thể lấy một bean từ Spring container bằng ký hiệu @ đứng trước tên bean. Ví dụ:

~~~text
@orderService
~~~

Biểu thức yêu cầu BeanResolver của EvaluationContext tìm bean có tên orderService và trả về đối tượng tương ứng.

Có thể dùng bean reference như một giá trị trong biểu thức, đọc thuộc tính hoặc gọi phương thức của bean:

~~~text
@pricingService.defaultCurrency
~~~

~~~text
@pricingService.calculate(#order)
~~~

Trong ví dụ thứ hai, SpEL lấy bean pricingService, sau đó gọi phương thức calculate(...) với biến #order.

Bean reference giúp biểu thức kết nối với các thành phần nghiệp vụ đã được Spring quản lý. Nó không tạo bean mới và cũng không tìm bean theo kiểu Java một cách tự động; nó yêu cầu phân giải theo tên bean.

## 2. Cú pháp tham chiếu bean thông thường

Với tên bean đơn giản, thường dùng trực tiếp:

~~~text
@orderService
@inventoryService
@customerRepository
~~~

Dấu @ cho parser biết đây là bean reference. Phần tên phía sau được chuyển cho BeanResolver để tìm đối tượng.

Ví dụ Java với một EvaluationContext được tạo thủ công:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

Expression expression =
    parser.parseExpression("@orderService");

Object orderService = expression.getValue(context);
~~~

BeanFactoryResolver là adapter có sẵn để dùng một BeanFactory làm nơi phân giải bean. ApplicationContext cũng là một BeanFactory, nên có thể truyền trực tiếp vào constructor như ví dụ.

Nếu ứng dụng có một BeanResolver tùy chỉnh, có thể đăng ký resolver đó bằng context.setBeanResolver(...). Resolver chịu trách nhiệm nhận tên bean và trả về đối tượng phù hợp.

## 3. Vì sao tên bean có ký tự đặc biệt cần đặt trong dấu nháy?

Tên bean thông thường thường dùng chữ và số theo quy ước camelCase. Tuy nhiên, Spring cho phép tên hoặc alias chứa dấu chấm và các ký tự đặc biệt khác.

Trong cú pháp SpEL, dấu chấm còn có ý nghĩa truy cập thuộc tính hoặc gọi phương thức. Vì vậy, nếu tên bean chứa dấu chấm hoặc ký tự đặc biệt, parser cần biết toàn bộ phần đó là một tên bean duy nhất.

Hãy đặt tên bean dưới dạng string literal trong dấu nháy đơn:

~~~text
@'order.service'
~~~

Một số ví dụ:

~~~text
@'order.service'
@'payment-service'
@'legacy$processor'
~~~

Không viết tên có dấu chấm như một bean reference thông thường:

~~~text
@order.service
~~~

Cách viết trên có thể được hiểu là tham chiếu bean order rồi truy cập thuộc tính service, thay vì tìm bean có tên order.service.

Khi dùng string literal, dấu nháy bao trọn tên bean. Parser sau đó chuyển chính xác tên đó cho BeanResolver.

## 4. Dùng bean có tên đặc biệt trong biểu thức lớn

Sau khi tham chiếu được bean, có thể tiếp tục truy cập thuộc tính, gọi phương thức hoặc kết hợp với toán tử khác.

Ví dụ đọc thuộc tính:

~~~text
@'order.service'.defaultCurrency
~~~

Ví dụ gọi phương thức:

~~~text
@'payment-service'.authorize(#payment)
~~~

Ví dụ kết hợp với điều kiện:

~~~text
@'feature.toggle'.isEnabled('new-checkout') and #order.total > 0
~~~

Tên bean vẫn là một string literal được đặt sau dấu @. Phần sau tên bean là thao tác trên đối tượng mà resolver trả về.

Các phương thức được gọi phải tồn tại và có thể truy cập theo cấu hình method resolver của EvaluationContext. Việc phân giải bean thành công không bảo đảm mọi lời gọi phương thức hoặc truy cập thuộc tính tiếp theo đều hợp lệ.

## 5. Cấu hình BeanResolver khi tự tạo context

Một StandardEvaluationContext mới không tự biết Spring container của ứng dụng. Nếu tự tạo parser và context ngoài cơ chế xử lý biểu thức của Spring, cần đăng ký BeanResolver.

Ví dụ dùng BeanFactoryResolver:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SpelBeanLookup {

    public Object findOrderService(ApplicationContext applicationContext) {
        ExpressionParser parser = new SpelExpressionParser();

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setBeanResolver(
            new BeanFactoryResolver(applicationContext)
        );

        Expression expression =
            parser.parseExpression("@orderService");

        return expression.getValue(context);
    }
}
~~~

Trong ví dụ:

1. Parser phân tích biểu thức @orderService.
2. Context được gắn với BeanFactoryResolver.
3. Khi đánh giá, SpEL gọi resolver để tìm bean có tên orderService.
4. Kết quả là instance do Spring container quản lý.

Nếu bỏ qua setBeanResolver(...), một bean reference trong context thủ công sẽ không có resolver để xử lý và có thể phát sinh SpelEvaluationException với thông báo không có BeanResolver được đăng ký.

Không cần tự đăng ký resolver trong mọi tình huống. Khi biểu thức được đánh giá bởi cơ chế tích hợp của Spring, chẳng hạn xử lý @Value, framework cung cấp ngữ cảnh bean phù hợp. Hãy kiểm tra cách biểu thức được tạo và đánh giá trước khi cấu hình thủ công lần nữa.

## 6. Bean reference trong @Value

Trong mã Java, @Value là annotation của Spring. Bên trong chuỗi SpEL của annotation, ký hiệu @ cũng được dùng để tham chiếu bean.

Ví dụ:

~~~java
@Component
public class CheckoutConfiguration {

    private final String currency;

    public CheckoutConfiguration(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }
}
~~~

Ở đây:

- @Value là annotation yêu cầu Spring lấy giá trị cho tham số constructor.
- #{ ... } đánh dấu phần biểu thức SpEL.
- @pricingService là bean reference bên trong biểu thức.
- .defaultCurrency đọc thuộc tính từ bean đã phân giải.

Có thể dùng tên bean có ký tự đặc biệt trong SpEL của @Value:

~~~java
@Value("#{ @'order.service'.defaultCurrency }")
private String currency;
~~~

Cần phân biệt ký hiệu @ của annotation Java với ký hiệu @ trong ngôn ngữ SpEL. Ý nghĩa của ký hiệu trong từng vị trí phụ thuộc vào cú pháp bao quanh nó.

## 7. Tên bean, alias và cách phân giải

Một bean trong Spring có thể có tên chính và một hoặc nhiều alias. Bean reference có thể dùng tên hoặc alias mà container nhận diện.

Ví dụ khai báo bean với alias trong Java configuration:

~~~java
@Bean(name = {"orderService", "order.service"})
public OrderService orderService() {
    return new OrderService();
}
~~~

Có thể tham chiếu bằng tên đơn giản:

~~~text
@orderService
~~~

Hoặc dùng alias có dấu chấm dưới dạng string literal:

~~~text
@'order.service'
~~~

Cả hai tên đều trỏ đến cùng bean nếu container đã đăng ký chúng như alias của nhau.

Khi đặt tên bean, nên ưu tiên tên đơn giản, dễ đọc và nhất quán. Alias có ký tự đặc biệt hữu ích khi cần tương thích cấu hình cũ hoặc tích hợp với một quy ước đặt tên bên ngoài. Trong biểu thức SpEL, luôn dùng đúng tên hoặc alias đã được đăng ký.

Tên bean được phân giải theo tên chính xác. Không nên giả định parser tự bỏ dấu gạch nối, chuyển chữ hoa thành chữ thường hoặc tìm bean gần giống khi tên không tồn tại.

## 8. Tham chiếu FactoryBean

FactoryBean là một cơ chế của Spring cho phép một bean tạo ra đối tượng khác. Khi tham chiếu bean theo tên thông thường, container trả về sản phẩm do FactoryBean tạo ra.

Nếu cần truy cập chính FactoryBean, dùng tiền tố & trước tên bean:

~~~text
&orderServiceFactory
~~~

BeanResolver nhận tên &orderServiceFactory và yêu cầu container trả về factory instance thay vì sản phẩm của factory.

Có thể phân biệt:

| Cách tham chiếu | Đối tượng được yêu cầu |
|---|---|
| @orderServiceFactory | Sản phẩm do FactoryBean tạo ra |
| &orderServiceFactory | Chính FactoryBean |

Đây là khác biệt về đối tượng được lấy từ container. Chỉ dùng tiền tố & khi thực sự cần thao tác với factory, ví dụ kiểm tra cấu hình hoặc trạng thái của factory.

Tài liệu Spring mô tả tên gửi cho BeanResolver có tiền tố & khi yêu cầu FactoryBean. Nếu bean factory được tham chiếu có tên đặc biệt, hãy kiểm tra cú pháp parser của phiên bản Spring đang sử dụng và bảo đảm tên được chuyển nguyên vẹn tới resolver.

## 9. Phân biệt bean reference, biến và thuộc tính

Ba cách viết dưới đây không có cùng ý nghĩa:

| Cú pháp | Ý nghĩa |
|---|---|
| @orderService | Lấy bean tên orderService qua BeanResolver |
| #orderService | Đọc biến orderService trong EvaluationContext |
| orderService | Đọc thuộc tính orderService từ root object hiện tại |

Ví dụ, ứng dụng có thể đồng thời đăng ký một bean và một biến cùng tên:

~~~java
context.setVariable("orderService", serviceMock);
~~~

Trong SpEL:

~~~text
@orderService
~~~

tham chiếu bean được resolver tìm trong container.

~~~text
#orderService
~~~

đọc biến serviceMock đã được đăng ký vào context.

Không có tiền tố @ hoặc #, parser sẽ tìm thuộc tính trên root object theo quy tắc truy cập property. Hãy dùng đúng tiền tố để tránh tham chiếu nhầm nguồn dữ liệu.

## 10. Kết hợp bean reference với biến và root object

Bean reference có thể phối hợp với dữ liệu được truyền vào context:

~~~text
@pricingService.calculate(#order, #discountRate)
~~~

Trong ví dụ:

- @pricingService lấy service từ container.
- #order lấy đơn hàng từ biến context.
- #discountRate lấy tỷ lệ giảm giá từ biến context.
- calculate(...) gọi phương thức của service.

Cũng có thể dùng root object:

~~~text
@authorizationService.canAccess(authentication, resourceId)
~~~

Trong trường hợp này, authentication và resourceId được đọc từ root object nếu đó là các thuộc tính có thể truy cập.

Hãy tách rõ trách nhiệm: container cung cấp collaborator, còn EvaluationContext cung cấp dữ liệu đầu vào cho biểu thức. Không nên nhúng dữ liệu người dùng trực tiếp vào chuỗi tên bean hoặc nối chuỗi để tạo biểu thức động nếu có thể truyền dữ liệu qua biến.

## 11. Lỗi thường gặp khi tham chiếu bean

Một số lỗi phổ biến:

- **Không có BeanResolver:** context thủ công chưa gọi setBeanResolver(...).
- **Sai tên bean:** tên hoặc alias không được đăng ký trong container.
- **Quên dấu nháy cho tên đặc biệt:** tên có dấu chấm hoặc ký tự đặc biệt chưa được đặt trong string literal.
- **Nhầm bean reference với biến:** dùng @name trong khi dữ liệu thực tế chỉ được đăng ký bằng setVariable.
- **Nhầm FactoryBean với sản phẩm:** quên tiền tố & khi cần chính factory.
- **Lỗi truy cập sau khi phân giải:** bean đã được tìm thấy nhưng property hoặc method tiếp theo không tồn tại hoặc không thể truy cập.
- **Bean tạo sản phẩm thất bại:** FactoryBean ném lỗi khi container yêu cầu sản phẩm.

Khi gỡ lỗi, hãy tách quá trình thành hai bước: kiểm tra resolver có tìm được bean đúng tên hay không, rồi kiểm tra biểu thức có truy cập được thuộc tính hoặc phương thức mong muốn trên đối tượng trả về hay không.

Không nên bắt mọi lỗi SpEL rồi trả về null như thể bean reference thành công. Hãy ghi nhận tên bean và nguyên nhân phân giải để sửa cấu hình hoặc đăng ký bean chính xác.

## 12. Giới hạn quyền truy cập bean

Một bean reference có thể mở ra nhiều khả năng hơn một phép đọc thuộc tính. Sau khi lấy được bean, biểu thức có thể gọi phương thức mà EvaluationContext cho phép. Nếu bean là service có quyền ghi dữ liệu, gửi thông điệp hoặc thực hiện giao dịch, biểu thức có thể kích hoạt hành động đó.

Vì vậy:

1. Chỉ đăng ký BeanResolver khi biểu thức thực sự cần bean.
2. Không cung cấp toàn bộ ApplicationContext cho biểu thức không đáng tin cậy.
3. Với biểu thức đến từ người dùng hoặc nguồn bên ngoài, cân nhắc một BeanResolver chỉ cho phép danh sách bean được chọn.
4. Chỉ phơi bày các phương thức cần thiết và có tác dụng rõ ràng.
5. Tránh để biểu thức cấu hình gọi những phương thức thay đổi trạng thái nếu mục đích chỉ là tính toán hoặc đọc dữ liệu.
6. Kiểm tra quyền và dữ liệu đầu vào trong service Java; không dựa vào cú pháp SpEL để thay thế kiểm soát nghiệp vụ.

BeanResolver là một phần của ranh giới quyền truy cập. Việc giới hạn bean được tham chiếu giúp giảm khả năng biểu thức gọi nhầm hoặc gọi tùy ý các thành phần trong ứng dụng.

## 13. Ví dụ tổng hợp

Giả sử Spring container có một bean service tên thông thường và một alias chứa dấu chấm. Có thể đánh giá cả hai dạng:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

Expression regularReference =
    parser.parseExpression("@pricingService");

Expression specialNameReference =
    parser.parseExpression("@'order.service'");

Object pricingService =
    regularReference.getValue(context);

Object orderService =
    specialNameReference.getValue(context);
~~~

Nếu hai tên được đăng ký như hai alias của cùng một bean, hai biểu thức trả về cùng một instance do container quản lý.

Ví dụ gọi phương thức của bean có tên đặc biệt:

~~~java
Expression calculate = parser.parseExpression(
    "@'order.service'.calculate(#order)"
);

context.setVariable("order", order);

Object total = calculate.getValue(context);
~~~

Biểu thức này phân giải bean trước, rồi gọi phương thức trên đối tượng được trả về. Kiểu và giá trị của biến order phải tương thích với chữ ký phương thức calculate.

## 14. Kiểm thử bean reference

Khi kiểm thử một biểu thức có bean reference, hãy bao gồm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Tên bean thông thường | Resolver trả về đúng bean |
| Tên có dấu chấm | Dùng dạng string literal, ví dụ @'order.service' |
| Tên có dấu gạch nối hoặc ký tự đặc biệt | Parser nhận toàn bộ tên như một literal |
| Alias của bean | Alias phân giải về cùng instance |
| Context không có resolver | Phát hiện lỗi thiếu BeanResolver |
| Tên bean không tồn tại | Phát hiện lỗi phân giải bean |
| Bean reference kết hợp method call | Phương thức và đối số được truy cập đúng |
| Bean reference kết hợp property | Thuộc tính có thể đọc và có kiểu mong muốn |
| FactoryBean thông thường | Nhận sản phẩm của factory |
| Tiền tố & | Nhận chính FactoryBean |
| Biến cùng tên với bean | Phân biệt @name và #name |

Nên kiểm thử bằng Spring context hoặc BeanFactory có cấu hình gần với môi trường chạy thật. Một mock BeanResolver có thể hữu ích cho unit test, nhưng không thay thế kiểm tra tích hợp với quy tắc tên bean và alias của container.

## 15. Ghi nhớ

Bean reference trong SpEL dùng ký hiệu @ để lấy bean qua BeanResolver. Tên thông thường có thể viết trực tiếp như @orderService. Nếu tên có dấu chấm hoặc ký tự đặc biệt, hãy đặt toàn bộ tên trong string literal, ví dụ @'order.service'.

Khi tự tạo StandardEvaluationContext, cần đăng ký BeanResolver, thường có thể dùng BeanFactoryResolver với ApplicationContext hoặc BeanFactory. Cơ chế tích hợp của Spring như xử lý @Value đã cung cấp ngữ cảnh phân giải bean phù hợp.

Tiền tố & dùng để yêu cầu chính FactoryBean thay vì sản phẩm mà factory tạo ra. Bean reference khác biến #name và thuộc tính root object không có tiền tố.

Hãy dùng tên bean chính xác, kiểm tra alias và resolver, phân biệt lỗi phân giải với lỗi truy cập property hoặc method sau đó. Chỉ cung cấp những bean mà biểu thức thực sự cần, đặc biệt khi biểu thức đến từ nguồn không đáng tin cậy.

## Tài liệu tham khảo

- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)