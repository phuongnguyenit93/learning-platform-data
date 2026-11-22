# Rủi ro khi expression có quyền gọi bean tùy ý

Spring Expression Language (SpEL) hỗ trợ tham chiếu bean Spring bằng cú pháp **@beanName** khi EvaluationContext được cấu hình BeanResolver. Khả năng này rất tiện cho biểu thức do ứng dụng hoặc đội phát triển kiểm soát: biểu thức có thể gọi method của service, đọc dữ liệu từ một bean hoặc kết hợp các quy tắc được cung cấp sẵn.

Rủi ro xuất hiện khi người dùng không tin cậy được phép viết expression trong một context có thể phân giải bean rộng. Một biểu thức có thể truy cập bean có quyền cao, gọi method gây thay đổi trạng thái, đọc dữ liệu nhạy cảm hoặc kích hoạt thao tác tốn tài nguyên. Việc parse thành công không chứng minh biểu thức được phép thực hiện những hành động đó.

Nguyên tắc quan trọng: **không cấp BeanResolver có quyền truy cập toàn bộ BeanFactory cho expression do người dùng kiểm soát**. Hãy giới hạn bean, method, dữ liệu và phạm vi đánh giá theo đúng nhu cầu.

## 1. Bean reference trong SpEL hoạt động như thế nào?

### 1.1. Cú pháp @beanName

SpEL dùng ký hiệu **@** để tham chiếu bean theo tên:

~~~java
@pricingService.calculate(order)
~~~

Biểu thức trên yêu cầu EvaluationContext phân giải bean có tên pricingService, sau đó gọi method calculate với đối số order.

Có thể tham chiếu bean trong biểu thức kết hợp với property hoặc method:

~~~java
@featurePolicy.enabled('checkout')
@exchangeRateService.rate('USD', 'VND')
@catalogRepository.findByCode('P-100')
~~~

Các biểu thức này chỉ hoạt động nếu context có BeanResolver phù hợp. Việc viết cú pháp @beanName không tự động tìm bean trong mọi ExpressionParser hoặc EvaluationContext.

### 1.2. BeanResolver

Extension point chịu trách nhiệm phân giải bean là interface BeanResolver trong package org.springframework.expression:

~~~java
public interface BeanResolver {
    Object resolve(
            EvaluationContext context,
            String beanName
    ) throws AccessException;
}
~~~

Khi parser đánh giá một bean reference, nó yêu cầu BeanResolver tìm object tương ứng. Resolver trả về bean hoặc ném AccessException nếu không thể phân giải.

Một EvaluationContext không có BeanResolver sẽ không thể giải quyết bean reference. Đây là một giới hạn hữu ích khi biểu thức không cần truy cập bean.

### 1.3. BeanFactoryResolver

Spring cung cấp BeanFactoryResolver để nối SpEL với Spring BeanFactory:

~~~java
BeanFactoryResolver resolver =
        new BeanFactoryResolver(beanFactory);

StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setBeanResolver(resolver);
~~~

Sau khi cấu hình, biểu thức có thể dùng cú pháp:

~~~java
@pricingService.calculate(order)
~~~

BeanFactoryResolver ủy quyền việc lấy bean cho BeanFactory. Nếu BeanFactory chứa nhiều bean, resolver này có thể làm cho các bean đó trở thành đối tượng mà expression tham chiếu theo tên, tùy quyền và các khả năng khác được cấp trong context.

Điều này phù hợp với biểu thức đáng tin cậy do ứng dụng quản lý. Với biểu thức do người dùng gửi lên, việc cấp resolver trỏ thẳng tới BeanFactory thường là quyền quá rộng.

### 1.4. Bean reference khác dependency injection

Cú pháp @beanName trong SpEL là một yêu cầu phân giải bean tại thời điểm đánh giá expression. Nó không phải annotation @Autowired và cũng không tự động inject dependency vào class.

Ví dụ:

~~~java
@pricingService.calculate(order)
~~~

Biểu thức yêu cầu resolver lấy bean pricingService và gọi method. Trong khi đó, dependency injection thường diễn ra khi Spring tạo và cấu hình bean của ứng dụng.

Hai cơ chế có mục đích khác nhau. Bean reference trong SpEL là một năng lực runtime mà context có thể cấp hoặc không cấp.

### 1.5. Tên bean đặc biệt và FactoryBean

Tên bean có thể chứa ký tự đặc biệt. SpEL hỗ trợ đặt tên bean trong dấu nháy sau ký hiệu @ khi cần:

