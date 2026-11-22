# Không expose bean ngoài phạm vi biểu thức cần thiết trong SpEL

Spring Expression Language (SpEL) có thể tham chiếu bean bằng cú pháp `@beanName` khi EvaluationContext được cấu hình một BeanResolver. Cách này tiện lợi vì biểu thức có thể gọi method hoặc đọc property của component do Spring quản lý. Tuy nhiên, nếu đưa toàn bộ BeanFactory vào phạm vi biểu thức, một expression có thể tiếp cận nhiều service và tài nguyên hơn mức use case cần.

Nguyên tắc nên áp dụng là **least privilege**: chỉ expose những bean thật sự cần cho biểu thức, với API hẹp và quyền hạn phù hợp. Việc một bean tồn tại trong Spring container không có nghĩa mọi expression đều cần được phép tham chiếu bean đó.

## 1. Rủi ro khi expose quá nhiều bean

Khi StandardEvaluationContext dùng BeanFactoryResolver trỏ tới BeanFactory của ứng dụng, biểu thức có thể resolve nhiều bean theo tên:

    @pricingService
    @orderRepository
    @paymentService
    @notificationService

Nếu những bean này được expose, expression có thể gọi các method công khai trên object được resolve. Tùy thiết kế ứng dụng, các method đó có thể:

- Đọc dữ liệu nhạy cảm hoặc dữ liệu ngoài phạm vi người dùng hiện tại.
- Ghi, sửa hoặc xóa dữ liệu trong database.
- Gửi email, phát message hoặc gọi dịch vụ bên ngoài.
- Thực hiện thao tác thanh toán, thay đổi quyền hoặc cập nhật trạng thái.
- Khởi tạo thêm object hoặc truy cập tài nguyên dùng chung.

Rủi ro không chỉ nằm ở tên bean. Một bean được expose có thể chứa nhiều method công khai, và ReflectiveMethodResolver mặc định có thể phân giải lời gọi method phù hợp trên object đó. Vì vậy, cho phép tham chiếu một bean rộng quyền cũng có thể gián tiếp mở nhiều thao tác không liên quan tới mục đích của expression.

Không nên đưa ApplicationContext, BeanFactory hoặc một service quản trị tổng quát vào expression context chỉ để biểu thức có thể tự tìm thêm dependency. Điều đó làm mất ranh giới rõ ràng giữa những capability mà ứng dụng chủ động cấp và những capability mà expression có thể tự khám phá.

## 2. Chỉ dùng BeanResolver khi expression thật sự cần bean

Bean reference được resolve thông qua BeanResolver của EvaluationContext. Với StandardEvaluationContext, có thể kết nối toàn bộ BeanFactory bằng BeanFactoryResolver:

    context.setBeanResolver(
            new BeanFactoryResolver(applicationContext.getBeanFactory())
    );

Cấu hình này thuận tiện cho expression nội bộ đáng tin cậy, nhưng phạm vi resolve phụ thuộc vào toàn bộ bean và alias mà factory cung cấp. Nếu expression đến từ người dùng, tenant, cấu hình có thể chỉnh sửa hoặc nguồn không hoàn toàn tin cậy, việc cấp resolver rộng như vậy có thể vượt quá nhu cầu.

Nếu expression chỉ cần đọc một giá trị đã tính sẵn, hãy truyền giá trị đó qua biến hoặc root object thay vì expose cả service. Nếu expression cần một vài thao tác tính toán, hãy cung cấp facade nhỏ chỉ có các method cần thiết.

## 3. Tạo BeanResolver theo allowlist

Có thể triển khai BeanResolver tùy chỉnh để chỉ resolve một tập tên bean đã được ứng dụng cho phép. Ví dụ:

    public final class AllowlistBeanResolver implements BeanResolver {

        private final Map<String, Object> allowedBeans;

        public AllowlistBeanResolver(Map<String, Object> allowedBeans) {
            this.allowedBeans = Map.copyOf(allowedBeans);
        }

        @Override
        public Object resolve(
                EvaluationContext context, String beanName)
                throws AccessException {

            Object bean = allowedBeans.get(beanName);
            if (bean == null) {
                throw new AccessException(
                        "Bean is not available to this expression: " + beanName
                );
            }

            return bean;
        }
    }

