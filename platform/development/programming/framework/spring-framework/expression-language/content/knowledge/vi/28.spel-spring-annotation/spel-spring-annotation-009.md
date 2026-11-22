# Xác định EvaluationContext do từng module Spring cung cấp

## 1. Vì sao mỗi module có EvaluationContext riêng?

Spring Expression Language (SpEL) cung cấp parser và bộ máy đánh giá expression dùng chung. Tuy nhiên, khi một annotation hoặc module Spring hỗ trợ SpEL, module đó thường tự tạo hoặc cấu hình EvaluationContext phù hợp với mục đích của nó.

EvaluationContext quyết định expression có thể nhìn thấy những gì và được phép làm gì. Context có thể cung cấp:

- Root object để phân giải property và method không có tiền tố.
- Variables được tham chiếu bằng tiền tố #.
- PropertyAccessor để đọc hoặc ghi property theo quy tắc của module.
- MethodResolver và ConstructorResolver để tìm method hoặc constructor.
- BeanResolver để truy cập bean bằng cú pháp @beanName.
- TypeLocator để phân giải class trong biểu thức T(...).
- TypeConverter để chuyển đổi giá trị khi gán property, gọi method hoặc lấy kết quả.

Vì vậy, một expression có thể chạy được ở một điểm tích hợp nhưng thất bại ở điểm khác. Ví dụ, một bean reference có thể dùng được trong expression của BeanFactory nhưng không có sẵn trong một context được tạo thủ công. Một biến #result có thể được cung cấp bởi cache expression evaluator nhưng không tồn tại trong context của @Value.

Không có một EvaluationContext duy nhất tự động áp dụng cho mọi annotation Spring. Muốn biết expression cụ thể nhìn thấy gì, cần xác định module nào xử lý annotation đó và context nào module ấy tạo ra.

## 2. Phân biệt parser, Expression và EvaluationContext

Ba thành phần này có nhiệm vụ khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| ExpressionParser | Phân tích source thành cấu trúc Expression |
| Expression | Giữ biểu thức đã parse và cung cấp getValue/setValue |
| EvaluationContext | Cung cấp root object, variables, accessor, resolver và quy tắc chuyển đổi lúc đánh giá |

Ví dụ dùng context tự tạo:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.name");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

String name = expression.getValue(context, String.class);
~~~

Parser không quyết định customer là object nào. EvaluationContext chứa root object order; property accessor của context đọc customer và name khi expression được đánh giá.

Một parser có thể được tái sử dụng với nhiều context. Cùng một Expression có thể cho kết quả khác nhau khi root object hoặc variables thay đổi. Khi một annotation Spring đánh giá expression, module tích hợp thường sở hữu bước tạo context và truyền context vào expression evaluator.

## 3. Cách tìm EvaluationContext của một annotation

Khi gặp một annotation có thuộc tính nhận SpEL, hãy lần theo thành phần chịu trách nhiệm xử lý annotation đó. Không nên suy luận context chỉ từ cú pháp expression.

Một quy trình thực tế:

1. Xác định annotation thuộc module nào, ví dụ core container, cache, method security, Spring Data hoặc event.
2. Tìm processor, interceptor, expression evaluator hoặc handler xử lý annotation.
3. Tìm vị trí gọi parseExpression và evaluate/getValue.
4. Xem context được tạo ở đâu, root object có kiểu gì và variables nào được đặt vào context.
5. Kiểm tra BeanResolver, TypeConverter, PropertyAccessor và các resolver có được cấu hình không.
6. Viết test nhỏ tại đúng điểm tích hợp để xác nhận những biến và object thực sự có sẵn.

Tên class có thể thay đổi giữa các phiên bản Spring và giữa các module. Hãy tra cứu source code của đúng dependency đang chạy trong ứng dụng, thay vì lấy một class name từ ví dụ của phiên bản khác rồi giả định nó vẫn đúng.

## 4. @Value và BeanFactory expression context

Trong Spring Framework core container, @Value và expression trong bean definition được xử lý qua cơ chế expression của BeanFactory. ConfigurableBeanFactory có BeanExpressionResolver; implementation mặc định phổ biến là StandardBeanExpressionResolver.

Resolver này tạo EvaluationContext dựa trên BeanExpressionContext của BeanFactory. Context thường được cấu hình để truy cập các khả năng của container như bean, environment và các object theo scope.

Ví dụ:

~~~java
@Component
public class WelcomeMessage {
    @Value("Hello #{systemProperties['user.name']}")
    private String message;

    @Value("#{T(java.lang.Math).max(3, 5)}")
    private int limit;

    @Value("#{applicationProperties['region']}")
    private String region;
}
~~~

Expression trong @Value được đánh giá trong context do Spring container cung cấp. Bean reference có thể được viết bằng @beanName khi resolver có BeanResolver phù hợp. Property access cũng có thể được mở rộng để đọc dữ liệu từ BeanExpressionContext, BeanFactory, Map hoặc Environment.

Không nên xem ví dụ trên là danh sách đầy đủ các biến có sẵn cho mọi BeanFactory hoặc mọi cấu hình. Hãy kiểm tra resolver và BeanFactory cụ thể của ứng dụng. Với context tự tạo bằng new StandardEvaluationContext(), những khả năng này không tự xuất hiện.

Nếu cần tự đánh giá expression có cùng khả năng như @Value, hãy cấu hình rõ root object, BeanResolver, TypeConverter, PropertyAccessor và các biến cần thiết. Trong nhiều trường hợp, dùng chính Spring container để kiểm thử @Value sẽ đáng tin cậy hơn việc cố dựng lại nội bộ resolver trong một unit test.

## 5. Method security: @PreAuthorize và @PostAuthorize

Spring Security method security có expression handler riêng. Với cấu hình method security tiêu chuẩn, DefaultMethodSecurityExpressionHandler tạo context và security expression root dành cho method invocation.

Các annotation thường dùng:

- @PreAuthorize: kiểm tra điều kiện trước khi method chạy.
- @PostAuthorize: kiểm tra điều kiện sau khi method trả về.
- @PreFilter: lọc đối số collection trước khi method chạy.
- @PostFilter: lọc collection trả về hoặc collection được chỉ định sau khi method chạy.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('invoice:read')")
public Invoice findInvoice(Long id) {
    return repository.findById(id).orElseThrow();
}