~~~java
@'pricing-service'.calculate(order)
~~~

Spring cũng hỗ trợ cú pháp **&** để lấy chính FactoryBean thay vì object mà FactoryBean tạo ra:

~~~java
@&reportFactory
~~~

Khả năng truy cập FactoryBean cần được xem là một quyền riêng. Không cho phép người dùng tham chiếu FactoryBean chỉ vì họ cần dùng một bean thông thường; việc gọi method trên factory có thể mở thêm khả năng tạo object hoặc thao tác ngoài dự kiến.

## 2. Bean reference được cấu hình ở đâu?

### 2.1. Cấu hình trên StandardEvaluationContext

Ứng dụng có thể tự tạo context và chủ động gắn BeanResolver:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);

Object result = parser
        .parseExpression("@pricingService.calculate(#root)")
        .getValue(context);
~~~

Ví dụ giả định applicationContext có bean pricingService. Khi context được cấp resolver này, expression có thể tham chiếu bean theo tên.

Không phải mọi StandardEvaluationContext đều tự động có BeanFactoryResolver. Nếu ứng dụng không gọi setBeanResolver và không có cơ chế khác cung cấp resolver, bean reference sẽ không được phân giải.

### 2.2. Bean expression trong cấu hình Spring

Spring sử dụng SpEL trong một số điểm cấu hình như giá trị annotation @Value và biểu thức trong bean definition. StandardBeanExpressionResolver là một thành phần của container dùng để đánh giá bean expression trong ngữ cảnh Spring.

Ví dụ:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Một biểu thức bean expression trong cấu hình Spring có thể được container đánh giá với ngữ cảnh và khả năng phân giải bean mà container cung cấp.

Đây là biểu thức thuộc cấu hình ứng dụng. Nguồn cấu hình thường được kiểm soát bởi quy trình triển khai và review. Không nên suy rộng rằng mọi expression nhận từ API, form hoặc database đều cần có cùng quyền như biểu thức cấu hình nội bộ.

### 2.3. Chỉ cấp resolver khi thực sự cần

Nếu expression chỉ đọc property trên một DTO hoặc thực hiện phép so sánh, không cần gắn BeanResolver. Bỏ resolver khỏi context sẽ loại bỏ khả năng dùng cú pháp bean reference.

Ví dụ context không cấp bean resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

Boolean allowed = parser
        .parseExpression("active && score >= 80")
        .getValue(context, Boolean.class);
~~~

Cấu hình này phù hợp hơn khi expression chỉ cần dữ liệu đã chuẩn bị. Tuy nhiên, cần kiểm soát thêm method resolver, property accessor, type locator và constructor resolver nếu expression không tin cậy.

## 3. Vì sao bean reference tùy ý nguy hiểm?

### 3.1. Truy cập bean có quyền cao

Một Spring application có thể chứa nhiều bean phục vụ các nhiệm vụ nhạy cảm:

- Repository hoặc service truy cập dữ liệu khách hàng.
- DataSource hoặc thành phần truy cập database.
- Thành phần gửi email, thông báo hoặc message.
- Service thao tác tệp hoặc lưu trữ.
- Service quản lý tài khoản, quyền và phiên đăng nhập.
- Thành phần tích hợp hệ thống bên ngoài.
- Factory hoặc registry có khả năng tạo và tìm object khác.

Nếu expression có thể tham chiếu tùy ý các bean này, người viết expression có thể gọi những method mà ứng dụng vốn chỉ định cho một luồng xử lý tin cậy.

Rủi ro không chỉ nằm ở việc đọc bean. Method có thể ghi dữ liệu, gửi thông điệp, thay đổi trạng thái hoặc thực hiện giao dịch.

### 3.2. Gọi method có tác dụng phụ

Ví dụ, một context có thể phân giải bean mailSender. Nếu expression được phép gọi method gửi email, một người dùng có thể kích hoạt hành động gửi thông báo ngoài quy trình nghiệp vụ dự kiến.

Tương tự, method trên repository có thể truy vấn dữ liệu hoặc thay đổi trạng thái nếu API cung cấp thao tác ghi. Method trên storage service có thể đọc hoặc ghi tệp.

Ngay cả khi expression chỉ được dùng để đánh giá điều kiện, việc gọi method trong predicate hoặc ternary branch vẫn có thể kích hoạt tác dụng phụ. Không nên xem một expression Boolean là thao tác chỉ đọc nếu các method mà nó gọi có thể thay đổi trạng thái.