Khi tạo context, chỉ truyền những object được phép:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    Object result = parser.parseExpression(
            "@pricing.calculatePreview(#order)"
    ).getValue(context);

Trong ví dụ này, expression chỉ resolve được bean reference tên `pricing`. Những tên như `@paymentService` hoặc `@orderRepository` không nằm trong allowlist sẽ bị từ chối.

`AllowlistBeanResolver` là code minh họa do ứng dụng tự triển khai; `BeanResolver` là interface của Spring trong package `org.springframework.expression`. Trong triển khai thực tế, nên kiểm tra cả tên bean rỗng, alias, quy tắc đặt tên và cách báo lỗi theo chính sách của ứng dụng. Không lấy map allowlist từ dữ liệu do expression hoặc người dùng không tin cậy tự gửi lên.

## 4. Expose facade có API hẹp

Allowlist tên bean mới chỉ giới hạn được object nào có thể được resolve. Nó chưa giới hạn method nào trên object đó có thể được gọi. Nếu đưa trực tiếp một service lớn vào allowlist, expression vẫn có thể nhìn thấy nhiều method công khai của service.

Một facade dành riêng cho SpEL nên có API nhỏ và rõ ràng:

    public final class PricingExpressionFacade {

        private final PricingService pricingService;

        public PricingExpressionFacade(PricingService pricingService) {
            this.pricingService = pricingService;
        }

        public BigDecimal calculatePreview(OrderView order) {
            return pricingService.calculatePreview(order);
        }

        public String getDefaultCurrency() {
            return "VND";
        }
    }

Facade này chỉ công khai các thao tác mà expression cần. Những method như `capturePayment`, `refund`, `deleteOrder` hoặc `save` không được đưa ra API của facade nếu use case không cần chúng.

Ưu tiên method chỉ đọc hoặc tính toán. Nếu một expression thực sự cần khởi phát hành động, hãy để Java service xác thực quyền và điều phối hành động ở một bước tường minh. Không expose một method tổng quát như `execute(String command)` hoặc `invoke(String methodName, Object... args)` vì nó có thể biến facade thành cổng gọi tùy ý.

## 5. Không expose các bean hạ tầng và bean quyền rộng

Các object sau thường không phù hợp để đưa vào context của expression không tin cậy:

- ApplicationContext hoặc BeanFactory.
- Repository tổng quát có thể đọc hoặc ghi nhiều loại entity.
- Service thanh toán, chuyển tiền hoặc quản lý tài khoản.
- Notification sender, mail sender hoặc message publisher.
- File system, process execution hoặc network client.
- Security administration, user management hoặc permission service.
- Bean có khả năng tự resolve dependency hoặc gọi các service khác theo tên.

Nếu expression cần một kết quả từ các bean này, hãy tính kết quả trong tầng Java và truyền giá trị cần thiết vào context. Nếu cần một hành động có kiểm soát, expose một facade chỉ thực hiện đúng hành động đó sau khi tầng nghiệp vụ đã xác minh quyền.

## 6. Phân biệt bean reference và variable reference

Không phải mọi object mà expression cần đều phải được tham chiếu bằng `@beanName`. Có thể truyền object hoặc giá trị qua biến:

    context.setVariable("orderView", orderView);
    context.setVariable("discountRate", new BigDecimal("0.05"));

    #orderView.total * (1 - #discountRate)

Biến phù hợp với dữ liệu của lần đánh giá hiện tại, còn bean reference phù hợp với capability hoặc facade mà expression được phép sử dụng.

| Cú pháp | Nguồn | Phạm vi nên dùng |
|---|---|---|
| `@pricing` | BeanResolver | Facade hoặc capability đã allowlist |
| `#orderView` | Biến trong EvaluationContext | Dữ liệu của lần đánh giá |
| `property` | Root object | Dữ liệu được root object công khai |

Nếu chỉ cần một giá trị như thuế suất, tên hiển thị hoặc trạng thái, hãy truyền giá trị thay vì expose service chỉ để đọc một property. Điều này giúp expression ít phụ thuộc vào container và dễ kiểm thử hơn.

## 7. Giữ proxy và scope do Spring quản lý

Nếu bean được Spring AOP proxy, hãy expose bean instance do container trả về, giữ nguyên proxy. Không unwrap proxy để lấy target object, vì lời gọi có thể cần đi qua transaction, security interceptor, caching hoặc các advice khác.

