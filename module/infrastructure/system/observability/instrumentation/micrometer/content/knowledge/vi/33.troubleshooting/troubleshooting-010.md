# Annotation không có tác dụng do thiếu aspect, thiếu proxy hoặc tự gọi nội bộ

## Ba nhóm nguyên nhân cần phân biệt

Micrometer cung cấp annotation như @Timed và @Counted để gắn phép đo với method nghiệp vụ. Khi annotation có mặt nhưng không thấy Timer hoặc Counter, điều đó chưa đủ để kết luận registry hay exporter bị lỗi. Annotation chỉ là metadata; một aspect phải nhận diện annotation và chặn lời gọi method thì instrumentation mới chạy.

Trong Spring Boot, lỗi thường thuộc một trong ba nhóm:

1. **Thiếu aspect hoặc cấu hình AOP:** dependency hỗ trợ AOP không có, TimedAspect/CountedAspect chưa được đăng ký, hoặc pointcut không khớp annotation.
2. **Lời gọi không đi qua proxy:** object được tạo bằng new, bean không do Spring quản lý, caller giữ target thay vì proxy, hoặc kiểu inject không phù hợp với JDK proxy.
3. **Self-invocation:** một method gọi method khác trên cùng object bằng this, nên lời gọi nội bộ không quay lại proxy.

Sau khi xác nhận ba nhóm trên, mới kiểm tra meter có được đăng ký vào MeterRegistry hay bị MeterFilter từ chối, rồi kiểm tra endpoint hoặc exporter. Cần tách lỗi thực thi aspect khỏi lỗi xuất dữ liệu: aspect có thể đã chạy và cập nhật registry trong khi backend vẫn chưa nhận metric.

Bài học này thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER, nơi ứng dụng Java dùng Counter, Gauge, Timer, DistributionSummary và tag có kiểm soát, tích hợp Spring Boot và xuất metrics đến hệ giám sát. Quy trình dưới đây tập trung vào chẩn đoán annotation không có tác dụng trong Spring AOP proxy.

## Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Method có @Timed nhưng Timer không xuất hiện | Thiếu TimedAspect hoặc lời gọi không qua proxy | Kiểm tra bean aspect và AopUtils |
| @Counted không tăng | Thiếu CountedAspect hoặc self-invocation | Kiểm tra aspect và call path |
| Method bên ngoài có Timer, method nội bộ không có | Self-invocation | Tìm lời gọi this.method() |
| Gọi bean bằng interface chạy, ép kiểu implementation lỗi | JDK dynamic proxy | Kiểm tra kiểu proxy và interface |
| Bean có annotation nhưng không phải proxy | AOP auto-proxy chưa được bật hoặc không có advisor khớp | Kiểm tra dependency, aspect và cấu hình |
| Test tạo service bằng new không ghi metric | Object nằm ngoài Spring container | Inject bean từ ApplicationContext |
| Timer có trong registry nhưng backend không thấy | Filter, endpoint, scrape hoặc exporter | Kiểm tra registry rồi đến pipeline |
| Method private/final không được chặn | Giới hạn proxy-based AOP | Đưa instrumentation lên public method phù hợp |

Một lỗi có thể có nhiều nguyên nhân đồng thời. Ví dụ, thiếu starter AOP và self-invocation cùng tồn tại. Sửa một nguyên nhân không chứng minh các nguyên nhân khác đã được loại bỏ.

## Bước 1: Xác nhận dependency và cấu hình AOP

### Dependency cần thiết

Đối với ứng dụng Spring Boot, cần có Actuator/Micrometer và hạ tầng Spring AOP phù hợp. Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

Spring Boot dependency management nên quản lý phiên bản tương thích. Starter AOP cung cấp Spring AOP và các thành phần hỗ trợ auto-proxying. Chỉ có starter Actuator không đồng nghĩa mọi annotation Micrometer đã có aspect tương ứng.

Với cấu hình thủ công ngoài Spring Boot, cần bảo đảm Spring AOP, AspectJ Weaver và cơ chế auto-proxy được bật theo cách phù hợp với phiên bản Spring. Không thêm dependency hoặc cấu hình trùng lặp nếu ứng dụng đã có chúng qua một starter khác.

### Đăng ký TimedAspect