@PostAuthorize("returnObject.owner == authentication.name")
public Invoice loadOwnedInvoice(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Context security cung cấp root object chuyên biệt, thường có các khả năng như hasRole, hasAuthority, authentication, principal, permission checks và bean reference khi được cấu hình. Method arguments được đưa vào evaluation context theo tên tham số nếu có thể khám phá, đồng thời có thể tham chiếu bằng alias dạng #p0 hoặc #a0.

Trong @PostAuthorize, kết quả method có thể được tham chiếu bằng returnObject hoặc #returnObject tùy cú pháp và context của handler. Trong @PreFilter/@PostFilter, filterObject đại diện cho phần tử hiện tại đang được lọc. Các biến này có ý nghĩa theo từng annotation và thời điểm thực thi; không giả định chúng luôn có mặt trong mọi expression security.

Nếu thay MethodSecurityExpressionHandler hoặc cấu hình root object tùy chỉnh, tập helper và variables có thể khác. Hãy kiểm tra handler thực tế được đăng ký trong ứng dụng.

## 6. Cache annotations: @Cacheable, @CachePut và @CacheEvict

Spring Cache có expression evaluator riêng cho các annotation cache. Cache operation expression thường được đánh giá với root object mô tả method invocation và cache liên quan.

Ví dụ:

~~~java
@Cacheable(
        cacheNames = "products",
        key = "#root.methodName + ':' + #id",
        condition = "#id != null",
        unless = "#result == null")
public Product findProduct(Long id) {
    return repository.findById(id).orElse(null);
}
~~~

Trong cache expression, root object thường cung cấp thông tin như method, target, targetClass, arguments và caches. Các argument của method có thể được truy cập bằng tên tham số nếu tên được giữ lại hoặc bằng alias như #p0 và #a0.

#result được dùng ở những giai đoạn mà kết quả method đã có, chẳng hạn điều kiện unless của @Cacheable. Không phải mọi thuộc tính cache đều được đánh giá sau khi method chạy. Ví dụ condition và key thường được tính trước khi invocation, nên không thể dựa vào kết quả method chưa tồn tại.

Với @CacheEvict, thuộc tính beforeInvocation ảnh hưởng thời điểm eviction. Một expression không thể đọc kết quả method trước khi method được gọi. Hãy xác định thời điểm evaluator chạy trước khi sử dụng #result hoặc các biến phụ thuộc kết quả.

## 7. Spring Data repository query expressions

Spring Data có EvaluationContextProvider và các thành phần mở rộng để tạo context cho SpEL trong repository query. Cú pháp cụ thể phụ thuộc module Spring Data và loại repository.

Ví dụ trong Spring Data JPA:

~~~java
@Query("select u from User u where u.firstname = ?#{[0]}")
List<User> findBySpelArgument(String firstname);
~~~

Spring Data JPA cũng hỗ trợ biến #entityName trong query template:

~~~java
@Query("select e from #{#entityName} e where e.active = true")
List<?> findAllActive();
~~~

Repository query context có thể cung cấp method arguments, tên tham số, entity metadata và các extension đã đăng ký. Một extension có thể bổ sung root object hoặc variables; ví dụ tích hợp Spring Security có thể cung cấp thông tin người dùng nếu extension tương ứng được thêm vào cấu hình.

Không nên giả định một variable chỉ xuất hiện vì ứng dụng có dependency tương ứng trên classpath. Extension phải được module hỗ trợ và đăng ký theo cách mà EvaluationContextProvider sử dụng. Kiểm tra cấu hình Spring Data đang chạy và viết repository integration test cho query expression.

## 8. @EventListener condition

@EventListener có thuộc tính condition cho phép dùng SpEL để quyết định listener có được gọi hay không:

~~~java
@Component
public class OrderEvents {

    @EventListener(condition = "#event.status == 'PAID'")
    public void onOrderChanged(OrderChangedEvent event) {
        // Xử lý sự kiện đã thanh toán.
    }
}
~~~

Event listener expression được đánh giá trong context do cơ chế event annotation của Spring tạo ra. Context có thể đưa event và method arguments vào root object hoặc variables để expression truy cập. Cách đặt tên và alias phụ thuộc evaluator và phiên bản Spring.

Vì vậy, hãy xác nhận các tham chiếu như #root, #event, #a0 hoặc tên tham số bằng source code và integration test của phiên bản đang dùng. Đừng mặc định context của @EventListener giống context của @Value hoặc method security chỉ vì cả ba đều dùng SpEL.

## 9. Scoped values và các annotation dùng @Value

Một số module hoặc scope Spring cho phép @Value tham chiếu dữ liệu chỉ có trong một scope cụ thể. Ví dụ, Spring Batch late binding thường dùng step-scoped hoặc job-scoped bean để đọc job parameters và execution context:

~~~java
@Bean
@StepScope
public ItemReader<InputRecord> reader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return createReader(inputFile);
}
~~~

Ở đây expression được đánh giá trong vòng đời bean scope có liên quan. Các object như jobParameters được expose bởi cơ chế scope và BeanFactory integration của Spring Batch.

Nếu chuyển cùng expression sang một bean singleton thông thường hoặc một StandardEvaluationContext tự tạo, jobParameters có thể không tồn tại. Sự hiện diện của biến phụ thuộc vào scope và resolver đang hoạt động, không chỉ phụ thuộc vào nội dung expression.

Khi kiểm thử late binding, hãy chạy test với đúng StepScope hoặc JobScope test support của Spring Batch để mô phỏng context cần thiết.

## 10. So sánh các context thường gặp

| Điểm tích hợp | Thành phần cần lần theo | Dữ liệu thường được expose |
|---|---|---|
| @Value / bean definition | BeanExpressionResolver, thường là StandardBeanExpressionResolver | BeanFactory, Environment, system properties/environment và scope context |
| @PreAuthorize / @PostAuthorize | MethodSecurityExpressionHandler | Security root, authentication, method arguments, quyền và helper security |
| @PreFilter / @PostFilter | Method security expression handler | Security root, filterObject và collection đang lọc |
| @Cacheable / @CachePut / @CacheEvict | CacheOperationExpressionEvaluator | Method, target, targetClass, args, caches và result theo thời điểm |
| Spring Data query | EvaluationContextProvider và query evaluator của module | Method arguments, entity metadata và registered extensions |
| @EventListener condition | Event expression evaluator | Event và method arguments theo context của listener |
| Spring Batch late binding | Scope context kết hợp BeanFactory expression resolution | jobParameters, jobExecutionContext hoặc stepExecutionContext theo scope |

Bảng này là bản đồ định hướng để tìm đúng nơi triển khai. Tập biến chính xác và kiểu root object có thể thay đổi theo module, cấu hình và phiên bản.

