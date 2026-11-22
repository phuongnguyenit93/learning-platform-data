# Tham chiếu bean bằng @beanName trong SpEL

Spring Expression Language (SpEL) cho phép tham chiếu bean do Spring container quản lý bằng cú pháp `@beanName`. Sau khi lấy được bean, biểu thức có thể đọc property hoặc gọi method trên bean đó như với một object thông thường. Khả năng này giúp biểu thức kết nối với service, component hoặc object cấu hình trong ứng dụng.

Để tham chiếu hoạt động, EvaluationContext phải có một BeanResolver biết cách tìm bean theo tên. Một StandardEvaluationContext được tạo độc lập không tự biết ApplicationContext hoặc BeanFactory của ứng dụng. Vì vậy, cần cấu hình resolver phù hợp trước khi đánh giá biểu thức có `@beanName`.

## 1. Cú pháp tham chiếu bean

Cú pháp cơ bản:

    @beanName

Ví dụ:

    @pricingService
    @messageSource
    @orderPolicy

SpEL diễn giải `@pricingService` là tham chiếu tới bean có tên `pricingService` trong container. Kết quả là object bean, không phải chuỗi ký tự "pricingService".

Có thể tiếp tục đọc property hoặc gọi method trên bean:

    @pricingService.defaultCurrency
    @pricingService.calculateDiscount(#order)
    @messageSource.getMessage('order.created', null, null)

Trong ví dụ cuối, SpEL lấy bean messageSource rồi gọi method `getMessage` với các đối số tương ứng. Bean được tìm theo tên tại thời điểm biểu thức được đánh giá.

Dấu `@` ở đây là cú pháp của SpEL để tham chiếu bean. Nó không phải annotation Java như `@Component` hay `@Service`; các annotation đó thường giúp Spring đăng ký bean, còn `@beanName` dùng bean đã được container quản lý trong một expression.

## 2. Cấu hình BeanResolver cho StandardEvaluationContext

Trong một EvaluationContext tự tạo, cần đăng ký BeanResolver. Spring cung cấp `BeanFactoryResolver` để kết nối SpEL với BeanFactory:

    ConfigurableApplicationContext applicationContext =
            ...;

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setBeanResolver(
            new BeanFactoryResolver(
                    applicationContext.getBeanFactory()
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "@pricingService.defaultCurrency"
    ).getValue(context);

`BeanFactoryResolver` nằm trong package `org.springframework.context.expression`. Nó nhận một BeanFactory và dùng factory đó để tìm bean theo tên khi SpEL yêu cầu resolve bean reference.

Nếu đang có sẵn BeanFactory, có thể truyền trực tiếp vào constructor. Với ApplicationContext, có thể lấy BeanFactory thông qua API phù hợp của context đang sử dụng.

Nếu bỏ qua cấu hình BeanResolver, một StandardEvaluationContext thông thường không thể tự resolve `@pricingService`; việc đánh giá biểu thức sẽ thất bại vì không có resolver để tìm bean. Việc tạo parser không tự động kết nối parser với Spring container.

## 3. Dùng bean reference để gọi method

Sau khi bean được resolve, có thể gọi method trên bean:

    @pricingService.calculate(#order.subtotal, #customer.level)

Giả sử bean `pricingService` có method nhận hai đối số tương ứng. SpEL sẽ:

1. Resolve bean `pricingService` thông qua BeanResolver.
2. Đánh giá các đối số `#order.subtotal` và `#customer.level`.
3. Phân giải method `calculate` phù hợp với target và kiểu đối số.
4. Gọi method và trả về giá trị kết quả.

Ví dụ trong Java:

    context.setVariable("order", order);
    context.setVariable("customer", customer);

    BigDecimal discount = parser.parseExpression(
            "@pricingService.calculate(#order.subtotal, #customer.level)"
    ).getValue(context, BigDecimal.class);

Biến `order` và `customer` phải được đăng ký trong context. Bean `pricingService` được tìm bằng tên trong BeanFactoryResolver; nó không cần đăng ký như một biến SpEL riêng.

Có thể gọi method không tham số:

    @featureFlags.isNewCheckoutEnabled()

Hoặc đọc property:

    @applicationSettings.defaultLocale

Cần bảo đảm method/property thực sự tồn tại và kiểu kết quả phù hợp với nơi biểu thức sử dụng.

## 4. Tên bean có dấu chấm hoặc ký tự đặc biệt

Tên bean thường là identifier đơn giản, ví dụ `pricingService`. Nếu tên bean chứa dấu chấm hoặc ký tự cần phân định rõ, có thể đặt tên bean trong dấu nháy đơn sau `@`:

    @'legacy.pricing.service'

Cách viết này giúp parser hiểu toàn bộ phần được quote là tên bean. Tên trong biểu thức phải khớp với tên bean hoặc alias được container đăng ký.

Nếu có thể, nên dùng tên bean ngắn, rõ nghĩa và không cần escape. Tên bean được đặt theo quy ước nhất quán giúp expression dễ đọc và tránh lỗi do tên chứa ký tự đặc biệt.

## 5. Tham chiếu FactoryBean bằng dấu &

Spring có một loại bean đặc biệt là `FactoryBean`. Khi tra cứu tên FactoryBean thông thường, container trả về object do factory tạo ra. Nếu cần truy cập chính object factory, dùng tiền tố `&`:

    @myProduct
    @&myProduct

- `@myProduct` tham chiếu product do FactoryBean tạo ra.
- `@&myProduct` tham chiếu chính FactoryBean.

Ví dụ, nếu `reportFactory` là FactoryBean tạo ReportExporter:

    @reportFactory.exportFormat
    @&reportFactory.getObjectType()

Biểu thức thứ nhất làm việc với product mà factory cung cấp; biểu thức thứ hai làm việc với factory object. Chỉ dùng dấu `&` khi thực sự cần thao tác với FactoryBean, không phải product của nó.

## 6. Bean alias, scope và proxy

BeanResolver sử dụng tên bean thông qua BeanFactory. Nếu container đăng ký alias, alias cũng có thể được dùng để resolve bean theo các quy tắc của factory.

Kết quả nhận được phụ thuộc scope của bean:

- **Singleton:** các lần resolve thường trả về cùng instance singleton do container quản lý.
- **Prototype:** mỗi lần BeanFactory resolve có thể tạo một instance mới.
- **Request hoặc session scope:** việc resolve phụ thuộc vào request/session đang hoạt động và có thể thất bại nếu scope chưa được kích hoạt.

Bean lazy-init có thể được khởi tạo khi lần đầu được resolve. Vì vậy, chỉ việc đánh giá biểu thức cũng có thể kích hoạt quá trình khởi tạo bean.

Nếu bean được Spring AOP proxy, BeanFactoryResolver thông thường trả về object mà container quản lý, tức proxy khi bean được proxy hóa. Lời gọi method qua bean reference sẽ đi qua proxy và các interceptor tương ứng. Không nên tự lấy target object bên trong proxy nếu muốn giữ các hành vi transaction, security hoặc advice do Spring quản lý.

## 7. Bean reference trong biểu thức cấu hình Spring

Trong các vị trí mà Spring container tự quản lý việc đánh giá bean expression, framework có thể cung cấp BeanResolver phù hợp. Ví dụ, biểu thức trong annotation `@Value` có thể tham chiếu bean:

    @Value("#{ @pricingService.defaultCurrency }")
    private String currency;

Hoặc gọi method:

    @Value("#{ @featureFlags.isNewCheckoutEnabled() }")
    private boolean newCheckoutEnabled;

Các biểu thức kiểu này được Spring xử lý trong môi trường bean expression của container. Cách cấu hình đó khác với việc tự tạo một StandardEvaluationContext trong Java; với context tự tạo, hãy đăng ký BeanResolver như phần trước.

Không nhầm biểu thức `@Value` với cú pháp `@beanName`: `@Value` là annotation của Spring để inject giá trị, còn `@pricingService` bên trong chuỗi SpEL là bean reference.

## 8. Tách bean reference khỏi biến trong EvaluationContext

Bean reference và variable reference đều có thể trả về object, nhưng cách resolve khác nhau:

| Cú pháp | Nguồn dữ liệu | Cách đăng ký |
|---|---|---|
| `@pricingService` | Bean theo tên trong Spring container | BeanResolver |
| `#pricingService` | Biến trong EvaluationContext | `context.setVariable(...)` |
| `customer` | Property trên root object | Root object và PropertyAccessor |

Ví dụ:

    context.setVariable("calculator", calculator);

    #calculator.calculate(10)

Lời gọi trên sử dụng biến do ứng dụng đặt vào context. Trong khi đó:

    @calculator.calculate(10)

yêu cầu container có bean tên `calculator` và BeanResolver được cấu hình.

Dùng bean reference khi muốn expression truy cập component do Spring quản lý. Dùng biến khi muốn cung cấp object riêng cho một lần đánh giá hoặc một context cụ thể. Không nên đăng ký cùng một object dưới nhiều cách tham chiếu nếu điều đó làm biểu thức khó hiểu.

## 9. Giới hạn bean được phép truy cập

Bean reference có thể mở ra quyền truy cập tới các component trong ứng dụng. Nếu expression đến từ người dùng hoặc nguồn không hoàn toàn tin cậy, việc cung cấp BeanFactoryResolver cho toàn bộ BeanFactory có thể làm lộ quá nhiều bean.

Ví dụ, nếu context có thể resolve mọi bean, người viết expression có thể thử tham chiếu repository, service quản trị hoặc component có method gây tác dụng phụ. Chỉ cần bean được resolve không có nghĩa mọi method của bean đó đều phù hợp để gọi từ expression.

Một số nguyên tắc nên áp dụng:

- Chỉ đưa bean cần thiết vào phạm vi expression.
- Cân nhắc một custom BeanResolver chỉ resolve các tên nằm trong allowlist.
- Ưu tiên facade có API hẹp thay vì expose trực tiếp service có nhiều quyền.
- Tránh cung cấp repository, payment gateway, notification sender hoặc service quản trị cho expression không tin cậy.
- Kết hợp giới hạn bean với giới hạn method invocation, property access và quyền ghi.
- Xác thực đầu vào và quyền nghiệp vụ trong service; không dựa vào expression để tự cấp quyền.

Một custom BeanResolver có thể kiểm tra tên bean trước khi trả object. Nếu tên không được phép, resolver nên từ chối rõ ràng thay vì trả về một object tùy ý. Allowlist cần được xác định trong code cấu hình đáng tin cậy, không lấy từ nội dung expression.

## 10. Xử lý lỗi khi resolve bean

Một bean reference có thể thất bại trong các tình huống:

- Không có BeanResolver trong EvaluationContext.
- Bean name hoặc alias không tồn tại.
- FactoryBean không cung cấp product như mong đợi.
- Bean thuộc request/session scope nhưng scope chưa hoạt động.
- Khởi tạo bean thất bại do dependency hoặc cấu hình.
- Bean được resolve nhưng method/property được gọi không tồn tại hoặc không truy cập được.

Khi debug, hãy tách lỗi resolve bean khỏi lỗi gọi method. Trước tiên xác nhận BeanResolver đã được đăng ký và tên bean có trong BeanFactory. Sau đó kiểm tra chữ ký method, kiểu đối số, scope và lỗi gốc trong quá trình thực thi.

Không nên bắt mọi lỗi rồi trả null như thể bean không tồn tại một cách bình thường. Điều đó có thể che giấu lỗi cấu hình hoặc lỗi khởi tạo quan trọng. Hãy xử lý theo chính sách lỗi của ứng dụng và cung cấp thông tin chẩn đoán phù hợp.

## 11. Ghi nhớ

Cú pháp `@beanName` tham chiếu bean theo tên trong Spring container. Trong một StandardEvaluationContext tự tạo, cần đăng ký `BeanFactoryResolver` bằng `setBeanResolver(...)` để SpEL có thể tìm bean. Sau khi resolve, có thể đọc property hoặc gọi method trên bean như một object thông thường. Dùng `&beanName` khi cần chính FactoryBean thay vì product của nó. Bean scope, lazy initialization và AOP proxy vẫn do container quản lý. Vì bean reference có thể mở quyền truy cập tới service và method có tác dụng phụ, hãy giới hạn bean được expose và chỉ cho phép các thao tác phù hợp với mục đích của expression.
