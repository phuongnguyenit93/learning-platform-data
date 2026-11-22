# Tham chiếu bean trong ApplicationContext với Spring Expression Language

Spring Expression Language (SpEL) có thể tham chiếu trực tiếp đến một bean do Spring quản lý bằng tên bean. Cú pháp này giúp biểu thức đọc property hoặc gọi method trên một thành phần trong ApplicationContext, ví dụ \`@pricingService.calculateTotal(...)\`.

Để giải quyết một bean reference, SpEL cần một \`BeanResolver\` trong EvaluationContext. Trong ứng dụng Spring, cơ chế tích hợp sẵn thường kết nối resolver với BeanFactory của ApplicationContext. Khi tự tạo EvaluationContext bằng Java, ứng dụng cần cấu hình resolver nếu muốn dùng cú pháp \`@beanName\`.

## 1. Bean reference là gì?

Bean là một object được Spring IoC container tạo, cấu hình và quản lý vòng đời. Bean có thể được đăng ký qua component scanning, annotation cấu hình, XML hoặc các cơ chế đăng ký bean khác.

SpEL dùng ký hiệu \`@\` để tham chiếu bean theo tên:

~~~spel
@pricingService
~~~

Biểu thức trên yêu cầu resolver tìm bean có tên \`pricingService\` trong BeanFactory được cấu hình.

Sau khi lấy được bean, biểu thức có thể tiếp tục truy cập property hoặc gọi method:

~~~spel
@pricingService.defaultCurrency
@pricingService.calculateTotal(#order)
~~~

Bean reference không tự tạo một object mới bằng toán tử \`new\`. Nó yêu cầu Spring container cung cấp bean đã được quản lý theo tên hoặc alias.

## 2. Phân biệt bean reference, variable và root property

Ba cách viết dưới đây có ý nghĩa khác nhau:

| Cú pháp | Nguồn giá trị | Ý nghĩa |
|---|---|---|
| \`@pricingService\` | BeanResolver / BeanFactory | Lấy bean Spring theo tên |
| \`#minimum\` | Biến trong EvaluationContext | Lấy giá trị biến được đăng ký |
| \`customer\` | Root object hoặc object hiện tại | Đọc property trên object đang xét |

Ví dụ:

~~~spel
@pricingService.calculate(#order, #minimum)
~~~

Trong biểu thức này:

- \`@pricingService\` là bean được giải quyết từ container.
- \`#order\` là biến được đăng ký trong EvaluationContext.
- \`#minimum\` là một biến khác trong cùng context.
- \`calculate(...)\` là method được gọi trên bean đã tìm được.

Không nên thay \`@pricingService\` bằng \`#pricingService\` trừ khi ứng dụng thực sự đăng ký một biến có tên \`pricingService\`. Bean name và variable name là hai namespace khác nhau.

## 3. BeanResolver chịu trách nhiệm phân giải bean

SpEL định nghĩa interface \`BeanResolver\` để tách việc tìm bean khỏi cú pháp biểu thức. Khi gặp một bean reference, SpEL gọi resolver được cấu hình trong EvaluationContext.

Spring cung cấp \`BeanFactoryResolver\`, một triển khai dùng BeanFactory để tìm bean theo tên. Vì ApplicationContext kế thừa các khả năng của BeanFactory, có thể dùng ApplicationContext làm nguồn cho resolver.

Luồng xử lý:

~~~text
Biểu thức: @pricingService
          |
          v
SpEL nhận diện bean reference
          |
          v
EvaluationContext lấy BeanResolver
          |
          v
BeanFactoryResolver.resolve(...)
          |
          v
BeanFactory.getBean("pricingService")
          |
          v
Bean Spring được trả về
          |
          v
SpEL tiếp tục đọc property hoặc gọi method
~~~

Nếu context không có BeanResolver, SpEL không thể giải quyết cú pháp bean reference. Nếu resolver có nhưng không tìm thấy bean theo tên, evaluation cũng thất bại.

## 4. Cấu hình BeanFactoryResolver thủ công

Khi ứng dụng tự tạo \`StandardEvaluationContext\`, có thể kết nối nó với ApplicationContext hoặc BeanFactory bằng \`BeanFactoryResolver\`.

Ví dụ:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.context.expression.BeanFactoryResolver;

ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("@pricingService.defaultCurrency");

String currency =
    expression.getValue(context, String.class);
~~~

Ở đây:

1. ApplicationContext là container cung cấp bean.
2. BeanFactoryResolver kết nối SpEL với container.
3. setBeanResolver đăng ký resolver trên EvaluationContext.
4. Biểu thức \`@pricingService.defaultCurrency\` lấy bean theo tên rồi đọc property.
5. getValue trả giá trị property theo kiểu String được yêu cầu.

Nếu chỉ tạo một StandardEvaluationContext mà không gọi setBeanResolver, bean reference sẽ không tự động hoạt động trong context đó.

## 5. Gọi method trên bean

Một ứng dụng thường tham chiếu bean để gọi service hoặc policy đã được Spring quản lý.

Giả sử có service:

~~~java
public class PricingService {
    public BigDecimal calculateTotal(
            BigDecimal price,
            int quantity) {
        return price.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Bean được đăng ký với tên \`pricingService\`. Có thể gọi method từ SpEL:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "@pricingService.calculateTotal(#price, #quantity)"
);

BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Kết quả:

~~~text
750000
~~~

SpEL thực hiện hai việc liên tiếp:

- BeanResolver tìm bean \`pricingService\`.
- MethodResolver tìm và gọi method \`calculateTotal\` trên object bean đó.

Bean resolution và method resolution là hai bước khác nhau. Bean có thể được tìm thấy thành công nhưng method call vẫn thất bại nếu tên method, chữ ký hoặc quyền truy cập không phù hợp.

## 6. Tham chiếu bean trong @Value

Trong ứng dụng Spring, bean reference thường xuất hiện bên trong SpEL expression dùng với annotation \`@Value\`.

Ví dụ:

~~~java
@Component
public class InvoiceSettings {

    @Value("#{ @taxPolicy.defaultRate }")
    private BigDecimal taxRate;

    public BigDecimal getTaxRate() {
        return taxRate;
    }
}
~~~

Giả sử bean có tên \`taxPolicy\` và có property \`defaultRate\`. Spring đánh giá biểu thức trong quá trình xử lý dependency injection và gán giá trị vào field \`taxRate\`.

Có thể gọi method của bean trong biểu thức:

~~~java
@Value("#{ @currencyPolicy.defaultCurrency() }")
private String currency;
~~~

Trong môi trường Spring được cấu hình thông thường, cơ chế expression resolver tích hợp với BeanFactory nên bean reference có thể được giải quyết mà không cần tự tạo StandardEvaluationContext cho từng annotation.

Cần phân biệt cú pháp:

- \`@Value(...)\` là annotation của Spring dùng để cung cấp giá trị cho field, parameter hoặc method.
- \`#{...}\` bao quanh một SpEL expression trong chuỗi annotation.
- \`@taxPolicy\` bên trong expression là bean reference.

## 7. Tên bean, alias và tên có ký tự đặc biệt

Bean thường được tham chiếu bằng tên đăng ký:

~~~spel
@pricingService
@taxPolicy
~~~

Nếu BeanFactory đăng ký alias cho bean, alias cũng có thể được dùng khi resolver hỗ trợ tra cứu alias thông qua BeanFactory.

Với tên bean chứa ký tự đặc biệt hoặc dấu chấm, có thể đặt tên trong dấu nháy đơn:

~~~spel
@'pricing.service'
~~~

Cách viết này giúp parser phân biệt tên bean với phần cú pháp còn lại của biểu thức.

Tên bean phải khớp với tên hoặc alias được đăng ký trong container. Nếu viết sai tên, resolver không tìm thấy bean và evaluation thất bại.

## 8. Tham chiếu FactoryBean bằng ký hiệu &

Spring có loại bean đặc biệt gọi là \`FactoryBean\`. Khi tra cứu bean do FactoryBean tạo ra, BeanFactory thường trả về object sản phẩm của factory.

Nếu muốn tham chiếu chính object FactoryBean, dùng tiền tố \`&\` trước tên bean:

~~~spel
@&myFactory
~~~

Trong đó:

- \`@myFactory\` tham chiếu sản phẩm được FactoryBean cung cấp.
- \`@&myFactory\` tham chiếu chính FactoryBean.

Ví dụ, nếu bean có tên \`clientFactory\`, biểu thức \`@&clientFactory\` yêu cầu container trả về factory object thay vì sản phẩm của nó.

Cú pháp này chỉ phù hợp khi tên bean tương ứng với một FactoryBean. Với bean thông thường, không có lý do để thêm tiền tố \`&\`.

## 9. Bean reference và vòng đời bean

Bean reference được giải quyết thông qua BeanFactory, vì vậy hành vi phụ thuộc vào scope của bean.

| Scope | Hành vi khi lấy bean |
|---|---|
| singleton | Container dùng chung một instance trong phạm vi singleton của BeanFactory |
| prototype | Container tạo instance mới cho mỗi lần yêu cầu bean |
| request | Instance gắn với HTTP request hiện tại |
| session | Instance gắn với HTTP session hiện tại |
| application | Instance gắn với ServletContext |
| custom scope | Theo quy tắc của Scope do ứng dụng đăng ký |

Ví dụ, bean singleton thường trả về cùng instance khi được tham chiếu ở các lần đánh giá khác nhau trong cùng BeanFactory. Bean prototype có thể trả về instance mới khi resolver thực hiện một lần tra cứu mới.

Các scope gắn với web như request hoặc session cần scope tương ứng đang hoạt động. Nếu expression được đánh giá ngoài phạm vi hợp lệ, BeanFactory có thể phát sinh lỗi do scope chưa được kích hoạt.

Bean reference vì vậy giữ lại cơ chế quản lý vòng đời của Spring. Nó không tương đương với việc tự gọi constructor bằng Java.

## 10. Bean reference và AOP proxy

Nếu bean được Spring bọc bằng AOP proxy, việc giải quyết bean thông qua BeanFactory thường trả về object mà container quản lý, có thể chính là proxy.

Khi SpEL gọi method trên bean reference:

~~~spel
@accountService.loadAccount(#accountId)
~~~

lời gọi được thực hiện trên object được container cung cấp. Nếu đó là proxy, các interceptor tương ứng như transaction, security hoặc logging có thể tham gia theo cấu hình AOP.

Điều này là một lý do nên tham chiếu bean thông qua container thay vì tự tạo một instance bằng \`new\`: ứng dụng tiếp tục sử dụng object đã được Spring cấu hình và quản lý.

## 11. Bean reference trong template expression

Bean reference cũng có thể xuất hiện trong template expression nếu parser được cung cấp ParserContext phù hợp.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Tổng tiền: #{ @pricingService.calculateTotal(#price, #quantity) }",
    templateContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);
context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);

String message =
    expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Tổng tiền: 750000
~~~

ParserContext xác định phần văn bản và phần SpEL trong template. BeanResolver vẫn thuộc EvaluationContext và chịu trách nhiệm tìm bean lúc đánh giá.

Hai thành phần này có nhiệm vụ khác nhau: ParserContext quyết định cách phân tích chuỗi; EvaluationContext cung cấp môi trường thực thi.

## 12. Những lỗi thường gặp khi tham chiếu bean

### 12.1. Không có BeanResolver

Biểu thức:

~~~spel
@pricingService
~~~

không thể được giải quyết nếu EvaluationContext không có BeanResolver.

Với context tự tạo, hãy đăng ký:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);
~~~

Trong môi trường Spring tích hợp sẵn, hãy kiểm tra expression resolver có được kết nối đúng với BeanFactory không.

### 12.2. Sai tên bean hoặc alias

Nếu bean không được đăng ký với tên được viết trong expression, BeanFactoryResolver không thể tìm thấy nó.

Kiểm tra:

- Tên bean thực tế.
- Alias đã đăng ký.
- Phân biệt chữ hoa và chữ thường.
- Tên chứa dấu chấm hoặc ký tự đặc biệt có được đặt trong dấu nháy đơn đúng cách không.

### 12.3. Bean được tìm thấy nhưng property hoặc method không tồn tại

Ví dụ:

~~~spel
@pricingService.unknownMethod()
~~~

BeanResolver có thể tìm thấy bean thành công, nhưng MethodResolver không tìm được method tương ứng. Tương tự, property access có thể thất bại nếu bean không có property hoặc accessor phù hợp.

Cần phân biệt lỗi lấy bean với lỗi thao tác trên bean sau khi đã lấy được.

### 12.4. Scope không hoạt động

Nếu bean thuộc request scope hoặc session scope nhưng expression được đánh giá ngoài phạm vi web tương ứng, việc lấy bean có thể thất bại.

Hãy kiểm tra nơi và thời điểm expression được đánh giá, cũng như scope của bean.

### 12.5. Lỗi khởi tạo hoặc dependency của bean

BeanFactory có thể tìm thấy định nghĩa bean nhưng quá trình tạo instance gặp lỗi vì dependency, constructor hoặc lifecycle callback thất bại.

Trong trường hợp đó, lỗi không phải do cú pháp bean reference. Cần xem exception gốc từ quá trình khởi tạo bean.

## 13. Kiểm soát quyền truy cập qua bean reference

Bean reference có thể mở đường đến service, repository hoặc các thành phần có quyền thay đổi trạng thái ứng dụng. Vì vậy, expression có thể thực hiện nhiều hơn việc đọc dữ liệu.

Ví dụ:

~~~spel
@accountService.disableAccount(#accountId)
~~~

Nếu method được phép gọi và bean được giải quyết, biểu thức có thể thực hiện một thao tác nghiệp vụ thực sự.

Khi đánh giá expression lấy từ người dùng hoặc nguồn không đáng tin cậy, không nên cung cấp một BeanResolver có thể truy cập toàn bộ container mà không giới hạn. Cần cân nhắc:

- Chỉ cung cấp những bean mà biểu thức thực sự cần.
- Dùng context có phạm vi truy cập phù hợp.
- Hạn chế method có tác dụng phụ.
- Kiểm soát dữ liệu đầu vào và quyền nghiệp vụ.
- Không xem cú pháp SpEL là ranh giới bảo mật.

Nếu ứng dụng không cần bean reference, không đăng ký BeanResolver cho context đó.

## 14. Ví dụ hoàn chỉnh: gọi bean trong ApplicationContext

Giả sử có service:

~~~java
@Component("discountPolicy")
public class DiscountPolicy {

    public BigDecimal discountFor(BigDecimal total) {
        if (total.compareTo(new BigDecimal("1000000")) >= 0) {
            return new BigDecimal("0.10");
        }
        return BigDecimal.ZERO;
    }
}
~~~

Tạo context và đánh giá biểu thức:

~~~java
ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

context.setVariable(
    "total",
    new BigDecimal("1500000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "@discountPolicy.discountFor(#total)"
);

BigDecimal discountRate =
    expression.getValue(context, BigDecimal.class);

System.out.println(discountRate);
~~~

Kết quả:

~~~text
0.10
~~~

Luồng xử lý:

1. Bean \`discountPolicy\` được đăng ký trong ApplicationContext.
2. BeanFactoryResolver kết nối EvaluationContext với container.
3. Biến \`total\` được đăng ký trong context.
4. SpEL giải quyết \`@discountPolicy\` thành bean object.
5. MethodResolver tìm và gọi \`discountFor(BigDecimal)\`.
6. Method trả về BigDecimal và getValue nhận kết quả theo kiểu được yêu cầu.

## 15. Ghi nhớ

- Bean reference dùng cú pháp \`@beanName\` để lấy bean theo tên từ container.
- BeanResolver là thành phần chịu trách nhiệm giải quyết bean reference.
- Spring cung cấp BeanFactoryResolver để kết nối SpEL với BeanFactory; ApplicationContext có thể được truyền vào resolver.
- StandardEvaluationContext tự tạo cần được cấu hình BeanResolver trước khi dùng cú pháp @.
- Trong biểu thức @Value của Spring, cơ chế expression resolver tích hợp với BeanFactory thường đã cung cấp khả năng bean reference.
- \`#name\` là biến trong EvaluationContext, còn \`@name\` là bean reference.
- Có thể truy cập property và gọi method trên bean sau khi bean được giải quyết.
- \`&beanName\` dùng để lấy chính FactoryBean thay vì sản phẩm do factory tạo.
- Scope của bean, AOP proxy và lifecycle của container vẫn có hiệu lực khi bean được lấy qua resolver.
- Không nên mở bean reference rộng rãi cho expression không đáng tin cậy nếu không kiểm soát quyền truy cập và tác dụng phụ.

Khi dùng bean reference trong SpEL, hãy xác định bean name, bảo đảm EvaluationContext có BeanResolver phù hợp, rồi kiểm tra riêng bước lấy bean và bước truy cập property hoặc gọi method trên bean đó.