## 11. Cùng một expression không đảm bảo cùng kết quả ở mọi module

Giả sử expression dùng #result:

~~~text
#result == null
~~~

Expression này có ý nghĩa khi evaluator cung cấp biến result tại thời điểm đánh giá, ví dụ một số cache operation sau khi method trả về hoặc post-invocation expression của security. Trong một context không có biến result, expression có thể trả về null hoặc không có hành vi mà người viết mong đợi.

Tương tự, #root.method có thể tồn tại trong cache expression nhưng không có cùng cấu trúc ở context của @Value. Biến authentication có thể được expose bởi security handler hoặc extension nhưng không tự xuất hiện trong một context SpEL độc lập.

Khi tái sử dụng expression giữa các module, hãy liệt kê dependencies của nó: root properties, variables, bean references, method calls và conversion rules. Sau đó xác nhận mỗi context cung cấp đủ các dependencies đó.

## 12. Cách kiểm tra root object và variables trong lúc debug

Khi expression cho kết quả bất ngờ, hãy kiểm tra context ở đúng điểm evaluate:

1. Đặt breakpoint tại expression evaluator hoặc handler xử lý annotation.
2. Kiểm tra root object và kiểu runtime của root object.
3. Xem danh sách variables đã được đặt vào context.
4. Kiểm tra property accessors và method resolvers.
5. Kiểm tra BeanResolver có được cấu hình hay không nếu expression dùng @beanName.
6. Kiểm tra TypeConverter và ConversionService nếu có chuyển đổi kiểu.
7. Xác định expression được đánh giá trước hay sau method invocation.

Không phải mọi EvaluationContext đều có API liệt kê tất cả variables theo cách thống nhất. Nếu cần quan sát variables, hãy xem nơi context được tạo và các lệnh setVariable hoặc extension được gọi tại đó. Có thể thêm logging hoặc breakpoint trong code tích hợp khi chạy test.

## 13. Kiểm thử đúng module thay vì chỉ kiểm thử parser

Một unit test gọi SpelExpressionParser và StandardEvaluationContext xác nhận cú pháp và hành vi SpEL cơ bản. Nó không chứng minh annotation integration đang tạo đúng context.

Hãy kiểm thử tại đúng tầng:

- Với @Value, khởi tạo ApplicationContext và xác nhận bean nhận đúng giá trị.
- Với method security, gọi method qua Spring proxy và xác nhận quyền truy cập theo authentication hiện tại.
- Với cache annotations, gọi method qua proxy và xác nhận key, condition hoặc unless theo kết quả method.
- Với Spring Data, thực thi repository query thực tế và kiểm tra tham số/metadata.
- Với @EventListener, publish event và xác nhận condition quyết định listener có chạy.
- Với Spring Batch, chạy test trong StepScope hoặc JobScope phù hợp.

Các test tích hợp này xác nhận module đã tạo context, root object, variables và resolver như mong muốn. Chỉ parse expression riêng lẻ không kiểm tra được các bước đó.

## 14. Khi context thiếu một biến hoặc bean

Nếu expression tham chiếu một variable không được cung cấp, kết quả lookup có thể là null hoặc gây lỗi ở thao tác tiếp theo. Nếu dùng bean reference @service mà BeanResolver không có hoặc bean không được tìm thấy, evaluation có thể thất bại.

Cách xử lý:

- Xác định module có cam kết cung cấp variable hoặc bean reference đó hay không.
- Kiểm tra cấu hình extension, resolver và bean registration.
- Nếu variable là đầu vào của ứng dụng, truyền nó rõ ràng qua context hoặc object root.
- Nếu logic chỉ có ở một module, giữ expression trong phạm vi module đó thay vì dùng lại ở nơi không có cùng context.
- Viết test cho trường hợp variable thiếu để quyết định rõ kết quả mặc định hay lỗi cấu hình.

Đừng che giấu lỗi cấu hình bằng cách thêm Elvis mặc định vào mọi variable. Giá trị mặc định chỉ phù hợp khi đó là quy tắc nghiệp vụ; nếu biến bắt buộc bị thiếu, lỗi rõ ràng thường dễ chẩn đoán hơn.

## 15. Bảo mật và quyền của EvaluationContext

EvaluationContext không chỉ quyết định dữ liệu nào expression nhìn thấy mà còn quyết định khả năng mà expression có thể sử dụng. Một context có thể cho phép gọi method, tham chiếu bean, phân giải type hoặc đọc property nhạy cảm.

