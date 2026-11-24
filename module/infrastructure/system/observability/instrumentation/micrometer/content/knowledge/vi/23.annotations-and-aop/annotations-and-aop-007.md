# Giới hạn proxy, lời gọi nội bộ cùng đối tượng và phương thức không được chặn

## Annotation không tự động chặn mọi lời gọi method

Trong Spring Boot, Micrometer có thể ghi metrics bằng API trực tiếp như Counter và Timer, hoặc dùng annotation như **@Timed** và **@Counted** kết hợp AOP. Annotation giúp đặt instrumentation gần method nghiệp vụ, nhưng nó chỉ hoạt động khi lời gọi đi qua cơ chế chặn tương ứng.

Spring AOP thường triển khai bằng **proxy** bao quanh Spring bean. Proxy nhận lời gọi từ bên ngoài, áp dụng advice/aspect rồi mới chuyển tiếp đến object đích. Nếu lời gọi không đi qua proxy, aspect không có cơ hội chạy dù method có annotation.

Vì vậy, khi một method có @Timed nhưng không thấy Timer, hoặc @Counted nhưng count không tăng, cần kiểm tra đường đi của lời gọi và loại proxy trước khi kết luận Micrometer không hoạt động.

Bài học này thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, tập trung vào đo lường ứng dụng Java bằng meter có ngữ nghĩa rõ, tích hợp Spring Boot và kiểm thử instrumentation. Hiểu giới hạn proxy giúp tránh bỏ sót metrics, ghi trùng thời lượng hoặc tạo cảm giác rằng annotation đã bao phủ toàn bộ đường thực thi.

## Spring AOP proxy hoạt động như thế nào?

### Lời gọi bên ngoài đi qua proxy

Giả sử Spring quản lý một bean có method được đánh dấu @Timed. Khi một component khác lấy bean từ ApplicationContext và gọi method, tham chiếu được inject thường là proxy. Proxy tìm các advisor/aspect phù hợp, chạy advice trước hoặc sau lời gọi, rồi chuyển tiếp đến target object.

Luồng khái quát:

~~~text
Caller
  |
  v
Spring bean proxy
  |
  +--> TimedAspect / other advice
  |
  v
Target object method
  |
  v
Return result
  |
  v
Advice records metric
~~~

Với lời gọi đi qua proxy, aspect có thể đo thời gian method, ghi count hoặc áp dụng các hành vi AOP khác. Việc ghi metric phụ thuộc aspect được đăng ký, pointcut khớp method và registry được cung cấp đúng.

### Spring AOP chỉ chặn những join point mà proxy nhìn thấy

Spring AOP dựa trên proxy tập trung vào method execution trên Spring bean. Nó không tự động chặn mọi thao tác trong JVM.

Các trường hợp thường không được proxy-based Spring AOP chặn:

- Lời gọi nội bộ từ method này sang method khác trên cùng target object.
- Lời gọi đến object được tạo trực tiếp bằng new, nằm ngoài Spring container.
- Gọi constructor hoặc truy cập field.
- Gọi static method.
- Gọi private method qua this.
- Method hoặc class không thể được proxy theo kiểu proxy đang dùng, ví dụ final class/method với CGLIB.

Điều quan trọng là phân biệt **method có annotation** với **method được gọi qua proxy**. Annotation chỉ cung cấp metadata cho aspect; nó không tự thay đổi cơ chế dispatch của Java.

## Self-invocation: lời gọi nội bộ bỏ qua proxy

### Vì sao this.inner() không chạy aspect?

Xem ví dụ:

~~~java
@Service
public class InvoiceService {

    public void processInvoice() {
        calculateTax();
    }

    @Timed("invoice.tax.calculation")
    public void calculateTax() {
        // Tinh thue.
    }
}
~~~