### 3.3. Rò rỉ dữ liệu

Một bean có thể trả về object chứa thông tin nhạy cảm. Nếu expression có thể đọc property hoặc gọi method trên object đó, dữ liệu có thể đi vào kết quả, log, thông báo lỗi hoặc response của API.

Một chuỗi truy cập nhiều cấp có thể đi từ bean được cho phép tới object khác:

~~~java
@customerService.findById(#customerId).account.owner.email
~~~

Việc cho phép một bean ban đầu không có nghĩa mọi object mà bean trả về đều an toàn để lộ cho expression. Quyền truy cập có thể lan theo object graph và các method mà object đó cung cấp.

### 3.4. Thăm dò tên bean và cấu trúc ứng dụng

Khi resolver cho phép thử nhiều tên bean, người viết expression có thể thăm dò những tên tồn tại thông qua khác biệt giữa kết quả phân giải thành công và lỗi.

Thông báo lỗi chi tiết có thể vô tình tiết lộ tên class, bean, package hoặc cấu trúc nội bộ. Không nên trả nguyên stack trace hoặc thông báo exception của Spring cho client không tin cậy.

Hãy dùng danh sách bean cho phép rõ ràng, trả thông báo lỗi tổng quát ở API và lưu thông tin kỹ thuật trong log nội bộ có kiểm soát.

### 3.5. Tiêu thụ tài nguyên

Bean được tham chiếu có thể thực hiện truy vấn lớn, gọi dịch vụ mạng, xử lý collection lớn hoặc tạo object tốn bộ nhớ. Một expression ngắn vẫn có thể kích hoạt method đắt đỏ.

Nếu người dùng có thể gửi nhiều expression hoặc lặp lại lời gọi tốn tài nguyên, hệ thống có thể bị quá tải. Vì vậy, kiểm soát bean reference cần đi cùng giới hạn số lần đánh giá, dữ liệu đầu vào và chi phí method.

## 4. Không cấp toàn bộ BeanFactory cho expression không tin cậy

### 4.1. Rủi ro của resolver tổng quát

Cấu hình sau thuận tiện cho expression nội bộ:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);
~~~

Nhưng resolver này ủy quyền tra cứu cho BeanFactory. Nếu expression do người dùng kiểm soát, việc cấp quyền phân giải rộng làm tăng đáng kể bề mặt truy cập.

Không nên dùng một allowlist ở giao diện rồi vẫn cấp BeanFactoryResolver cho context. Kiểm soát phải nằm tại resolver hoặc ranh giới thực thi mà người dùng không thể bỏ qua.

### 4.2. Không gắn resolver khi không cần

Đây là lựa chọn đơn giản và dễ kiểm tra nhất:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

// Không gọi setBeanResolver nếu biểu thức không cần bean reference.
~~~

Biểu thức không thể dùng @beanName nếu context không có resolver. Khi cần một giá trị từ service, hãy tính giá trị đó ở Java rồi đưa kết quả đã xác thực vào context dưới dạng biến hoặc property của DTO.

### 4.3. Cấp bean tối thiểu

Nếu expression thật sự cần gọi một vài dịch vụ, hãy tạo một facade hẹp với method chỉ phục vụ mục đích đó. Không cấp trực tiếp các bean có quyền rộng như application context, repository tổng quát hoặc service quản trị.

Ví dụ facade:

~~~java
public class PricingExpressionFacade {

    private final PricingService pricingService;

    public PricingExpressionFacade(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    public BigDecimal quote(String productCode) {
        return pricingService.quote(productCode);
    }
}
~~~

Facade chỉ cung cấp method quote theo hợp đồng đã chọn. Nó không công khai các thao tác quản trị, ghi dữ liệu tùy ý hoặc truy cập những dịch vụ khác.

Tuy nhiên, facade không tự động làm expression an toàn. Method quote vẫn cần xác thực argument, giới hạn truy vấn và bảo đảm không làm lộ dữ liệu của tenant khác.

## 5. Dùng BeanResolver theo allowlist

### 5.1. Ý tưởng

Nếu cần hỗ trợ bean reference, có thể triển khai BeanResolver chỉ cho phép một tập tên bean cụ thể. Resolver từ chối mọi tên khác trước khi truy cập BeanFactory.

Ví dụ:

~~~java
public final class AllowListBeanResolver implements BeanResolver {

    private final BeanFactoryResolver delegate;
    private final Set<String> allowedBeanNames;