Với bean có scope request, session hoặc prototype, cần quyết định rõ cách lấy instance. Không nên lưu một instance có scope ngắn vào allowlist dùng chung lâu dài. Có thể tạo resolver hoặc context theo request/use case để việc resolve tuân theo scope và vòng đời mà ứng dụng mong muốn.

Với expression chạy trong nhiều tenant hoặc nhiều người dùng, không dùng chung một allowlist chứa object có trạng thái riêng của request. Hãy tạo context và facade phù hợp với principal, tenant và mục đích của lần đánh giá đó.

## 8. BeanResolver không thay thế các giới hạn khác

Giới hạn tên bean là một lớp kiểm soát. Sau khi bean được resolve, expression vẫn có thể đọc property hoặc gọi method mà context cho phép. Do đó, cần giới hạn đồng thời:

- **Bean access:** bean name nào được resolve.
- **Method access:** method nào được phép gọi trên object đã expose.
- **Property access:** property nào được đọc hoặc ghi.
- **Evaluation features:** có cho phép assignment, type reference, constructor invocation hoặc bean reference hay không.
- **Input data:** biến, root object và đối số có nguồn gốc đáng tin cậy hay không.

SimpleEvaluationContext được thiết kế để giới hạn nhiều tính năng của SpEL và không hỗ trợ bean references. Nếu use case cần `@beanName`, thường phải dùng một EvaluationContext hỗ trợ BeanResolver, chẳng hạn StandardEvaluationContext với resolver tùy chỉnh. Khi đó, cần cấu hình rõ các capability khác thay vì coi BeanResolver allowlist là lớp bảo vệ duy nhất.

## 9. Cô lập context theo use case

Mỗi loại expression nên nhận một context riêng với đúng dữ liệu và capability cần thiết. Ví dụ:

    EvaluationContext createPricingContext(OrderView order) {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("order", order);
        context.setBeanResolver(
                new AllowlistBeanResolver(
                        Map.of("pricing", pricingExpressionFacade)
                )
        );

        return context;
    }

Đây là cấu trúc minh họa; service tạo context phải lấy order và facade sau khi đã xác thực quyền truy cập tương ứng. Không chia sẻ một StandardEvaluationContext có quyền rộng cho mọi người dùng hoặc mọi loại expression.

Nếu một expression chỉ dùng để kiểm tra điều kiện, hãy cung cấp root object chỉ đọc và tránh expose các bean có method thay đổi trạng thái. Nếu use case khác cần hành động, tạo context riêng cho use case đó với facade và chính sách rõ ràng.

## 10. Kiểm thử allowlist

Nên kiểm tra cả bean được phép và bean bị từ chối:

    context.setBeanResolver(
            new AllowlistBeanResolver(
                    Map.of("pricing", pricingExpressionFacade)
            )
    );

    parser.parseExpression("@pricing.getDefaultCurrency()")
            .getValue(context);

Lời gọi trên có thể resolve bean `pricing`. Một tham chiếu như:

    @paymentService.refund(#order.id)

phải bị từ chối nếu `paymentService` không có trong allowlist. Ngoài ra, cần kiểm tra rằng facade không công khai method ngoài phạm vi, resolver không vô tình chấp nhận alias không mong muốn và context của tenant này không thể resolve capability của tenant khác.

Với các method được expose, hãy kiểm tra số lần gọi, kiểu đối số, kết quả và side effect. Đặc biệt, nếu expression có thể được đánh giá lại hoặc retry, hãy bảo đảm method không gây hành động trùng ngoài ý muốn.

## 11. Ghi nhớ

Không expose toàn bộ Spring BeanFactory cho expression nếu use case chỉ cần một vài capability. Dùng BeanResolver allowlist để giới hạn tên bean, rồi expose facade có API hẹp để giới hạn method có thể gọi. Truyền dữ liệu của lần đánh giá qua biến hoặc root object thay vì mở service chỉ để đọc một giá trị. Giữ nguyên proxy và scope do Spring quản lý, cô lập context theo use case/tenant và kiểm soát cả property access, method invocation lẫn assignment. Một bean có mặt trong container không mặc nhiên thuộc phạm vi được phép của mọi expression.