Nếu một bean khác gọi invoiceService.processInvoice() qua proxy, proxy chặn lời gọi processInvoice rồi chuyển đến target object. Bên trong target, lệnh calculateTax() tương đương this.calculateTax(). Lời gọi này diễn ra trực tiếp trên target object, không quay lại proxy.

Kết quả là TimedAspect không nhìn thấy lời gọi calculateTax và meter invoice.tax.calculation không được ghi như mong đợi. Việc chuyển calculateTax thành public cũng không sửa được self-invocation; vấn đề nằm ở đường đi của lời gọi, không chỉ visibility.

Nếu processInvoice cũng được đánh dấu @Timed và được gọi qua proxy, aspect của processInvoice vẫn có thể chạy. Chỉ lời gọi nội bộ calculateTax bị bỏ qua.

### Tách method được đo sang một Spring bean khác

Cách rõ ràng nhất là đặt ranh giới instrumentation ở một bean riêng:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public void processInvoice() {
        taxCalculator.calculateTax();
    }
}

@Service
public class TaxCalculator {

    @Timed("invoice.tax.calculation")
    public void calculateTax() {
        // Tinh thue.
    }
}
~~~

InvoiceService gọi TaxCalculator qua bean được inject. Nếu TaxCalculator được Spring quản lý và đã được proxy, lời gọi calculateTax đi qua proxy nên TimedAspect có thể chặn.

Cách này cũng tạo ranh giới trách nhiệm rõ: InvoiceService điều phối quy trình; TaxCalculator thực hiện phép tính thuế; instrumentation gắn với lời gọi public giữa hai component.

Không nên tách bean chỉ để thêm một annotation nếu việc tách làm mô hình nghiệp vụ khó hiểu. Nhưng khi hai thao tác có trách nhiệm độc lập và cần đo riêng, ranh giới bean thường là thiết kế dễ kiểm thử nhất.

### Các cách khác và trade-off

Có một số cách xử lý self-invocation khác, nhưng cần cân nhắc:

| Cách | Cách hoạt động | Hạn chế |
|---|---|---|
| Tách sang bean khác | Lời gọi đi qua Spring proxy của bean được inject | Có thể cần điều chỉnh ranh giới trách nhiệm |
| Self-injection | Inject proxy của chính bean rồi gọi qua tham chiếu đó | Dễ tạo phụ thuộc vòng hoặc làm thiết kế khó hiểu |
| AopContext.currentProxy() | Lấy proxy hiện tại rồi gọi method qua proxy | Cần expose proxy; phụ thuộc context AOP và làm code gắn chặt Spring |
| AspectJ weaving | Weave aspect vào bytecode thay vì chỉ dựa vào proxy | Cấu hình, build/runtime và debug phức tạp hơn |

Ưu tiên tách trách nhiệm thành bean khác khi phù hợp. Self-injection hoặc AopContext chỉ nên dùng khi có lý do thiết kế cụ thể và đã hiểu lifecycle proxy. Nếu cần chặn self-invocation, private method hoặc join point ngoài phạm vi proxy, cân nhắc AspectJ weaving thay vì kỳ vọng Spring proxy làm được.

## JDK dynamic proxy và CGLIB proxy

Spring AOP có thể dùng hai kiểu proxy chính. Kiểu proxy ảnh hưởng method nào có thể được gọi qua proxy.

### JDK dynamic proxy

JDK proxy tạo object proxy triển khai các interface mà target cung cấp. Caller thường tương tác qua interface.

~~~java
public interface PaymentService {
    void pay();
}

@Service
public class DefaultPaymentService implements PaymentService {

    @Timed("payment.execute")
    @Override
    public void pay() {
        // Xu ly thanh toan.
    }
}
~~~

Với JDK dynamic proxy, lời gọi qua interface có thể đi qua proxy. Method chỉ tồn tại trên concrete class nhưng không có trong interface sẽ không được truy cập qua kiểu proxy interface đó.

