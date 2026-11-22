# Không expose ApplicationContext toàn bộ cho expression SpEL

Spring Expression Language (SpEL) có thể truy cập object và gọi method được cung cấp qua EvaluationContext. Nếu đưa toàn bộ `ApplicationContext` hoặc `BeanFactory` vào root object hay variables, expression có thể dùng các API của container để tìm thêm bean và dependency. Phạm vi truy cập khi đó rộng hơn nhiều so với dữ liệu hoặc thao tác mà một use case cần.

Thiết kế an toàn nên cấp cho expression đúng capability cần thiết: dữ liệu đầu vào qua root object hoặc variables, và một số facade có API hẹp nếu cần gọi logic ứng dụng. Không biến ApplicationContext thành một service locator mà expression có thể tự do khám phá.

## 1. Vì sao ApplicationContext có quyền quá rộng?

ApplicationContext là trung tâm quản lý bean của Spring. Ngoài việc lấy bean theo tên hoặc kiểu, nó còn cung cấp các khả năng liên quan tới BeanFactory, resource loading, event publishing, environment và lifecycle của container.

Nếu expression có thể truy cập trực tiếp context, nó có thể thử gọi các API như:

    #applicationContext.getBean('paymentService')
    #applicationContext.getBeanFactory()
    #applicationContext.publishEvent(#event)

Tên method cụ thể và khả năng gọi còn phụ thuộc object, resolver và cấu hình EvaluationContext. Tuy nhiên, khi ApplicationContext được expose, expression có thể khám phá nhiều thành phần hơn dự định, thay vì chỉ dùng một API đã được giới hạn.

Rủi ro có thể gồm:

- Truy cập repository hoặc service không thuộc phạm vi use case hiện tại.
- Gọi method có thể ghi dữ liệu, gửi message, thanh toán hoặc thay đổi trạng thái.
- Đọc cấu hình hoặc bean chứa thông tin nhạy cảm.
- Resolve bean theo tên hoặc kiểu mà người viết expression tự chọn.
- Kích hoạt khởi tạo bean ngoài dự kiến khi gọi `getBean`.
- Tạo dependency ẩn, làm khó kiểm tra quyền, thứ tự khởi tạo và side effect.

Không nên xem ApplicationContext như một object dữ liệu thông thường. Nó là cổng truy cập tới container và các capability mà container quản lý.

## 2. Không đặt ApplicationContext làm root object hoặc variable

Tránh tạo context theo cách sau:

    StandardEvaluationContext context =
            new StandardEvaluationContext(applicationContext);

Hoặc:

    context.setVariable("applicationContext", applicationContext);

Trong cả hai trường hợp, expression có thể truy cập object ApplicationContext qua property/method access được bật trong EvaluationContext. Ví dụ:

    #applicationContext.getBean('orderRepository')

Nếu root object là ApplicationContext, expression có thể bắt đầu bằng property hoặc method không có tiền tố variable, tùy cách resolver xử lý. Nếu context được đăng ký thành variable, expression dùng `#applicationContext`.

Thay vào đó, hãy đặt root object là model dữ liệu đã được giới hạn cho use case:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setVariable("customer", customerView);

Root object và variables nên là DTO, view model hoặc object domain có API vừa đủ. Không đưa container, service locator hoặc object quản trị vào context chỉ để expression có thể tìm dependency khác.

## 3. Phân biệt bean reference với việc expose ApplicationContext

Cú pháp `@beanName` trong SpEL sử dụng BeanResolver của EvaluationContext để resolve bean theo tên. Đây là cơ chế riêng, không yêu cầu đặt ApplicationContext làm root object.

Ví dụ kết nối StandardEvaluationContext với toàn bộ BeanFactory:

    context.setBeanResolver(
            new BeanFactoryResolver(applicationContext.getBeanFactory())
    );

Cách này cho phép expression dùng `@pricingService`, nhưng BeanFactoryResolver có thể resolve nhiều bean mà BeanFactory quản lý. Nếu expression không hoàn toàn tin cậy, việc mở resolver toàn cục vẫn có thể quá rộng.

Cần phân biệt:

- **Expose ApplicationContext trực tiếp:** expression nhận object container và có thể gọi API trên container.
- **BeanFactoryResolver:** expression dùng cú pháp `@name` để resolve bean thông qua resolver.
- **Custom BeanResolver:** ứng dụng kiểm soát chính xác tên bean nào có thể được resolve.
- **Variable:** ứng dụng đưa một object cụ thể vào context bằng `setVariable`.

Nếu chỉ cần một capability, hãy cung cấp đúng object đó thay vì cung cấp container để expression tự tìm.

## 4. Dùng biến cho dữ liệu của lần đánh giá

Khi expression cần dữ liệu đầu vào, hãy truyền dữ liệu qua variables:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setVariable("customer", customerView);
    context.setVariable("discountRate", new BigDecimal("0.05"));
    context.setVariable("region", "VN");

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "total * (1 - #discountRate)"
    ).getValue(context);