Micrometer cung cấp TimedAspect để xử lý @Timed. Nếu ứng dụng không tự cấu hình aspect này, annotation có thể không tạo Timer dù MeterRegistry vẫn hoạt động.

Ví dụ đăng ký bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class MetricsAspectConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

### Đăng ký CountedAspect

Tương tự, @Counted cần CountedAspect:

~~~java
@Configuration(proxyBeanMethods = false)
public class CountAspectConfiguration {

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
~~~

Kiểm tra ApplicationContext có đúng một bean aspect cần thiết. Đăng ký aspect hai lần có thể khiến một lời gọi bị chặn nhiều lần và metric tăng lặp.

Không giả định Spring Boot tự đăng ký TimedAspect hoặc CountedAspect trong mọi phiên bản/cấu hình. Kiểm tra bean thực tế và tài liệu của phiên bản Micrometer đang dùng. Nếu đã có auto-configuration riêng, không tạo thêm bean trùng.

### Kiểm tra AOP auto-proxy

Với Spring Boot starter AOP, auto-configuration thường thiết lập cơ chế proxy cho các advisor hợp lệ. Trong cấu hình Spring thuần, có thể cần bật auto-proxy bằng cấu hình Java phù hợp, ví dụ:

~~~java
@Configuration
@EnableAspectJAutoProxy
class AopConfiguration {
}
~~~

@EnableAspectJAutoProxy bật xử lý aspect dựa trên proxy của Spring; nó không tự tạo TimedAspect hoặc CountedAspect. Cần có cả aspect bean lẫn cơ chế proxy. Cũng không cần thêm annotation này một cách máy móc nếu Boot đã cấu hình auto-proxy.

## Bước 2: Xác nhận bean được Spring proxy

### Kiểm tra bean trong ApplicationContext

Spring AOP áp dụng cho Spring bean. Nếu code tạo object trực tiếp bằng new, Spring không tự bọc object đó bằng proxy:

~~~java
PaymentService service = new PaymentService();
service.authorize(command);
~~~

Trong trường hợp này, annotation vẫn nằm trên method nhưng không có proxy của Spring để chặn lời gọi.

Hãy inject bean qua constructor hoặc lấy bean từ ApplicationContext:

~~~java
@Service
public class CheckoutService {

    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(PaymentCommand command) {
        paymentService.authorize(command);
    }
}
~~~

Nếu PaymentService được Spring quản lý và advisor khớp method, lời gọi qua tham chiếu được inject có thể đi qua proxy.

### Dùng AopUtils để kiểm tra

Có thể kiểm tra bean có phải proxy hay không:

~~~java
Object bean = applicationContext.getBean(PaymentOperations.class);

boolean proxy = AopUtils.isAopProxy(bean);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(bean);
boolean cglibProxy = AopUtils.isCglibProxy(bean);
~~~

PaymentOperations trong ví dụ là interface của service. Nếu dự án dùng JDK proxy, lấy bean qua interface là cách kiểm tra phù hợp. Không giả định có thể lấy proxy bằng concrete implementation class.

Kết quả AopUtils.isAopProxy trả false cho thấy bean được lấy không phải AOP proxy. Tuy nhiên, true chỉ xác nhận bean có proxy; vẫn cần kiểm tra aspect, advisor và method cụ thể có được chặn hay không.

Có thể kiểm tra aspect bean riêng:

~~~java
assertThat(applicationContext.getBeansOfType(TimedAspect.class))
    .hasSize(1);
~~~

Nếu dùng @Counted, kiểm tra CountedAspect tương ứng. Kiểm tra bean tồn tại và kiểm tra method thực sự được intercept là hai xác minh khác nhau.

## Bước 3: Kiểm tra loại proxy và chữ ký method

### JDK dynamic proxy

JDK proxy tạo object triển khai các interface của target. Caller cần gọi qua method được khai báo trên interface.

~~~java
public interface PaymentOperations {
    Receipt authorize(PaymentCommand command);
}

@Service
public class DefaultPaymentService implements PaymentOperations {