Nếu code inject concrete implementation hoặc ép kiểu không phù hợp, có thể gặp lỗi kiểu dữ liệu hoặc vô tình gọi target thay vì proxy. Nên inject interface khi cấu hình dùng JDK proxy và xác minh kiểu bean thực tế.

### CGLIB class-based proxy

CGLIB tạo subclass của target class để override method và chèn advice. Cách này cho phép proxy bean không cần interface, nhưng có giới hạn của kế thừa Java:

- Class final không thể được subclass.
- Method final không thể bị override để chèn advice.
- Private method không thể được override.
- Static method không được dispatch đa hình như instance method nên không thể được chặn theo cách này.
- Các ràng buộc visibility, package và module có thể ảnh hưởng khả năng override.

Vì vậy, nếu dùng CGLIB, hãy ưu tiên class và method không final, với public method làm API chặn rõ ràng. Không dựa vào annotation trên private hoặc final method để tạo metrics.

### Chọn proxy type trong Spring Boot

Spring Boot có cấu hình proxy-target-class để điều khiển kiểu proxy cho auto-proxying:

~~~yaml
spring:
  aop:
    proxy-target-class: true
~~~

Giá trị true yêu cầu class-based proxy trong các cơ chế auto-proxy tương ứng; false cho phép dùng JDK dynamic proxy khi bean có interface. Giá trị mặc định có thể phụ thuộc phiên bản và cấu hình, vì vậy hãy kiểm tra tài liệu Boot đang dùng và kiểu bean thực tế.

Đổi proxy type không khắc phục self-invocation. Cả JDK proxy và CGLIB đều cần lời gọi đi qua proxy. CGLIB cũng không thể chặn private/final method theo cơ chế override.

## Phương thức nào có thể được chặn?

### Public method là ranh giới an toàn nhất

Với Spring AOP proxy, hãy đặt annotation trên method public được gọi từ bean khác. Điều này phù hợp với API nghiệp vụ và tránh nhiều khác biệt giữa JDK proxy, CGLIB và phiên bản framework.

Protected hoặc package-private method có thể được chặn trong một số cấu hình class-based proxy và phiên bản Spring, nhưng không phải lúc nào cũng có thể truy cập qua JDK interface proxy. Private method không thể được proxy theo cơ chế method override. Static method không phải instance method và không được chặn như một lời gọi proxy thông thường.

Nếu method cần instrumentation là private helper, hãy cân nhắc đo method public bao quanh nó hoặc tách helper thành bean riêng nếu nó thực sự là một đơn vị nghiệp vụ độc lập.

### Class hoặc method final

Ví dụ:

~~~java
@Service
public final class ReportService {

    @Timed("report.generate")
    public void generate() {
        // Tao bao cao.
    }
}
~~~

Với class-based proxy, class final không thể được subclass. Tương tự, method final không thể bị override. Nếu dự án dùng JDK proxy qua interface, class target có thể final trong một số trường hợp vì proxy không cần subclass target; tuy nhiên lời gọi vẫn phải qua interface proxy và method phải nằm trên interface.

Không nên giải quyết bằng cách bỏ final một cách máy móc. Hãy chọn proxy model phù hợp với kiến trúc và xác định rõ method nào cần được chặn. Nếu thiết kế class final là yêu cầu quan trọng, có thể dùng interface proxy hoặc instrumentation khác phù hợp.

## Cấu hình @Timed và TimedAspect

### Đăng ký aspect

Annotation @Timed trong Micrometer cung cấp metadata cho TimedAspect. Trong cấu hình Spring AOP thông thường, cần đăng ký aspect bean và bảo đảm Spring AOP có mặt.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

Dependency management của Spring Boot nên quản lý phiên bản Micrometer tương thích. Nếu không dùng starter AOP, cần bảo đảm Spring AOP và thư viện AspectJ Weaver tương ứng đã có trên classpath.

Đăng ký TimedAspect:

~~~java
@Configuration(proxyBeanMethods = false)
public class MetricsAopConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Không giả định chỉ thêm annotation là aspect đã tự xuất hiện. Kiểm tra cấu hình auto-configuration của phiên bản dự án; nếu không có TimedAspect bean, đăng ký rõ ràng như ví dụ.

### Đặt annotation trên method public

~~~java
@Service
public class PaymentService {

    @Timed(
        value = "payment.processing",
        extraTags = {"operation", "charge"}
    )
    public Receipt charge(PaymentCommand command) {
        return paymentGateway.charge(command);
    }
}
~~~

Khi bean được gọi từ một bean khác qua proxy, TimedAspect có thể ghi Timer cho lời gọi charge. value xác định tên meter; extraTags thêm các tag tĩnh. Chỉ dùng tag có tập giá trị hữu hạn; không đưa command ID, customer ID hoặc exception message vào tag.

@Timed không thay thế việc chọn ranh giới đo đúng. Nếu method chỉ submit công việc bất đồng bộ rồi trả về ngay, thời lượng method có thể khác thời gian xử lý hoàn tất. Hãy kiểm tra hỗ trợ asynchronous/reactive của đúng phiên bản Micrometer và cách trả về của method. Nếu cần đo đến lúc công việc thực sự hoàn tất, có thể dùng Timer.Sample trong callback hoặc instrumentation reactive chuyên dụng.

### @Counted và CountedAspect

Tương tự, @Counted cần aspect hỗ trợ:

~~~java
@Configuration(proxyBeanMethods = false)
public class CountMetricsConfiguration {

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
~~~

Ví dụ method:

~~~java
@Service
public class OrderService {

    @Counted("orders.submit.invocations")
    public void submit(OrderCommand command) {
        // Xu ly don hang.
    }
}
~~~

CountedAspect đếm số lần method được gọi qua proxy theo cấu hình annotation. Nếu method được gọi nội bộ qua this.submit(...), lời gọi đó không đi qua proxy và có thể không được tính. Cũng cần xác định muốn đếm số lần gọi method hay số nghiệp vụ thành công; nếu chỉ muốn đếm thành công, có thể ghi Counter tại điểm xác nhận thành công thay vì dùng annotation bao quanh toàn method.

## Async và reactive: thời gian method không luôn là thời gian công việc

Một method có thể trả về CompletableFuture, Mono hoặc Flux. Khi đó method Java thường kết thúc trước khi công việc bất đồng bộ hoàn tất.

Ví dụ:

~~~java
public CompletableFuture<Result> processAsync() {
    return CompletableFuture.supplyAsync(this::doWork);
}
~~~

Nếu aspect chỉ đo thời gian gọi method đến lúc trả về future, Timer sẽ phản ánh thời gian tạo/submit future chứ không phải thời gian doWork hoàn tất. Một số implementation của TimedAspect có hỗ trợ theo dõi completion cho kiểu trả về cụ thể, nhưng khả năng đó phụ thuộc phiên bản và loại asynchronous type.

Với tác vụ cần đo chính xác đến completion, có thể đặt sample tại điểm bắt đầu và stop trong callback:

~~~java
Timer.Sample sample = Timer.start(registry);

CompletableFuture<Result> future = service.processAsync();

future.whenComplete((result, error) -> {
    Timer timer = registry.timer(
        "service.async.duration",
        "outcome",
        error == null ? "success" : "failure"
    );
    sample.stop(timer);
});
~~~

Ví dụ cần được điều chỉnh để bảo đảm callback chỉ hoàn tất sample một lần, tag outcome thuộc tập hữu hạn và sample gắn với đúng một lần thực thi. Với Reactor, nên ưu tiên Observation/reactive instrumentation có context propagation phù hợp; không giả định proxy đồng bộ có thể tự đo toàn bộ lifecycle của stream.

## Tại sao object tự tạo không được chặn?

Spring AOP chỉ tự động proxy các bean được quản lý trong ApplicationContext. Object được tạo trực tiếp:

~~~java
PaymentService service = new PaymentService();
service.charge(command);
~~~

không đi qua proxy do Spring tạo. Annotation trên method không có tác dụng AOP trong trường hợp này, trừ khi ứng dụng tự tạo và áp dụng proxy bằng cách khác.

Hãy inject bean qua constructor hoặc sử dụng bean do ApplicationContext quản lý. Trong test, gọi bean lấy từ Spring context thay vì tạo target class bằng new nếu mục tiêu là kiểm tra aspect.

Cũng cần tránh gọi target object đã được unwrapped từ proxy. Nếu code giữ cả proxy lẫn target rồi gọi target trực tiếp, lời gọi target sẽ bỏ qua advice.

## Cách kiểm tra proxy và xác minh metrics

### Kiểm tra bean có phải proxy không

Spring cung cấp tiện ích AopUtils:

~~~java
Object bean = applicationContext.getBean(PaymentService.class);

boolean proxy = AopUtils.isAopProxy(bean);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(bean);
boolean cglibProxy = AopUtils.isCglibProxy(bean);
~~~

Các kết quả giúp xác định Spring có tạo proxy và proxy thuộc loại nào. Tuy nhiên, chỉ có proxy không chứng minh TimedAspect đã khớp method; cần kiểm tra aspect bean, pointcut và meter sau khi gọi.

### Integration test cho @Timed

Ví dụ test:

~~~java
@SpringBootTest
class PaymentServiceMetricsTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    MeterRegistry registry;