Một số nguyên tắc:

- Không đánh giá template hoặc expression do người dùng tùy ý gửi lên bằng context có quyền rộng.
- Chỉ expose bean và method cần thiết cho expression.
- Dùng context giới hạn như SimpleEvaluationContext khi nhu cầu chỉ là data binding hoặc property access được kiểm soát.
- Với method security, giữ nguyên handler và root object được thiết kế cho security; không thay thế bằng context tự tạo làm mất các kiểm tra quyền.
- Không đưa secret hoặc object nhạy cảm vào root object nếu expression không cần truy cập chúng.

Một expression ngắn vẫn có thể gọi method có side effect nếu context cho phép. Hãy xem context là một phần của ranh giới bảo mật và kiểm thử quyền thực tế, không chỉ kiểm thử kết quả chuỗi.

## 16. Lỗi thường gặp

**Giả định mọi annotation dùng cùng một context**

Các module có evaluator, root object và variables riêng. Hãy tìm đúng handler của annotation.

**Nhầm root property với variable**

Property root được truy cập bằng tên trực tiếp; variable thường có tiền tố #. Hai nguồn này không thay thế cho nhau.

**Dùng #result trước khi kết quả tồn tại**

Một số expression chạy trước method invocation. Kiểm tra lifecycle của cache/security operation trước khi tham chiếu kết quả.

**Giả định bean reference luôn có sẵn**

Cú pháp @beanName cần BeanResolver phù hợp. Context tự tạo không tự biết ApplicationContext.

**Chỉ test bằng SpelExpressionParser**

Parser test không chạy annotation processor, AOP proxy, repository evaluator hoặc event listener. Hãy thêm test tích hợp cho module liên quan.

**Dùng biến từ module khác mà không đăng ký extension**

Spring Data hoặc module khác có thể cung cấp extension tùy cấu hình. Dependency trên classpath không tự đảm bảo extension đã được đăng ký.

**Tra cứu source của phiên bản khác**

Tên handler, evaluator và chi tiết variables có thể thay đổi. Kiểm tra đúng Spring Framework, Spring Security, Spring Data hoặc Spring Batch version của ứng dụng.

## 17. Ví dụ tổng hợp: cùng dữ liệu nhưng hai context

Một object Order có thể được dùng trong context tự tạo:

~~~java
Order order = new Order("ORD-1001", "Lan");

StandardEvaluationContext manualContext =
        new StandardEvaluationContext(order);
manualContext.setVariable("prefix", "Order");

Expression expression =
        new SpelExpressionParser().parseExpression(
                "#prefix + ': ' + code + ' / ' + customerName");

String result = expression.getValue(manualContext, String.class);
~~~

Ở context tự tạo, code phải chủ động cung cấp root object và variable prefix. Nếu expression cần bean reference hoặc một helper đặc biệt, code cũng phải cấu hình resolver tương ứng.

Khi cùng một chuỗi được dùng trong annotation của module khác, module đó sẽ tạo context theo contract riêng. Có thể root object không còn là Order, variable prefix không tồn tại, hoặc có thêm biến đặc biệt như #result hay #filterObject. Expression chỉ dùng lại an toàn khi hai context có cùng contract dữ liệu và quyền truy cập.

## 18. Ghi nhớ

- EvaluationContext xác định root object, variables, property accessors, method resolvers, bean/type resolver và TypeConverter.
- Parser tạo Expression; context cung cấp môi trường khi Expression được evaluate.
- Không có một EvaluationContext phổ quát cho mọi annotation Spring.
- @Value thường đi qua BeanExpressionResolver của BeanFactory, phổ biến là StandardBeanExpressionResolver.
- Method security dùng MethodSecurityExpressionHandler và security expression root riêng.
- Cache annotations dùng cache expression evaluator với root chứa method, target, arguments, caches và result theo thời điểm.
- Spring Data query và @EventListener có evaluator/context riêng; kiểm tra extension và method argument exposure.
- Spring Batch late binding phụ thuộc scope context như job parameters và execution context.
- Tìm evaluator, nơi tạo context và nơi set variables trong đúng phiên bản dependency.
- Kiểm thử qua chính annotation/module; parser unit test không thay thế integration test.
- Không giả định biến hoặc bean từ module này tồn tại trong context của module khác.
- Quyền của EvaluationContext là một phần của thiết kế bảo mật.