    @Timed("payment.authorize")
    @Override
    public Receipt authorize(PaymentCommand command) {
        return gateway.authorize(command);
    }
}
~~~

Nếu dùng JDK proxy, hãy inject PaymentOperations. Không ép proxy về DefaultPaymentService vì object proxy không nhất thiết là instance của class implementation.

Method chỉ có trên implementation nhưng không có trên interface không thể được gọi qua kiểu JDK proxy đó. Đặt API cần intercept trên interface hoặc chọn class-based proxy nếu phù hợp.

### CGLIB class-based proxy

CGLIB tạo subclass để override method và chèn advice. Vì dựa trên kế thừa Java, có các giới hạn:

- Class final không thể được subclass.
- Method final không thể được override.
- Private method không thể được override.
- Static method không được chặn như instance method qua proxy.
- Visibility và ràng buộc package/module có thể ảnh hưởng việc override.

Đặt annotation trên public instance method không final là lựa chọn dễ dự đoán nhất cho proxy-based Spring AOP.

### Kiểm tra proxy-target-class

Spring Boot có thể được cấu hình dùng class-based proxy:

~~~yaml
spring:
  aop:
    proxy-target-class: true
~~~

true yêu cầu class-based proxy trong cơ chế auto-proxy tương ứng; false cho phép JDK proxy khi bean có interface. Giá trị mặc định và tương tác với cấu hình khác có thể phụ thuộc phiên bản Spring Boot.

Đổi proxy type không sửa self-invocation. Cả JDK và CGLIB đều cần lời gọi đi qua proxy. CGLIB cũng không thể override final method hoặc private method.

### Kiểm tra visibility và vị trí annotation

Đối với proxy-based AOP, nên đặt annotation trên public method được gọi từ bean khác. Private method không thể được chặn bằng proxy method interception. Static method cũng không phải instance method để proxy chặn.

Protected hoặc package-private method có thể có hành vi khác nhau tùy loại proxy và phiên bản Spring; không nên dựa vào chúng nếu cần cấu hình dễ dự đoán giữa JDK và CGLIB.

Nếu annotation nằm trên method private được gọi từ public method, chuyển phép đo lên public boundary hoặc tách thao tác thành bean riêng nếu nó có trách nhiệm độc lập.

## Bước 4: Tìm self-invocation

### Vì sao lời gọi nội bộ bỏ qua aspect?

Xem ví dụ:

~~~java
@Service
public class InvoiceService {

    public void process() {
        calculateTax();
    }

    @Timed("invoice.tax.calculation")
    public void calculateTax() {
        // Calculate tax.
    }
}
~~~

Một bean khác gọi process() qua proxy. Proxy chặn process rồi chuyển đến target object. Bên trong target, calculateTax() tương đương this.calculateTax(). Lời gọi này diễn ra trực tiếp trên target, không quay lại proxy, nên TimedAspect không nhận được lời gọi calculateTax.

Chuyển calculateTax thành public không giải quyết vấn đề. Nguyên nhân là self-invocation, không phải chỉ visibility.

### Cách khắc phục ưu tiên: tách sang bean khác

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public void process() {
        taxCalculator.calculateTax();
    }
}

@Service
public class TaxCalculator {

    @Timed("invoice.tax.calculation")
    public void calculateTax() {
        // Calculate tax.
    }
}
~~~

InvoiceService gọi TaxCalculator qua bean được inject. Nếu TaxCalculator được proxy, lời gọi đi qua proxy và aspect có thể thực thi.

Cách này phù hợp khi TaxCalculator là một trách nhiệm riêng. Không tách bean chỉ để thêm annotation nếu việc đó làm mô hình nghiệp vụ phức tạp hơn.

### Các cách khác

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Tách bean | Ranh giới proxy rõ, dễ test | Cần tổ chức lại component |
| Self-injection | Có thể gọi lại proxy của chính bean | Dễ tạo phụ thuộc vòng, code khó hiểu |
| AopContext.currentProxy() | Gọi qua proxy hiện tại | Cần expose proxy, code phụ thuộc Spring |
| AspectJ weaving | Có thể chặn join point ngoài proxy | Build/runtime và debug phức tạp hơn |

Ưu tiên tách bean khi phù hợp. Self-injection hoặc AopContext chỉ nên dùng khi có lý do cụ thể. AspectJ weaving phù hợp khi yêu cầu interception thật sự vượt giới hạn proxy.

## Bước 5: Xác minh aspect đã chạy trước khi kiểm tra exporter

### Tạo integration test tối thiểu

Dùng Spring Boot Test để lấy bean từ context, gọi method qua proxy và kiểm tra MeterRegistry:

~~~java
@SpringBootTest
class TimedAspectIntegrationTest {