    @Test
    void recordsTimerWhenCalledThroughSpringProxy() {
        paymentService.charge(new PaymentCommand());

        Timer timer = registry.find("payment.processing")
            .tag("operation", "charge")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Test phải dùng bean do Spring inject. Nếu gọi new PaymentService(...), test sẽ không đi qua proxy và không kiểm tra được AOP.

Trong test thực tế, mock gateway hoặc dùng fixture để không gọi hệ thống thanh toán thật. Nếu method có nhiều nhánh, kiểm tra cả success và exception theo semantics mà aspect ghi nhận.

### Test self-invocation

Có thể tạo một service có method ngoài gọi method được đánh dấu trong cùng class. Gọi method ngoài qua proxy rồi xác minh Timer của method nội bộ không được tạo. Sau đó tách method nội bộ sang bean khác và xác minh Timer xuất hiện khi gọi qua bean proxy.

Test này giúp xác định nguyên nhân cụ thể thay vì chỉ nhìn thấy count bằng 0 ở dashboard.

### Kiểm tra các điều kiện chặn

Checklist chẩn đoán:

1. Bean có được tạo bởi Spring không?
2. Caller có lấy bean qua ApplicationContext hoặc dependency injection không?
3. Bean có thực sự là proxy không?
4. Dự án đang dùng JDK hay CGLIB proxy?
5. Method có nằm trên interface nếu dùng JDK proxy không?
6. Method có public và không final không?
7. Lời gọi có phải self-invocation qua this không?
8. TimedAspect hoặc CountedAspect đã được đăng ký chưa?
9. MeterRegistry được inject có đúng registry đang quan sát không?
10. MeterFilter hoặc enable property có từ chối meter không?
11. Test có gọi method qua proxy và xác minh registry không?
12. Nếu asynchronous, Timer có dừng ở thời điểm hoàn tất thật không?

## Khi nào nên dùng AspectJ weaving?

Spring AOP proxy phù hợp với phần lớn instrumentation ở ranh giới public method giữa các Spring bean. Nếu cần chặn self-invocation, private method, constructor hoặc join point mà proxy không nhìn thấy, AspectJ weaving có thể phù hợp hơn.

AspectJ có thể weave advice vào bytecode lúc compile-time hoặc load-time, thay vì dựa hoàn toàn vào proxy bên ngoài target. Cách này có phạm vi join point rộng hơn nhưng đòi hỏi cấu hình build/runtime, agent hoặc plugin weaving tùy phương thức triển khai.

Không chuyển sang AspectJ chỉ để sửa một self-invocation đơn giản nếu có thể tách trách nhiệm thành bean riêng. Weaving làm tăng độ phức tạp khi build, debug và triển khai; chỉ chọn khi phạm vi interception rộng hơn là yêu cầu thực sự.

## Những sai lầm thường gặp

**Cho rằng annotation tự động chặn mọi method.** Aspect cần được đăng ký và lời gọi phải đi qua proxy.

**Gọi method nội bộ bằng this.** Self-invocation bypass proxy nên annotation ở method bên trong không được áp dụng.

**Tạo bean bằng new.** Object nằm ngoài Spring container không có proxy do Spring quản lý.

**Đặt annotation trên private method.** Proxy-based Spring AOP không thể chặn private method theo cơ chế method override.

**Dùng final class hoặc final method với CGLIB.** CGLIB không thể subclass class final hoặc override method final.

**Giả định JDK proxy chặn mọi method của concrete class.** JDK proxy chỉ expose interface mà proxy triển khai.

**Đổi proxy-target-class để sửa self-invocation.** JDK và CGLIB đều không biến lời gọi nội bộ trên target thành lời gọi qua proxy.

**Đo async method đến lúc method trả về nhưng gọi đó là thời gian xử lý.** Cần xác định aspect có theo dõi completion của kiểu trả về không; nếu không, dùng sample hoặc reactive instrumentation.

**Đăng ký aspect nhiều lần.** Nhiều aspect hoặc instrumentation trùng có thể ghi metric lặp. Kiểm tra bean và cấu hình AOP trước khi thêm cấu hình mới.

**Chỉ kiểm tra endpoint metrics.** Metric vắng mặt có thể do proxy không chặn, aspect không có, filter từ chối hoặc exporter không gửi. Kiểm tra từ lời gọi đến registry rồi đến backend.

## Checklist thiết kế annotation và AOP

Trước khi dùng @Timed hoặc @Counted, hãy xác minh:

1. Method được gọi qua Spring bean proxy không?
2. Bean được quản lý bởi ApplicationContext hay được tạo bằng new?
3. Method có phải self-invocation từ cùng target object không?
4. Proxy là JDK hay CGLIB?
5. Method có public, không private và không final không?
6. Class có final khi dùng CGLIB không?
7. TimedAspect hoặc CountedAspect đã được đăng ký đúng một lần chưa?
8. MeterRegistry được aspect sử dụng có đúng registry cần xuất không?
9. Annotation có tạo tag hữu hạn và tên meter ổn định không?
10. Async/reactive method có được đo đến completion thật không?
11. Test có xác minh proxy, lời gọi và meter trong registry không?
12. Nếu cần interception ngoài giới hạn proxy, AspectJ weaving có thực sự cần thiết không?

## Kết luận

Annotation như @Timed và @Counted chỉ ghi metrics khi aspect tương ứng được đăng ký và lời gọi đi qua cơ chế AOP. Với Spring AOP proxy, lời gọi từ bean khác có thể được chặn; lời gọi nội bộ qua this, object tự tạo, private/static method và một số class/method final có thể bỏ qua proxy hoặc không thể được proxy theo kiểu đang dùng.

Hãy ưu tiên instrumentation ở public method của Spring bean, tách thao tác cần đo sang bean khác khi self-invocation gây bỏ sót, xác minh JDK/CGLIB proxy và kiểm tra TimedAspect/CountedAspect. Với async hoặc reactive, đo đến thời điểm công việc thực sự hoàn tất; với yêu cầu interception rộng hơn proxy, cân nhắc AspectJ weaving. Integration test cần gọi bean qua Spring context và xác nhận meter trong registry để chứng minh instrumentation hoạt động đúng.
