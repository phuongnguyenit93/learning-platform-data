# Gọi method trên bean được tham chiếu trong SpEL

Spring Expression Language (SpEL) có thể tham chiếu một bean do Spring quản lý bằng cú pháp @beanName, sau đó đọc property hoặc gọi method trên bean đó. Khả năng này giúp biểu thức dùng lại logic đã được đóng gói trong một component Spring, chẳng hạn tính một giá trị cấu hình, áp dụng một chính sách hoặc truy vấn một facade chuyên biệt.

Một lời gọi như @pricingPolicy.calculateDiscount(#total) cần hai khả năng riêng: BeanResolver phải tìm được bean pricingPolicy trong Spring container, sau đó MethodResolver phải tìm được method calculateDiscount phù hợp trên object vừa nhận được. Hiểu rõ hai bước này giúp cấu hình đúng EvaluationContext, xử lý lỗi dễ hơn và giới hạn các method mà expression có thể gọi.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Tham chiếu bean bằng cú pháp @beanName.
- Gọi method trên bean và truyền literal, biến hoặc property làm đối số.
- Cấu hình BeanFactoryResolver khi tự tạo StandardEvaluationContext.
- Hiểu cách Spring tích hợp bean reference trong @Value.
- Phân biệt BeanResolver với MethodResolver và PropertyAccessor.
- Nhận biết ảnh hưởng của overload, kiểu tham số, scope và proxy.
- Chẩn đoán lỗi khi bean hoặc method không được phân giải.
- Giới hạn bean và method được expose cho biểu thức để giảm rủi ro.

Bạn nên biết Spring IoC container, bean name, getter/method Java, SpelExpressionParser và cách truyền biến qua EvaluationContext.

## 2. Cú pháp tham chiếu bean

SpEL dùng ký hiệu @ để tham chiếu một bean theo tên:

~~~text
@pricingPolicy
~~~

Khi muốn đọc property của bean:

~~~text
@pricingPolicy.defaultRate
~~~

Khi muốn gọi method:

~~~text
@pricingPolicy.calculateDiscount(100)
~~~

Tên sau @ phải được BeanResolver phân giải thành một bean có trong container hoặc một đối tượng mà resolver quản lý. Bean name và alias phải đúng với cấu hình Spring.

Có thể truyền biến vào method:

~~~text
@pricingPolicy.calculateDiscount(#orderTotal)
~~~

Hoặc truyền property từ một biến object:

~~~text
@pricingPolicy.calculateDiscount(#order.total)
~~~

Ở đây #orderTotal và #order là biến SpEL, còn @pricingPolicy là bean reference. Hai cú pháp có vai trò khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| #variable | Đọc biến được đăng ký trong EvaluationContext |
| @beanName | Lấy bean theo tên qua BeanResolver |
| @beanName.property | Đọc property trên bean |
| @beanName.method(...) | Gọi method trên bean |

Không cần tạo bean bằng cú pháp new trong expression. Bean reference lấy object do Spring container quản lý, vì vậy dependency injection, lifecycle và các cơ chế proxy thông thường của bean vẫn do container xử lý.

## 3. BeanResolver làm nhiệm vụ gì?

BeanResolver là thành phần trong EvaluationContext chịu trách nhiệm giải quyết cú pháp @beanName. Nó nhận tên bean và trả về object tương ứng. Sau khi có object, SpEL tiếp tục xử lý property hoặc method trên object đó.

Với StandardEvaluationContext được tạo thủ công, không nên giả định BeanResolver đã được cấu hình. Nếu cần dùng bean reference, ứng dụng phải cung cấp resolver phù hợp.

Spring có lớp BeanFactoryResolver để kết nối SpEL với BeanFactory:

~~~java
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.spel.support.StandardEvaluationContext;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

BeanFactoryResolver dùng BeanFactory được truyền vào để tìm bean theo tên. Trong ứng dụng Spring, beanFactory thường là ApplicationContext hoặc BeanFactory hiện có.

Sau khi cấu hình, expression có thể sử dụng @beanName trong context đó.

## 4. Ví dụ gọi method trên bean

Giả sử có component chính sách giá:

~~~java
@Component("pricingPolicy")
public class PricingPolicy {

    public BigDecimal calculateDiscount(BigDecimal total) {
        if (total.compareTo(new BigDecimal("100")) >= 0) {
            return total.multiply(new BigDecimal("0.10"));
        }
        return BigDecimal.ZERO;
    }
}
~~~

Có thể gọi method bằng SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(new BeanFactoryResolver(beanFactory));
context.setVariable("total", new BigDecimal("150.00"));

Expression expression =
    parser.parseExpression("@pricingPolicy.calculateDiscount(#total)");

BigDecimal discount =
    expression.getValue(context, BigDecimal.class);
~~~

Kết quả là 15.00 theo logic của method ví dụ.

Luồng xử lý:

1. SpEL gặp @pricingPolicy.
2. BeanResolver lấy bean pricingPolicy từ BeanFactory.
3. SpEL nhận object PricingPolicy.
4. MethodResolver tìm method calculateDiscount phù hợp với đối số.
5. SpEL chuyển đổi đối số nếu cần và gọi method.
6. Kết quả được trả về từ getValue(...).

Đối tượng nhận method là bean do container cung cấp. Không cần đăng ký pricingPolicy thành biến #pricingPolicy, trừ khi ứng dụng chủ động muốn truyền object đó dưới dạng variable.

## 5. Truyền đối số vào method

Đối số của method có thể là literal, biến, property access hoặc kết quả của một biểu thức khác.

### 5.1. Literal

~~~text
@pricingPolicy.calculateDiscount(150)
~~~

Giá trị 150 được truyền vào method. Kiểu literal và kiểu tham số của method phải tương thích hoặc có thể chuyển đổi.

### 5.2. Biến trong context

~~~text
@pricingPolicy.calculateDiscount(#total)
~~~

Đăng ký biến từ Java:

~~~java
context.setVariable("total", new BigDecimal("150.00"));
~~~

Cách này phù hợp khi dữ liệu thay đổi theo từng lần đánh giá. Expression vẫn giữ nguyên còn giá trị biến được cập nhật trong context.

### 5.3. Property của object

~~~text
@pricingPolicy.calculateDiscount(#order.total)
~~~

Nếu order là object có property total đọc được, SpEL lấy total rồi truyền vào method.

Nếu order hoặc total có thể null, cần xác định cách xử lý trước khi gọi method. Có thể kiểm tra bằng điều kiện logic hoặc dùng null-safe navigation kết hợp với biểu thức mặc định nếu method chấp nhận giá trị đó.

### 5.4. Nhiều đối số

~~~text
@pricingPolicy.calculateRate(#customer.level, #order.total)
~~~

Method đích phải có chữ ký tương ứng hoặc một overload mà SpEL có thể phân giải. Khi có nhiều overload, kiểu của đối số và khả năng chuyển đổi ảnh hưởng tới method được chọn.

Hãy giữ đối số rõ ràng. Nếu biểu thức phải tính nhiều giá trị trước khi gọi method, có thể dùng dấu ngoặc để làm rõ thứ tự hoặc tính dữ liệu trong Java trước rồi truyền qua biến.

## 6. Gọi bean method trong @Value

Trong các điểm tích hợp do Spring quản lý, @Value hỗ trợ SpEL và container cung cấp khả năng tham chiếu bean.

Ví dụ đọc property:

~~~java
@Value("#{ @pricingPolicy.defaultRate }")
private BigDecimal defaultRate;
~~~

Ví dụ gọi method:

~~~java
@Value("#{ @pricingPolicy.rateFor('VIP') }")
private BigDecimal vipRate;
~~~

Spring đánh giá expression trong context tích hợp với container. Bean pricingPolicy phải tồn tại và method rateFor phải có chữ ký tương thích với đối số 'VIP'.

Có thể kết hợp nhiều bean hoặc property:

~~~java
@Value("#{ @featureFlags.enabled and @pricingPolicy.isAvailable }")
private boolean pricingEnabled;
~~~

Expression vẫn tuân theo cú pháp và quy tắc precedence của SpEL. Với điều kiện dài hoặc nghiệp vụ quan trọng, nên chuyển logic sang method có tên rõ ràng để dễ kiểm thử.

Không nhầm @Value với việc gọi bean trong StandardEvaluationContext tự tạo. Trong @Value, Spring cấu hình môi trường đánh giá cho integration point; trong Java code tự tạo context, bạn phải cấu hình BeanResolver nếu muốn dùng @beanName.

## 7. Bean reference khác gì variable và root object?

Có nhiều cách cung cấp object cho expression:

- Root object: object truyền vào getValue(context, rootObject) hoặc được đặt trong context.
- Variable: object được đăng ký bằng context.setVariable("name", object) và truy cập qua #name.
- Bean reference: object được lấy từ container qua @name.

Ví dụ cùng một method có thể được gọi bằng ba cách nếu object được cung cấp tương ứng:

~~~text
calculateDiscount(#total)
~~~

~~~text
#policy.calculateDiscount(#total)
~~~

~~~text
@pricingPolicy.calculateDiscount(#total)
~~~

Cách đầu giả định root object có method calculateDiscount. Cách thứ hai dùng biến policy. Cách thứ ba lấy bean theo tên từ BeanResolver.

Nên chọn một cách theo nguồn sở hữu object. Dùng @beanName khi expression thực sự cần truy cập component do Spring quản lý; dùng biến cho dữ liệu hoặc collaborator được truyền rõ ràng; dùng root object cho biểu thức gắn với một object chính.

## 8. BeanResolver và MethodResolver là hai bước độc lập

Một lỗi thiết kế thường gặp là nghĩ rằng có BeanResolver thì mọi method trên bean đều được phép gọi. Thực tế, BeanResolver chỉ giải quyết tên bean. MethodResolver chịu trách nhiệm tìm method trên object vừa nhận được.

| Thành phần | Câu hỏi mà nó trả lời |
|---|---|
| BeanResolver | Bean tên pricingPolicy là object nào? |
| MethodResolver | Object đó có method calculateDiscount phù hợp không? |
| TypeConverter | Đối số có chuyển được sang kiểu tham số không? |
| PropertyAccessor | Có thể đọc property total hoặc defaultRate không? |

StandardEvaluationContext thường có reflective method resolution mặc định. Nếu ứng dụng cần giới hạn method, có thể dùng MethodFilter hoặc custom MethodResolver theo allowlist. Việc giới hạn MethodResolver không tự động giới hạn bean nào có thể được tham chiếu; BeanResolver và danh sách bean được expose cũng cần được kiểm soát.

Một expression có thể phân giải thành công bean nhưng vẫn lỗi nếu method không tồn tại, không truy cập được hoặc đối số không tương thích.

## 9. Bean scope, proxy và object được trả về

BeanResolver lấy bean thông qua BeanFactory. Vì vậy, quy tắc scope và proxy do Spring container quản lý vẫn áp dụng.

- Singleton bean thường trả về cùng một instance được container quản lý.
- Prototype bean có thể tạo instance mới theo mỗi lần BeanFactory lấy bean.
- Request/session scope phụ thuộc vào request/session context đang hoạt động.
- Bean được bọc bởi AOP proxy có thể được trả về dưới dạng proxy; lời gọi method đi qua cơ chế proxy như bình thường.

Điều này có ý nghĩa khi expression gọi method có transaction, security advice hoặc logging advice. Tuy nhiên, không nên dùng SpEL như một cách thay thế luồng gọi service thông thường trong Java. Nếu method là một thao tác nghiệp vụ quan trọng, gọi trực tiếp từ Java thường rõ ràng hơn và dễ theo dõi hơn.

Không giả định mọi scope đều khả dụng ở mọi thời điểm. Ví dụ request-scoped bean không thể được dùng đúng cách khi không có request context phù hợp.

## 10. BeanFactory và FactoryBean

Thông thường:

~~~text
@myBean
~~~

tham chiếu object mà BeanFactory trả về cho bean name đó.

Nếu bean name đại diện một FactoryBean và cần lấy chính factory thay vì object do factory tạo ra, Spring dùng tiền tố &:

~~~text
&myFactoryBean
~~~

Đây là trường hợp chuyên biệt. Trong hầu hết expression nghiệp vụ, chỉ cần tham chiếu bean thông thường bằng @beanName. Chỉ dùng & khi thật sự cần thao tác với FactoryBean và hiểu rõ lifecycle của nó.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không phân giải được @beanName | Context không có BeanResolver hoặc bean name sai | Cấu hình BeanFactoryResolver và kiểm tra tên bean |
| Bean tồn tại nhưng method không tìm thấy | Sai method name, chữ ký hoặc method không truy cập được | Kiểm tra method và đối số |
| Chọn overload không như mong đợi | Kiểu đối số hoặc conversion làm nhiều overload phù hợp | Dùng biến có kiểu rõ ràng và tránh overload mơ hồ |
| Đối số không chuyển đổi được | Runtime value không tương thích với tham số | Kiểm tra kiểu và TypeConverter |
| Bean scope không hoạt động | Scope cần request/session context nhưng không có | Kiểm tra lifecycle và thời điểm evaluate |
| Method ném exception | Lỗi bên trong logic method | Xử lý exception theo hợp đồng nghiệp vụ |
| @Value không inject được | Expression sai cú pháp hoặc bean/method chưa sẵn sàng | Kiểm tra bean name, dependency và cấu hình expression |
| Bean được tìm thấy nhưng method ngoài dự kiến vẫn gọi được | MethodResolver quá rộng | Giới hạn method bằng facade, MethodFilter hoặc resolver allowlist |

Khi debug, kiểm tra theo thứ tự: bean name, BeanResolver, object runtime nhận được, method signature, kiểu đối số và exception trong method. Cách này giúp xác định lỗi nằm ở bước tìm bean hay bước gọi method.

## 12. Bảo mật khi gọi method trên bean

Tham chiếu bean trong SpEL có thể mở đường tới service, repository hoặc component có quyền lớn. Nếu expression đến từ người dùng hoặc nguồn cấu hình không tin cậy, cho phép tham chiếu bean tùy ý có thể dẫn tới hành động ngoài dự kiến.

Hãy áp dụng các nguyên tắc:

- Không đánh giá expression do người dùng cung cấp bằng context có thể truy cập mọi bean trong ApplicationContext.
- Không expose ApplicationContext, BeanFactory, repository hoặc service quản trị cho expression không tin cậy.
- Tạo facade nhỏ chỉ chứa method cần thiết.
- Giới hạn method bằng MethodFilter hoặc custom MethodResolver khi cần.
- Dùng BeanResolver có phạm vi hẹp nếu ứng dụng cần một tập bean cho phép.
- Ưu tiên method chỉ đọc, không có side effect và có kiểu đầu vào/đầu ra rõ ràng.
- Validate đối số trước khi method thực hiện nghiệp vụ.
- Không để expression tự quyết định bean name tùy ý từ dữ liệu request.
- Giới hạn độ dài và nguồn gốc expression.

BeanResolver không phải sandbox. Ngay cả khi chỉ expose một bean, method của bean đó có thể gọi các service khác hoặc thay đổi trạng thái. Hãy review quyền của facade và hành vi thực tế của từng method.

## 13. Bài tập thực hành

1. Tạo component PricingPolicy có method calculateDiscount(BigDecimal).
2. Cấu hình StandardEvaluationContext với BeanFactoryResolver.
3. Gọi @pricingPolicy.calculateDiscount(150) và đọc kết quả kiểu BigDecimal.
4. Đăng ký biến total rồi truyền #total làm đối số.
5. Gọi method có hai tham số và kiểm tra thứ tự đối số.
6. Tạo expression đọc @pricingPolicy.defaultRate và so sánh với lời gọi method.
7. Dùng @Value để inject kết quả từ method trên bean.
8. Tạo một method overload rồi kiểm tra SpEL chọn method nào với các kiểu đối số khác nhau.
9. Dùng facade nhỏ thay cho service lớn và thử giới hạn method.
10. Thử một bean name không tồn tại và ghi nhận lỗi phân giải.
11. Kiểm tra expression khi bean là proxy hoặc thuộc scope khác singleton.

## 14. Checklist trước khi gọi bean method

- [ ] Bean name có tồn tại trong BeanFactory không?
- [ ] EvaluationContext đã có BeanResolver phù hợp chưa?
- [ ] Đã phân biệt @beanName với #variable và root object chưa?
- [ ] Method có tên, chữ ký và khả năng truy cập đúng không?
- [ ] Đối số có kiểu tương thích và không null ngoài dự kiến không?
- [ ] Có overload cần làm rõ không?
- [ ] Method có side effect, I/O hoặc thay đổi trạng thái không?
- [ ] Bean có scope hoặc proxy cần lưu ý không?
- [ ] MethodResolver có giới hạn các method được phép gọi không?
- [ ] BeanResolver có expose quá nhiều bean không?
- [ ] Expression có nguồn gốc tin cậy và được giới hạn không?

## 15. Kết luận

Cú pháp @beanName cho phép SpEL lấy một bean do Spring quản lý và gọi method trên object đó. BeanResolver chịu trách nhiệm tìm bean; MethodResolver tiếp tục tìm method phù hợp; TypeConverter xử lý chuyển đổi đối số. Spring tự tích hợp khả năng này trong các điểm như @Value, còn StandardEvaluationContext tự tạo cần được cấu hình BeanFactoryResolver. Hãy expose facade nhỏ, giới hạn bean và method được phép gọi, kiểm tra kiểu đối số và tránh đánh giá expression không tin cậy bằng context có quyền rộng.