    @Autowired
    PaymentOperations paymentOperations;

    @Autowired
    MeterRegistry registry;

    @Test
    void recordsTimerWhenInvokedThroughSpringProxy() {
        paymentOperations.authorize(new PaymentCommand());

        Timer timer = registry.find("payment.authorize").timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Trong test thực tế, mock gateway hoặc dùng fixture để tránh gọi hệ thống thanh toán thật. Nếu method được gọi nhiều lần trong cùng context, reset hoặc cô lập registry để count từ test trước không làm sai kết quả.

Test này cần dùng bean được Spring inject. Nếu tạo PaymentService bằng new, test sẽ không kiểm tra được AOP proxy.

### Tái hiện self-invocation bằng test

Tạo service có method ngoài gọi method được đánh dấu annotation trong cùng class. Gọi method ngoài qua proxy và xác minh Timer của method nội bộ không được ghi. Sau đó tách method sang bean khác và xác minh Timer xuất hiện.

Test này chứng minh call path là nguyên nhân. Nó cũng ngăn lỗi quay lại khi một refactor gộp hai bean thành một.

### Kiểm tra @Counted

Với @Counted, kiểm tra CountedAspect được đăng ký và gọi method qua proxy. Sau đó xác minh Counter được tạo với tên và tag dự kiến, count tăng đúng số lần gọi.

Nếu mục tiêu là đếm business success, hãy kiểm tra điểm ghi nhận có nằm sau khi nghiệp vụ thành công hay không. @Counted thường đếm invocation theo aspect; nó không tự hiểu rằng chỉ kết quả thành công mới được tính.

## Bước 6: Nếu aspect chạy nhưng không thấy meter

Sau khi xác nhận aspect và proxy, kiểm tra MeterRegistry.

### Kiểm tra tên và loại meter

Tên meter có thể khác do convention hoặc do annotation dùng tên mặc định. Nên đặt tên rõ trong annotation:

~~~java
@Timed(value = "payment.authorize")
public Receipt authorize(PaymentCommand command) {
    return gateway.authorize(command);
}
~~~

Sau khi gọi method, inspect registry trong test:

~~~java
registry.getMeters().forEach(meter ->
    System.out.println(meter.getId())
);
~~~

Không dump toàn bộ meter trong production request path. Dùng test hoặc endpoint chẩn đoán được bảo vệ.

### Kiểm tra MeterFilter và enable property

Meter có thể bị từ chối bởi management.metrics.enable hoặc MeterFilter. Kiểm tra filter DENY theo tên, tag và các giới hạn maximum allowable metrics/tags.

Nếu meter bị filter, aspect vẫn có thể được gọi nhưng registry không đăng ký meter theo yêu cầu. Dùng SimpleMeterRegistry hoặc context test với filter thực tế để khoanh vùng.

### Kiểm tra registry mà aspect sử dụng

TimedAspect cần MeterRegistry. Nếu ứng dụng có nhiều registry hoặc tự tạo registry riêng, xác nhận aspect đang ghi vào registry được exporter sử dụng.

Không tạo một SimpleMeterRegistry riêng trong cấu hình production chỉ để cấp cho aspect nếu ứng dụng cần xuất qua Prometheus hoặc OTLP registry. Trong Spring Boot, inject registry do context quản lý và xác minh bean type/registry composition.

## Bước 7: Phân biệt lỗi instrumentation với lỗi export

Nếu meter đã có trong registry và count tăng, annotation đã thực thi. Khi đó kiểm tra tiếp:

1. Prometheus registry có expose sample qua scrape() không?
2. Endpoint /actuator/prometheus có được expose và truy cập được không?
3. Prometheus server có scrape target thành công không?
4. OTLP registry có export đúng endpoint, protocol và path không?
5. Collector có receiver và metrics pipeline phù hợp không?
6. Backend có nhận và lưu đúng resource attributes, name và tags không?

Không dùng việc backend chưa thấy metric để kết luận aspect không hoạt động. Đọc MeterRegistry trước để phân định lỗi nằm ở instrumentation hay pipeline.

## Sơ đồ chẩn đoán nhanh

~~~text
Annotation không tạo metric
          |
          v
Có TimedAspect / CountedAspect?
       /             \
     No               Yes
     |                 |
Đăng ký aspect     Bean có phải proxy?
                       /       \
                     No         Yes
                     |           |
              Kiểm tra Spring   Call có đi qua proxy?
              bean/AOP config      /       \
                                  No         Yes
                                  |           |
                            Sửa self-call   Method có được
                            hoặc new object  proxy chặn?
                                               /     \
                                             No       Yes
                                             |         |
                                      Kiểm tra JDK/  Metric có trong
                                      CGLIB/visibility registry?
                                                      /     \
                                                    No       Yes
                                                    |         |
                                               Filter/name/  Export,
                                               registry      scrape,
                                                             backend
~~~

Sơ đồ là thứ tự khoanh vùng. Nếu nhiều điều kiện sai, cần sửa và xác minh từng điều kiện, không dừng ở nhánh đầu tiên.

## Checklist điều tra

Khi annotation không có tác dụng, kiểm tra theo thứ tự:

1. Dependency Actuator/Micrometer và Spring AOP đã có chưa?
2. TimedAspect hoặc CountedAspect đã được đăng ký đúng một lần chưa?
3. Cơ chế auto-proxy có được bật không?
4. Bean có được tạo bởi Spring và caller có dùng bean proxy không?
5. AopUtils có xác nhận bean là proxy không?
6. Proxy là JDK hay CGLIB?
7. Với JDK proxy, method có nằm trên interface được expose không?
8. Với CGLIB, class và method có final không?
9. Method có phải public instance method phù hợp không?
10. Có lời gọi nội bộ bằng this không?
11. Có object được tạo bằng new hoặc target bị unwrap không?
12. Aspect có khớp method và annotation không?
13. Timer/Counter có xuất hiện và tăng trong MeterRegistry không?
14. MeterFilter hoặc management.metrics.enable có từ chối meter không?
15. Aspect có dùng đúng registry mà exporter đang publish không?
16. Endpoint, scrape, OTLP transport và Collector có hoạt động không?

Ghi lại bằng chứng cho từng bước: bean name/type, kết quả AopUtils, số lần gọi method, meter name/tag/count trong registry và trạng thái exporter. Điều này giúp tránh thay đổi cấu hình dựa trên phỏng đoán.

## Những sai lầm thường gặp

**Chỉ thêm @Timed rồi chờ metric xuất hiện.** Annotation cần TimedAspect và AOP proxy.

**Cho rằng Actuator tự đăng ký mọi aspect.** Kiểm tra bean aspect thực tế theo phiên bản và cấu hình.

**Thêm @EnableAspectJAutoProxy nhưng không tạo TimedAspect.** Auto-proxy không tự cung cấp aspect xử lý @Timed.

**Tạo service bằng new.** Object không đi qua Spring proxy.

**Gọi method nội bộ bằng this.** Self-invocation bypass proxy dù method được đánh dấu public.

**Đổi JDK sang CGLIB để sửa self-invocation.** Cả hai đều cần call đi qua proxy.

**Đặt annotation trên private hoặc final method.** Proxy-based interception không thể chặn các method đó theo cách thông thường.

**Inject concrete class khi bean là JDK proxy.** Dùng interface mà proxy triển khai.

**Đăng ký aspect hai lần.** Có thể ghi Timer/Counter lặp cho một invocation.

**Chỉ nhìn dashboard khi điều tra.** Kiểm tra MeterRegistry trước để xác định aspect có ghi dữ liệu không.

**Đếm invocation nhưng gọi metric là business success.** Định nghĩa lại semantics hoặc ghi Counter tại điểm nghiệp vụ thành công.

## Kết luận

Annotation @Timed hoặc @Counted không tự thực thi. Cần có aspect tương ứng, Spring phải tạo proxy cho bean và caller phải gọi method qua proxy. Thiếu một trong các điều kiện này có thể khiến metric không xuất hiện.

Hãy kiểm tra dependency và aspect bean trước, xác minh proxy bằng AopUtils, xem loại proxy và giới hạn method, rồi tìm self-invocation hoặc object tạo bằng new. Khi aspect đã chạy, kiểm tra MeterRegistry, MeterFilter và registry mà exporter sử dụng trước khi điều tra endpoint hoặc backend. Ưu tiên tách thao tác cần đo sang một Spring bean khác để tạo ranh giới proxy rõ ràng, và dùng integration test gọi bean từ Spring context để xác nhận metric được ghi đúng.