Expression chỉ thấy root object và những biến đã được ứng dụng cung cấp. Nó không cần quyền tìm kiếm bean để đọc dữ liệu.

Nên ưu tiên object bất biến hoặc DTO chỉ đọc, có các property cần thiết cho biểu thức. Tránh đưa entity quản lý bởi persistence context nếu expression không cần quyền sửa entity hoặc truy cập các quan hệ sâu. Dữ liệu được truyền vào phải được kiểm tra quyền truy cập trước khi tạo EvaluationContext.

## 5. Dùng facade có API hẹp cho thao tác cần thiết

Nếu expression cần gọi một vài method, hãy tạo facade chỉ công khai đúng các thao tác đó. Ví dụ:

    public final class PricingExpressionFacade {

        private final PricingService pricingService;

        public PricingExpressionFacade(
                PricingService pricingService) {
            this.pricingService = pricingService;
        }

        public BigDecimal calculatePreview(OrderView order) {
            return pricingService.calculatePreview(order);
        }

        public String defaultCurrency() {
            return "VND";
        }
    }

Facade này không expose toàn bộ PricingService và không cung cấp các method như capture payment, refund hoặc delete order nếu use case không cần.

Có thể đưa facade thành variable:

    context.setVariable("pricing", pricingExpressionFacade);

    #pricing.calculatePreview(#root)

Cách này giữ rõ object nào được expression sử dụng. Nếu muốn dùng cú pháp bean reference, hãy resolve facade bằng một BeanResolver giới hạn ở tên bean cụ thể.

Ưu tiên method thuần tính toán hoặc chỉ đọc. Nếu expression cần khởi phát hành động ghi dữ liệu, cân nhắc gọi service nghiệp vụ từ Java sau khi đã kiểm tra quyền, thay vì để expression tùy ý gọi method có side effect.

## 6. Giới hạn tên bean bằng custom BeanResolver

Khi thật sự cần cú pháp `@beanName`, có thể triển khai BeanResolver chỉ trả về các facade được allowlist:

    public final class AllowlistBeanResolver
            implements BeanResolver {

        private final Map<String, Object> allowedBeans;

        public AllowlistBeanResolver(
                Map<String, Object> allowedBeans) {
            this.allowedBeans = Map.copyOf(allowedBeans);
        }

        @Override
        public Object resolve(
                EvaluationContext context,
                String beanName) throws AccessException {

            Object bean = allowedBeans.get(beanName);
            if (bean == null) {
                throw new AccessException(
                        "Bean is not available: " + beanName
                );
            }
            return bean;
        }
    }

Cấu hình context:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    Object preview = parser.parseExpression(
            "@pricing.calculatePreview(#root)"
    ).getValue(context);

Expression có thể resolve `@pricing`, nhưng các tên khác như `@paymentService`, `@orderRepository` hoặc `@applicationContext` sẽ bị từ chối nếu không được thêm vào allowlist.

Đây là implementation minh họa do ứng dụng tự xây dựng; `BeanResolver` và `AccessException` là API của Spring Expression. Allowlist phải được tạo từ cấu hình đáng tin cậy. Không cho expression hoặc người dùng tự khai báo thêm bean name được phép.

## 7. Allowlist bean vẫn cần giới hạn method và property

Chỉ giới hạn tên bean chưa đủ nếu facade được expose có quá nhiều method công khai. Khi bean đã được resolve, SpEL vẫn dùng các cơ chế method resolution và property access của EvaluationContext để làm việc với object đó.

Vì vậy, cần giới hạn cả:

- **Bean:** chỉ resolve facade cần thiết.
- **Method:** chỉ công khai method phù hợp với use case; tránh service tổng quát.
- **Property:** chỉ expose dữ liệu cần đọc; không cấp quyền ghi nếu không cần.
- **Root và variables:** chỉ cung cấp object đã được kiểm tra quyền và có phạm vi rõ ràng.
- **Expression features:** tránh bật type reference, constructor invocation hoặc các capability khác nếu use case không cần.

Không tạo facade với API tổng quát như `execute(String command)`, `getBean(String name)` hoặc `invoke(String method, Object... args)`. Những method này có thể tái tạo quyền truy cập rộng mà allowlist ban đầu định ngăn chặn.

## 8. Chọn EvaluationContext phù hợp

SimpleEvaluationContext được thiết kế cho các use case giới hạn như data binding. Nó không hỗ trợ bean reference, type reference hoặc constructor invocation; instance method invocation cũng không được bật mặc định.

Ví dụ context chỉ đọc:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(orderView)
                    .build();

Đây là lựa chọn phù hợp khi expression chỉ cần đọc property từ model.

StandardEvaluationContext cung cấp nhiều khả năng hơn, bao gồm BeanResolver khi được cấu hình, method invocation và type/constructor resolution theo các resolver được đăng ký. Chỉ dùng nó khi use case thực sự cần những capability đó và có chính sách giới hạn phù hợp.

Không chuyển sang StandardEvaluationContext chỉ để làm cho expression chạy được nếu expression đến từ người dùng hoặc nguồn cấu hình không hoàn toàn tin cậy. Hãy xác định capability tối thiểu trước rồi chọn context.