    public AllowListBeanResolver(
            BeanFactory beanFactory,
            Set<String> allowedBeanNames) {

        this.delegate = new BeanFactoryResolver(beanFactory);
        this.allowedBeanNames = Set.copyOf(allowedBeanNames);
    }

    @Override
    public Object resolve(
            EvaluationContext context,
            String beanName) throws AccessException {

        if (!allowedBeanNames.contains(beanName)) {
            throw new AccessException(
                    "Bean reference is not allowed"
            );
        }

        return delegate.resolve(context, beanName);
    }
}
~~~

Đăng ký resolver:

~~~java
BeanResolver resolver = new AllowListBeanResolver(
        beanFactory,
        Set.of("pricingExpressionFacade")
);

StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

context.setBeanResolver(resolver);
~~~

Lúc này expression chỉ có thể phân giải tên pricingExpressionFacade qua resolver này.

Ví dụ hợp lệ:

~~~java
@pricingExpressionFacade.quote('P-100')
~~~

Ví dụ bị từ chối:

~~~java
@dataSource.getConnection()
~~~

### 5.2. Kiểm soát alias và FactoryBean dereference

Khi dùng allowlist, hãy quyết định rõ:

- Có cho phép bean alias hay không.
- Có cho phép tiền tố **&** để truy cập FactoryBean hay không.
- Có cho phép nhiều tên khác nhau cùng trỏ tới một bean hay không.
- Có cho phép tên bean có ký tự đặc biệt hay không.
- Có cần phân quyền theo tenant hoặc theo nhóm người dùng hay không.

Một allowlist theo tên cần khớp chính xác với quy ước tên mà resolver nhận được. Không nên vô tình mở rộng bằng wildcard hoặc cho phép mọi tên có chung prefix nếu các bean mới có thể được thêm vào sau này.

Ví dụ trên chỉ kiểm tra tên chính xác và chuyển tiếp cho BeanFactoryResolver. Nếu ứng dụng không cần FactoryBean dereference, hãy từ chối các tên bắt đầu bằng ký hiệu **&** và kiểm thử bằng biểu thức thực tế của phiên bản Spring đang sử dụng.

### 5.3. Allowlist bean chưa đủ để giới hạn method

Ngay cả khi chỉ cho phép một bean, expression vẫn có thể gọi các method mà bean công khai và truy cập object mà các method trả về.

Ví dụ:

~~~java
@pricingExpressionFacade.quote('P-100').getClass()
~~~

Đây là lý do facade phải có API nhỏ, trả về kiểu dữ liệu đơn giản và không để lộ object nội bộ. Cũng cần giới hạn các năng lực khác trong context, chẳng hạn type reference, constructor, property accessor và method resolver.

Allowlist tên bean là một lớp kiểm soát hữu ích, không phải sandbox hoàn chỉnh.

## 6. Giới hạn khả năng method invocation và property access

### 6.1. Không đưa service trực tiếp nếu chỉ cần dữ liệu

Nếu expression chỉ cần biết trạng thái của một khách hàng, hãy truy vấn bằng Java rồi đưa một giá trị Boolean vào context:

~~~java
boolean customerActive =
        customerService.isActive(customerId);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerActive", customerActive);
~~~

Expression chỉ cần:

~~~java
#customerActive
~~~

Cách này loại bỏ nhu cầu tham chiếu bean và giảm số method có thể được gọi từ expression.

### 6.2. Cân nhắc SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho một tập con SpEL với quyền hạn giới hạn hơn StandardEvaluationContext. Nó không cung cấp đầy đủ các khả năng như type reference, constructor và bean reference.

Ví dụ context chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Nếu cần method invocation, chỉ bật những resolver hoặc tính năng thật sự cần theo API builder của phiên bản Spring đang dùng. Không thêm bean resolver tổng quát để giải quyết một nhu cầu nhỏ.

SimpleEvaluationContext giúp giới hạn khả năng biểu thức nhưng không tự giới hạn kích thước đầu vào, số lần đánh giá, thời gian thực thi của method bên ngoài hoặc chi phí getter. Những giới hạn đó vẫn thuộc trách nhiệm ứng dụng.

### 6.3. Kiểm soát object graph

Root object, bean được phép và kết quả method có thể dẫn tới nhiều object khác. Hãy thiết kế object graph nhỏ:

- Dùng DTO hoặc expression view thay cho entity có nhiều quan hệ.
- Không expose ApplicationContext, BeanFactory hoặc service locator.
- Không trả về object có quyền quản trị từ facade.
- Hạn chế getter có tác dụng phụ hoặc thực hiện truy vấn.
- Tránh trả về collection lớn không có giới hạn.
- Chỉ cung cấp property mà predicate thực sự cần.

Kiểm soát root object và giá trị trả về giúp tránh việc expression đi từ một điểm truy cập nhỏ sang toàn bộ cấu trúc ứng dụng.

## 7. Phân quyền và cô lập theo tenant

Một bean có thể được dùng chung cho nhiều người dùng hoặc tenant. Nếu expression có thể gọi bean mà không truyền đầy đủ ngữ cảnh phân quyền, nó có thể truy cập dữ liệu ngoài phạm vi người dùng hiện tại.

Ví dụ, một repository method nhận customerId không đồng nghĩa người dùng được phép truy vấn bất kỳ customerId nào. Phân quyền phải được kiểm tra ở service hoặc repository theo principal và tenant thực tế.

Một số nguyên tắc:

- Không dựa vào expression để thực hiện authorization duy nhất.
- Kiểm tra quyền ở service trước khi trả dữ liệu hoặc thực hiện thao tác.
- Không để người dùng tự chọn bean quản trị hoặc tenant resolver.
- Không dùng một EvaluationContext dùng chung giữa các request có dữ liệu biến khác nhau.
- Tạo context theo phạm vi request hoặc lần đánh giá.
- Không đặt token, credential hoặc secret trong biến mà expression có thể đọc.

Nếu cùng một biểu thức được đánh giá cho nhiều tenant, cần bảo đảm bean được gọi nhận đúng tenant context từ nguồn đáng tin cậy. Không lấy tenantId do expression tự khai báo làm căn cứ duy nhất cho phân quyền.

## 8. Kiểm soát kích thước và tần suất đánh giá

Bean reference có thể kích hoạt method tốn tài nguyên. Vì vậy, cần giới hạn cả expression và cách nó được sử dụng:

- Giới hạn độ dài chuỗi trước khi parse.
- Giới hạn số lần đánh giá theo user, tenant hoặc khoảng thời gian.
- Giới hạn số lượng đối số và kích thước collection.
- Đặt timeout phù hợp cho các thao tác I/O bên trong service.
- Không expose method có truy vấn không giới hạn.
- Tránh gọi service từ predicate được chạy trên từng phần tử của collection lớn.
- Cache kết quả chỉ khi semantics và phạm vi quyền cho phép.
- Theo dõi thời gian parse, evaluate và số lần gọi bean.

Timeout ở tầng chờ kết quả không đảm bảo dừng được method Java đang chạy. Method cần có giới hạn thời gian và khả năng kết thúc có kiểm soát. Với workload không tin cậy có rủi ro cao, cân nhắc cô lập ở tiến trình hoặc môi trường riêng với giới hạn tài nguyên.

## 9. Xử lý lỗi bean reference

Các lỗi liên quan bean reference thường xuất hiện khi evaluate:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bean reference không được hỗ trợ | Context không có BeanResolver | Không dùng @beanName hoặc cấu hình resolver được kiểm soát |
| Không tìm thấy bean | Sai tên, alias hoặc bean chưa tồn tại | Kiểm tra cấu hình bean ở phía ứng dụng |
| Bean bị từ chối | Allowlist không cho phép tên đó | Xác nhận nhu cầu và cập nhật allowlist qua review |
| Không gọi được method | Method không tồn tại, không public hoặc argument không phù hợp | Kiểm tra API facade và kiểu đối số |
| Method ném exception | Logic bên trong bean thất bại | Xử lý nguyên nhân tại service và giữ cause |
| Không truy cập được property | Accessor không hỗ trợ hoặc property không tồn tại | Kiểm tra DTO và property accessor |
| Kết quả lộ dữ liệu ngoài phạm vi | Bean hoặc method trả về object quá rộng | Thu hẹp API và kiểm tra authorization |
| Đánh giá quá chậm | Method thực hiện I/O hoặc xử lý dữ liệu lớn | Giới hạn method, dữ liệu và tần suất |

Không nên bắt mọi lỗi bean reference rồi trả về null hoặc giá trị mặc định. Cách đó có thể che giấu việc tên bean bị viết sai, quyền bị từ chối hoặc service đang lỗi.

Phân biệt lỗi cấu hình, lỗi quyền và lỗi nghiệp vụ. Ở API công khai, trả thông báo an toàn; trong log nội bộ, lưu mã lỗi và nguyên nhân kỹ thuật theo chính sách bảo mật.

## 10. Ví dụ cấu hình an toàn hơn

Giả sử một rule chỉ cần gọi facade lấy giá sản phẩm. Thay vì cấp toàn bộ ApplicationContext, tạo facade và allowlist tên bean:

~~~java
PricingExpressionFacade facade =
        new PricingExpressionFacade(pricingService);

BeanFactory beanFactory = applicationContext;

StandardEvaluationContext context =
        new StandardEvaluationContext(expressionView);

context.setBeanResolver(
        new AllowListBeanResolver(
                beanFactory,
                Set.of("pricingExpressionFacade")
        )
);
~~~

Biểu thức:

~~~java
@pricingExpressionFacade.quote('P-100') > #minimumPrice
~~~

Các điểm cần bảo đảm:

1. Facade chỉ cung cấp method quote cần thiết.
2. Method xác thực product code và kiểm tra quyền truy cập dữ liệu.
3. Kết quả trả về là kiểu đơn giản, không phải service hoặc object quản trị.
4. Biến minimumPrice được tạo từ dữ liệu đã xác thực.
5. Context được tạo theo phạm vi sử dụng, không chia sẻ trạng thái giữa request.
6. Expression source được kiểm soát theo chính sách, độ dài và tần suất.
7. Các năng lực khác như type reference và constructor cũng được giới hạn nếu expression không tin cậy.

Nếu chỉ cần so sánh với minimumPrice, cách đơn giản hơn là gọi facade trong Java, lấy giá trị rồi truyền vào context. Khi đó expression không cần bean reference:

~~~java
BigDecimal price = facade.quote(productCode);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", price);
context.setVariable("minimumPrice", minimumPrice);
~~~

~~~java
#price > #minimumPrice
~~~

Cách này thường dễ kiểm soát hơn vì service được gọi ở một vị trí Java rõ ràng, còn SpEL chỉ xử lý dữ liệu đã chuẩn bị.

## 11. Checklist trước khi cho phép bean reference

Trước khi bật BeanResolver cho một nhóm expression, hãy xác nhận:

- Nguồn expression là đáng tin cậy hoặc đã được kiểm soát theo chính sách.
- Có lý do cụ thể cần bean reference; nếu không, không cấu hình resolver.
- Không cấp BeanFactoryResolver tổng quát cho expression không tin cậy.
- Resolver chỉ cho phép tên bean cụ thể và không dùng wildcard rộng.
- Alias và FactoryBean dereference được xử lý rõ ràng.
- Bean được phép có API nhỏ, method có tác dụng phụ được kiểm soát.
- Method không trả về ApplicationContext, service locator hoặc object nhạy cảm.
- Root object và object graph chỉ chứa dữ liệu cần thiết.
- Authorization được thực hiện ở service, không dựa vào expression.
- Tenant context đến từ nguồn đáng tin cậy.
- Độ dài expression, dữ liệu, số lần gọi và chi phí evaluate được giới hạn.
- Parse error, access error và service error được xử lý riêng.
- Không trả stack trace hoặc tên bean nội bộ cho client.
- Có kiểm thử cả bean được phép, bean bị từ chối và method lỗi.

## 12. Tổng kết

Bean reference cho phép SpEL truy cập bean Spring bằng cú pháp **@beanName** thông qua BeanResolver. BeanFactoryResolver là lựa chọn tiện lợi khi expression đáng tin cậy cần phân giải bean từ BeanFactory, nhưng nó có thể mở quyền truy cập rộng nếu được cấp cho expression do người dùng kiểm soát.

Để giảm rủi ro:

- Không cấu hình BeanResolver khi expression không cần bean.
- Tránh cấp toàn bộ BeanFactory cho expression không tin cậy.
- Nếu cần, dùng BeanResolver theo allowlist và chỉ expose facade có API hẹp.
- Kiểm soát method invocation, property access và object graph.
- Thực hiện authorization và tenant isolation trong service.
- Giới hạn kích thước, tần suất và chi phí thực thi.
- Không xem allowlist bean hoặc SimpleEvaluationContext là sandbox tài nguyên hoàn chỉnh.

SpEL nên nhận đúng dữ liệu và năng lực tối thiểu để diễn đạt quy tắc. Khi một biểu thức cần truy cập service có quyền cao hoặc thực hiện hành động nghiệp vụ quan trọng, hãy cân nhắc thực hiện hành động trong Java rồi chỉ đưa kết quả cần thiết vào EvaluationContext.