## 9. Không dùng ApplicationContext để tự khám phá dependency

Một expression không nên tự quyết định service nào cần dùng bằng cách gọi `getBean` theo dữ liệu động:

    #applicationContext.getBean(#serviceName).execute(#input)

Cách này tạo một service locator tổng quát. Người cung cấp expression hoặc dữ liệu `serviceName` có thể ảnh hưởng object nào được gọi, làm cho quyền truy cập khó kiểm soát và kiểm thử.

Hãy chuyển việc chọn service sang Java:

    Object result = switch (operation) {
        case "preview" -> pricingExpressionFacade.preview(input);
        case "validate" -> orderExpressionFacade.validate(input);
        default -> throw new IllegalArgumentException(
                "Unsupported operation"
        );
    };

Ví dụ trên minh họa một dispatch allowlist. Trong ứng dụng thực tế, lựa chọn operation phải được xác thực theo principal, tenant và use case. Expression chỉ nên nhận kết quả hoặc facade tương ứng sau khi Java đã quyết định capability được phép.

## 10. Cô lập context theo request, tenant và mục đích

Không dùng một EvaluationContext có root, variables hoặc resolver chứa trạng thái của request trước cho request tiếp theo. Khi ứng dụng xử lý nhiều người dùng hoặc tenant, việc tái sử dụng context không đúng cách có thể làm lộ dữ liệu hoặc capability giữa các phạm vi.

Hãy tạo context theo lần đánh giá hoặc theo một use case có vòng đời rõ ràng:

    EvaluationContext createContext(
            OrderView order,
            CustomerView customer,
            PricingExpressionFacade pricing) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable("customer", customer);
        context.setVariable("pricing", pricing);

        return context;
    }

Đây là cấu trúc minh họa. Trước khi tạo context, tầng ứng dụng phải xác nhận người gọi được phép xem order và customer tương ứng. Nếu facade có trạng thái theo request hoặc tenant, không lưu một instance dùng chung trong allowlist toàn cục.

Giữ context riêng cũng giúp kiểm thử dễ hơn: test có thể cung cấp một facade giả lập và chỉ các biến cần thiết, không cần khởi động toàn bộ ApplicationContext.

## 11. Bean scope, proxy và side effect

Nếu cần dùng bean do Spring quản lý, hãy lấy facade từ container ở tầng cấu hình và giữ nguyên proxy do Spring tạo. Không unwrap proxy để lấy target object, vì lời gọi có thể cần đi qua transaction, security, caching hoặc advice khác.

Chú ý scope của bean. Request/session-scoped bean chỉ hợp lệ trong scope tương ứng; prototype có thể tạo instance mới mỗi lần resolve. Không giữ một object scope ngắn trong resolver dùng chung lâu dài.

Cũng cần tránh gọi method có side effect trong expression chỉ dùng để hiển thị hoặc tính toán. Expression có thể được đánh giá nhiều lần. Nếu method gửi thông báo, ghi database hoặc gọi API, các lần đánh giá lặp lại có thể tạo hành động trùng. Hãy đặt hành động trong service nghiệp vụ với transaction, authorization và idempotency rõ ràng.

## 12. Kiểm thử ranh giới capability

Nên có test chứng minh expression chỉ truy cập được object đã được cấp:

1. Expression đọc được property cần thiết trên root object.
2. Expression dùng được các variables đã đăng ký.
3. Facade được allowlist có thể resolve và gọi method được phép.
4. Bean name không nằm trong allowlist bị từ chối.
5. ApplicationContext hoặc BeanFactory không xuất hiện trong root/variables của context dành cho expression không tin cậy.
6. Method ngoài phạm vi không được expose qua facade.
7. Context của tenant hoặc request này không chứa dữ liệu của tenant hoặc request khác.
8. Method có side effect không bị gọi ngoài số lần và thời điểm dự kiến.

Ví dụ kiểm tra bean bị từ chối:

    assertThrows(
            AccessException.class,
            () -> resolver.resolve(context, "paymentService")
    );

Ngoài unit test cho resolver và facade, hãy kiểm thử expression thông qua đúng EvaluationContext mà ứng dụng sử dụng. Điều đó giúp phát hiện cấu hình vô tình đăng ký thêm accessor, resolver hoặc object rộng quyền.

## 13. Ghi nhớ

Không đặt toàn bộ ApplicationContext hoặc BeanFactory làm root object hay variable cho expression. Các object đó cho phép khám phá dependency và có thể mở đường tới nhiều service, dữ liệu và thao tác ngoài phạm vi. Truyền dữ liệu bằng root object/variables đã được giới hạn; dùng facade có API hẹp cho capability cần thiết; nếu cần `@beanName`, dùng BeanResolver allowlist thay cho resolver toàn bộ BeanFactory. Giới hạn cả method, property và side effect, chọn SimpleEvaluationContext khi chỉ cần data binding, và cô lập EvaluationContext theo request hoặc tenant. Expression chỉ nên nhận đúng những gì use case cần.
