# Tương tác giữa bean override với Spring AOP proxy

Spring TestContext Framework cho phép thay một bean trong ApplicationContext bằng Mockito mock hoặc spy. Spring AOP cũng có thể bọc bean bằng proxy để thực thi các advice như transaction, cache, security, logging hoặc audit. Khi hai cơ chế này cùng xuất hiện, test cần hiểu rõ mình đang gọi mock, spy, proxy hay đối tượng đích (target).

Một bean được thay thế trong test có thể làm thay đổi đường đi của lời gọi. Nếu thay chính service đang được áp dụng AOP bằng mock, test không còn kiểm tra logic thật của service và có thể không còn xác minh được advice như transaction hoặc cache. Nếu dùng spy trên bean đã được proxy, test phải chú ý đến đối tượng mà Mockito đang theo dõi và đối tượng mà Spring dùng để áp dụng advice.

Bài học này giải thích cách bean override tương tác với Spring AOP proxy, cách chọn đúng đối tượng để thay thế, cách kiểm tra advice vẫn được thực thi và cách chẩn đoán khi xác minh Mockito không khớp với proxy hoặc target.

## 1. Phân biệt target, proxy và bean được override

Spring AOP thường áp dụng advice thông qua proxy. Một lời gọi từ bên ngoài đi qua proxy trước khi đến đối tượng đích:

~~~text
Caller
  |
  v
Spring AOP proxy
  |
  +--> Advice: transaction
  |
  +--> Advice: security
  |
  +--> Advice: cache / audit / logging
  |
  v
Target object
  |
  v
Business method
~~~

Các thành phần có vai trò khác nhau:

- **Target** là đối tượng thực thi logic nghiệp vụ.
- **AOP proxy** là đối tượng đứng trước target để điều phối advice.
- **Advice** là hành vi được thực hiện trước, sau hoặc xung quanh lời gọi method.
- **Bean override** là cơ chế trong test thay thế hoặc bọc một bean trong ApplicationContext bằng test double.
- **Mockito mock/spy** là đối tượng do Mockito quản lý để cung cấp phản hồi giả lập hoặc theo dõi lời gọi.

Trong một ứng dụng không dùng AOP, tham chiếu bean thường trỏ trực tiếp đến target. Khi AOP được bật, tham chiếu được inject vào collaborator thường là proxy. Test gọi method trên proxy; Spring chạy advice rồi mới chuyển lời gọi đến target.

Bean override thêm một lớp tương tác nữa. Nó có thể thay bean bằng mock hoặc bọc bean hiện có bằng spy. Vì vậy, không nên mặc định rằng biến được inject trong test luôn là target gốc hoặc luôn là proxy AOP.

## 2. Hai chiến lược bean override phổ biến

Spring Framework 6.2 bổ sung các annotation Mockito bean override trong Spring TestContext:

- **@MockitoBean** tạo Mockito mock và đăng ký nó để thay thế bean phù hợp trong ApplicationContext. Với cách dùng trên field, annotation có thể tạo bean nếu chưa có bean phù hợp; có thể dùng thuộc tính **enforceOverride = true** khi test yêu cầu bean phải tồn tại để được thay thế.
- **@MockitoSpyBean** bọc một bean hiện có bằng Mockito spy. Vì cần bọc implementation đang tồn tại, test phải có bean phù hợp trong context; spy được hỗ trợ cho singleton bean.

Cả hai annotation đều thuộc package:

~~~java
org.springframework.test.context.bean.override.mockito
~~~

Ví dụ thay repository bằng mock:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {

    @MockitoBean
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void loadsOrderUsingMockRepository() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        Order order = orderService.findById("order-17");

        assertEquals("order-17", order.id());
        verify(orderRepository).findById("order-17");
    }
}
~~~

OrderService vẫn là bean thật. Chỉ OrderRepository được thay bằng mock. Đây thường là lựa chọn tốt khi mục tiêu là kiểm tra logic service trong khi kiểm soát dữ liệu trả về từ repository.

Ví dụ bọc một bean bằng spy:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpyTest {

    @MockitoSpyBean
    private OrderService orderService;

    @Test
    void observesCallToRealService() {
        orderService.findById("order-17");

        verify(orderService).findById("order-17");
    }
}
~~~

Spy giữ hành vi thật của bean theo mặc định và cho phép Mockito theo dõi lời gọi hoặc stub một phần hành vi. Nếu bean đồng thời được Spring AOP proxy, cần xác định rõ spy đang theo dõi lớp proxy hay target và bảo đảm test gọi qua đúng tham chiếu cần kiểm tra.

## 3. Điều gì xảy ra khi @MockitoBean thay bean có AOP?

Giả sử OrderService được áp dụng **@Transactional** hoặc một aspect audit. Khi chạy ứng dụng bình thường, Spring có thể inject một proxy thay cho target. Proxy điều phối advice trước khi gọi method của service.

Nếu test dùng **@MockitoBean** để thay chính OrderService, bean được cung cấp cho test là mock. Logic thật của OrderService không còn là phần thực thi chính của lời gọi. Vì vậy:

- Các nhánh nghiệp vụ trong OrderService không được chạy.
- Repository hoặc collaborator mà service thật sử dụng có thể không được gọi.
- Assertion về kết quả nghiệp vụ của service không còn phản ánh implementation thật.
- Test không thể dùng mock service để chứng minh transaction hoặc cache của service thật hoạt động đúng.

Không nên suy luận rằng vì bean mock có cùng kiểu với service nên toàn bộ AOP behavior của service thật chắc chắn còn nguyên. Bean override thay đổi đối tượng mà context cung cấp; proxy và advice thực tế còn phụ thuộc cấu hình và thứ tự xử lý bean trong context. Nếu mục tiêu là xác minh AOP trên service, hãy giữ service thật và thay thế collaborator bên dưới nó.

### Mẫu nên dùng: giữ service thật, mock collaborator

~~~java
@SpringJUnitConfig(OrderAopTestConfig.class)
class OrderServiceAopTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void runsRealServiceWithControlledRepository() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        orderService.confirm("order-17");

        verify(orderRepository).save(any(Order.class));
    }
}
~~~

Ở đây, OrderService được tạo từ cấu hình Spring và vẫn thực hiện logic thật. Repository được mock để test điều khiển dữ liệu và xác minh tương tác. Nếu OrderService được áp dụng AOP, test có thể tiếp tục gọi qua bean proxy của service.

Thuộc tính **enforceOverride = true** hữu ích khi test muốn thất bại nếu không có bean OrderRepository để thay. Điều đó tránh tình huống test vô tình tạo một mock mới trong khi cấu hình context đã thiếu repository production mà test dự kiến kiểm tra.

## 4. Proxy có thể là JDK dynamic proxy hoặc CGLIB

Spring AOP thường tạo một trong hai dạng proxy:

| Loại proxy | Đặc điểm | Hệ quả khi test |
|---|---|---|
| JDK dynamic proxy | Proxy dựa trên interface mà target triển khai | Nên inject và gọi bean qua interface |
| CGLIB proxy | Tạo subclass của class target | Có thể inject theo class, nhưng bị giới hạn bởi final class/method và các quy tắc subclass |

Nếu bean dùng JDK proxy, tham chiếu được inject có thể không phải instance của class implementation cụ thể. Test nên phụ thuộc vào interface mà bean công khai.

Ví dụ:

~~~java
public interface OrderOperations {
    void confirm(String orderId);
}

public class OrderService implements OrderOperations {

    @Override
    public void confirm(String orderId) {
        // Business logic
    }
}
~~~

Test có thể inject qua interface:

~~~java
@Autowired
private OrderOperations orderOperations;
~~~

Cách này tránh ép kiểu proxy về OrderService khi proxy chỉ công khai interface. Nếu cần kiểm tra proxy, Spring cung cấp các tiện ích trong **AopUtils**:

~~~java
assertTrue(AopUtils.isAopProxy(orderOperations));
Class<?> targetClass = AopUtils.getTargetClass(orderOperations);
assertEquals(OrderService.class, targetClass);
~~~

**AopUtils.isAopProxy(...)** cho biết tham chiếu có phải AOP proxy hay không. **AopUtils.getTargetClass(...)** giúp xác định class đích mà proxy đại diện. Hai phép kiểm tra này hữu ích khi test cần chứng minh bean được cấu hình qua AOP.

Không nên kiểm tra proxy bằng cách so sánh class runtime với class implementation. Với JDK proxy, class runtime là proxy class; với CGLIB, runtime class là subclass được tạo động.

## 5. Tương tác giữa @MockitoSpyBean và AOP proxy

**@MockitoSpyBean** dùng chiến lược wrap: Spring lấy bean hiện có rồi bọc bean bằng Mockito spy. Nếu bean đã được AOP proxy, việc bọc có thể tạo quan hệ nhiều lớp giữa spy và proxy. Test cần phân biệt:

- Tham chiếu mà ApplicationContext cung cấp cho consumer.
- Đối tượng Mockito đang ghi nhận lời gọi.
- Target object nằm phía sau AOP proxy.
- Advice có được chạy khi lời gọi đi qua tham chiếu đó hay không.

Hãy gọi bean qua tham chiếu được inject từ Spring nếu mục tiêu là xác minh hành vi của ứng dụng. Sau đó dùng Mockito verify trên đúng spy được Spring cung cấp.

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpyTest {

    @MockitoSpyBean
    private OrderService orderService;

    @Test
    void recordsInvocationOnSpiedBean() {
        orderService.findById("order-17");

        verify(orderService).findById("order-17");
    }
}
~~~

Ví dụ này minh họa việc xác minh lời gọi trên spy. Nếu bean còn được AOP proxy, hãy bổ sung assertion về advice hoặc side effect để chứng minh proxy chain hoạt động; chỉ verify method được gọi chưa đủ chứng minh transaction, security hay cache advice đã thực thi.

### Không gọi target trực tiếp khi cần kiểm tra advice

Nếu lấy target object phía sau proxy rồi gọi trực tiếp, lời gọi có thể bỏ qua proxy và do đó bỏ qua advice. Ví dụ:

~~~java
Object target = AopTestUtils.getUltimateTargetObject(orderService);
~~~

Việc lấy target hữu ích cho chẩn đoán hoặc một số phép xác minh Mockito đặc thù. Nhưng nếu gọi method trên **target** thay vì bean proxy, test không còn kiểm tra đường đi AOP thông thường.

Hãy giữ nguyên tắc:

- Gọi method qua bean proxy khi cần kiểm tra advice.
- Chỉ truy cập target khi cần quan sát cấu trúc proxy hoặc xử lý một trường hợp xác minh cụ thể.
- Không dùng target reference để thay thế bean trong một test được thiết kế nhằm kiểm tra transaction, security hoặc cache.

## 6. Dùng spy ở collaborator của aspect để kiểm tra advice

Một cách ít phụ thuộc vào cấu trúc proxy hơn là giữ bean được áp dụng AOP thật, còn spy collaborator mà advice gọi đến.

Ví dụ aspect ghi lại sự kiện sau khi OrderService xác nhận đơn:

~~~java
@Aspect
class OrderAuditAspect {

    private final AuditRecorder auditRecorder;

    OrderAuditAspect(AuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @AfterReturning(
        pointcut = "execution(* example.OrderService.confirm(..)) && args(orderId)"
    )
    public void recordConfirmation(String orderId) {
        auditRecorder.record("confirmed:" + orderId);
    }
}
~~~

Cấu hình test:

~~~java
@Configuration
@EnableAspectJAutoProxy
class OrderAopTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }

    @Bean
    AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }

    @Bean
    OrderAuditAspect orderAuditAspect(AuditRecorder recorder) {
        return new OrderAuditAspect(recorder);
    }
}
~~~

Test thay repository và spy recorder, nhưng giữ service và aspect thật:

~~~java
@SpringJUnitConfig(OrderAopTestConfig.class)
class OrderAuditAspectTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository orderRepository;

    @MockitoSpyBean
    private AuditRecorder auditRecorder;

    @Autowired
    private OrderService orderService;

    @Test
    void executesAuditAdviceThroughSpringProxy() {
        when(orderRepository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        assertTrue(AopUtils.isAopProxy(orderService));

        orderService.confirm("order-17");

        verify(auditRecorder).record("confirmed:order-17");
    }
}
~~~

Ví dụ giả định pointcut và model phù hợp với package của dự án. Ý tưởng quan trọng là test gọi OrderService từ ApplicationContext, để Spring AOP điều phối advice. Mockito spy chỉ quan sát AuditRecorder mà advice sử dụng. Nhờ vậy, test có thể kiểm tra advice được gọi mà không cần spy trực tiếp service proxy.

Nếu **@MockitoSpyBean** không thể tìm được một bean AuditRecorder duy nhất, hãy khai báo qualifier hoặc điều chỉnh cấu hình để có đúng bean mục tiêu. Spy cần một bean hiện có để bọc.

## 7. Kiểm tra @Transactional khi service có bean override

**@Transactional** thường được thực thi qua Spring AOP proxy. Khi một method được gọi từ bên ngoài qua proxy, transaction interceptor có thể mở, tham gia hoặc kết thúc transaction theo cấu hình.

Nếu thay chính service có **@Transactional** bằng **@MockitoBean**, test không còn kiểm tra transaction boundary của implementation service thật. Để kiểm tra transaction, hãy giữ service thật và thay repository hoặc một collaborator không phải đối tượng cần xác minh.

Ví dụ service kiểm tra trạng thái transaction trong method:

~~~java
@Service
public class TransactionProbeService {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Cấu hình test cần bật transaction management và cung cấp transaction manager:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionTestConfig {

    @Bean
    PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    TransactionProbeService transactionProbeService() {
        return new TransactionProbeService();
    }
}
~~~

Test gọi bean từ context:

~~~java
@SpringJUnitConfig(TransactionTestConfig.class)
class TransactionProxyTest {

    @Autowired
    private TransactionProbeService transactionProbeService;

    @Test
    void startsTransactionThroughProxy() {
        assertTrue(AopUtils.isAopProxy(transactionProbeService));
        assertTrue(transactionProbeService.isTransactionActive());
    }
}
~~~

Ví dụ yêu cầu DataSource và dependency transaction phù hợp trong test context. Trong dự án thực tế, có thể dùng database test hoặc transaction manager phù hợp. Assertion kiểm tra transaction đang hoạt động bên trong lời gọi, không chỉ kiểm tra rằng bean có proxy.

Nếu cần mock repository được gọi bên trong transaction, hãy dùng **@MockitoBean** trên repository và vẫn gọi service thật. Như vậy, test vừa kiểm soát collaborator vừa giữ đường đi qua transaction proxy.

## 8. Kiểm tra cache và security advice

Nguyên tắc tương tự áp dụng cho các advice khác.

### Cache

Nếu method có **@Cacheable**, việc gọi qua proxy có thể kiểm tra cache interceptor. Nếu thay service chứa method đó bằng mock, test không còn chứng minh cache behavior của implementation thật.

Một test cache có thể:

1. Giữ service thật trong context.
2. Dùng spy hoặc mock cho repository bên dưới.
3. Gọi cùng method hai lần qua bean Spring.
4. Xác minh repository chỉ được truy vấn theo chính sách cache đã cấu hình.
5. Xóa cache giữa các test để tránh trạng thái dùng chung.

Ví dụ minh họa:

~~~java
@SpringJUnitConfig(CacheTestConfig.class)
class OrderCacheTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository repository;

    @Autowired
    private OrderQueryService queryService;

    @Autowired
    private CacheManager cacheManager;

    @Test
    void cachesRepeatedLookup() {
        when(repository.findById("order-17"))
                .thenReturn(Optional.of(new Order("order-17")));

        queryService.findById("order-17");
        queryService.findById("order-17");

        verify(repository, times(1)).findById("order-17");
    }

    @AfterEach
    void clearCache() {
        cacheManager.getCache("orders").clear();
    }
}
~~~

Ví dụ giả định cache **orders** được cấu hình và method service có **@Cacheable** với key tương ứng. Nếu cache key, condition hoặc cache manager khác, expected số lần gọi phải theo cấu hình thật của dự án.

### Security

Với method security, proxy có thể kiểm tra quyền trước khi gọi method. Nếu thay service được bảo vệ bằng mock, test có thể bỏ qua chính method interception cần xác minh.

Hãy giữ bean được bảo vệ thật trong context, thay thế collaborator như repository hoặc permission lookup nếu cần kiểm soát dữ liệu, rồi gọi qua bean được inject. Kiểm tra kết quả được phép và exception khi bị từ chối bằng cấu hình security phù hợp.

Không nên coi việc verify một mock collaborator là bằng chứng rằng security advice đã chạy. Hãy xác nhận trực tiếp hành vi bảo mật ở ranh giới proxy.

## 9. AOP self-invocation vẫn là một giới hạn

Spring AOP proxy thường chặn lời gọi từ bên ngoài đi vào bean. Khi một method trong target gọi method khác trên cùng đối tượng bằng **this**, lời gọi nội bộ đó không đi qua proxy lần nữa.

Ví dụ:

~~~java
@Service
class ReportService {

    public void generate() {
        saveReport();
    }

    @Transactional
    public void saveReport() {
        // Save report
    }
}
~~~

Nếu **generate()** được gọi qua proxy, lời gọi nội bộ **this.saveReport()** bên trong target không quay lại proxy. Vì vậy, transaction advice trên **saveReport()** có thể không được áp dụng như mong đợi.

Dùng **@MockitoSpyBean** không tự sửa giới hạn self-invocation. Spy có thể ghi nhận lời gọi method, nhưng điều đó không chứng minh lời gọi đã đi qua AOP proxy và chạy advice.

Một cách thiết kế phổ biến là tách method cần advice sang collaborator khác:

~~~java
@Service
class ReportWriter {

    @Transactional
    public void saveReport() {
        // Save report
    }
}

@Service
class ReportService {

    private final ReportWriter reportWriter;

    ReportService(ReportWriter reportWriter) {
        this.reportWriter = reportWriter;
    }

    public void generate() {
        reportWriter.saveReport();
    }
}
~~~

Khi ReportService gọi ReportWriter qua bean proxy được inject, lời gọi có thể đi qua transaction advice. Test có thể giữ ReportWriter thật và kiểm tra transaction hoặc dùng mock ở một ranh giới khác tùy mục tiêu.

## 10. Xác minh đúng đối tượng bằng AopUtils và AopTestUtils

Khi Mockito báo lỗi xác minh hoặc test không thấy advice, hãy xác định đối tượng đang được sử dụng.

Spring cung cấp các tiện ích:

| API | Mục đích |
|---|---|
| **AopUtils.isAopProxy(bean)** | Kiểm tra bean có phải AOP proxy không |
| **AopUtils.isJdkDynamicProxy(bean)** | Kiểm tra proxy dựa trên JDK interface |
| **AopUtils.isCglibProxy(bean)** | Kiểm tra proxy dựa trên CGLIB |
| **AopUtils.getTargetClass(bean)** | Lấy class target mà proxy đại diện |
| **AopTestUtils.getTargetObject(bean)** | Lấy target trực tiếp nếu bean là proxy phù hợp |
| **AopTestUtils.getUltimateTargetObject(bean)** | Đi sâu qua các lớp proxy lồng nhau để lấy target cuối |

Ví dụ chẩn đoán:

~~~java
@Autowired
private OrderOperations orderOperations;

@Test
void inspectsProxyType() {
    assertTrue(AopUtils.isAopProxy(orderOperations));

    Class<?> targetClass = AopUtils.getTargetClass(orderOperations);
    assertEquals(OrderService.class, targetClass);

    if (AopUtils.isJdkDynamicProxy(orderOperations)) {
        assertTrue(orderOperations instanceof OrderOperations);
    }
}
~~~

Các tiện ích này giúp hiểu cấu trúc proxy. Chúng không thay thế phép kiểm tra hành vi advice. Nếu test gọi target trực tiếp sau khi lấy nó từ proxy, advice có thể bị bỏ qua.

### Khi Mockito verify báo đối tượng không phải mock

Lỗi có thể xảy ra khi test gọi **verify(...)** trên một proxy hoặc target khác với Mockito spy mà annotation tạo ra. Hãy kiểm tra:

1. Field nào được đánh dấu **@MockitoSpyBean**?
2. Consumer đang gọi bean reference nào từ ApplicationContext?
3. Bean có bị AOP proxy hoặc proxy lồng nhau không?
4. Mockito spy nằm ở lớp nào trong chuỗi wrapper?
5. Test có đang gọi target trực tiếp thay vì bean proxy không?

Chỉ dùng **AopTestUtils** khi cần xác minh một target thực sự là Mockito spy. Không thể gọi **verify(...)** trên bất kỳ target object nào chỉ vì lấy được nó từ proxy; đối tượng đó phải là mock hoặc spy của Mockito.

Nếu test cần kiểm tra advice, ưu tiên xác minh side effect của advice qua một collaborator hoặc probe riêng. Cách này ít phụ thuộc vào thứ tự wrapper giữa Mockito và Spring AOP.

## 11. Thứ tự advice và thứ tự wrapper là hai vấn đề khác nhau

Spring AOP có thể áp dụng nhiều advisor cho cùng một bean. Thứ tự thực thi advice phụ thuộc cấu hình order của advisor và quy tắc interceptor chain.

Mockito spy lại là một wrapper để theo dõi lời gọi. Việc spy bọc proxy hay proxy bọc spy là vấn đề về cấu trúc đối tượng được quản lý trong test context.

Không nên nhầm:

- **Advice order** quyết định các interceptor của Spring AOP chạy theo thứ tự nào.
- **Wrapper order** quyết định lời gọi đi qua Mockito spy và AOP proxy theo đường nào.
- **Bean override strategy** quyết định bean bị thay thế hay được bọc.

Nếu thứ tự advice có ý nghĩa nghiệp vụ, hãy kiểm tra kết quả quan sát được của advice hoặc dùng test chuyên biệt cho aspect. Đừng suy luận thứ tự advice chỉ từ thứ tự Mockito verify.

Ví dụ, một lời gọi có thể đi qua transaction advice rồi audit advice, hoặc theo thứ tự khác do cấu hình advisor. Nếu cần bảo đảm thứ tự, hãy đặt order tường minh cho advisor và viết test kiểm tra sự kiện hoặc trạng thái thể hiện thứ tự đó.

## 12. Dùng @MockitoBean cho collaborator bên trong AOP target

Một pattern hữu ích là thay collaborator mà target gọi đến, nhưng giữ bean được áp dụng AOP:

~~~text
Test
 |
 v
AOP proxy của OrderService
 |
 +--> Transaction / Audit advice
 |
 v
OrderService thật
 |
 v
MockitoBean: OrderRepository
~~~

Trong cấu trúc này:

- Service vẫn chạy implementation thật.
- AOP proxy vẫn là đường gọi từ test vào service.
- Repository được thay bằng mock để điều khiển kết quả và xác minh tương tác.
- Advice có thể được kiểm tra thông qua transaction state hoặc side effect riêng.

Đây là lựa chọn phù hợp khi test muốn kết hợp logic thật, collaborator giả lập và AOP infrastructure.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderModuleTestConfig.class)
class OrderServiceProxyTest {

    @MockitoBean(enforceOverride = true)
    private OrderRepository repository;

    @Autowired
    private OrderOperations orderOperations;

    @Test
    void invokesRepositoryThroughRealServiceProxy() {
        when(repository.findById("order-22"))
                .thenReturn(Optional.of(new Order("order-22")));

        assertTrue(AopUtils.isAopProxy(orderOperations));

        orderOperations.confirm("order-22");

        verify(repository).save(any(Order.class));
    }
}
~~~

Test này kiểm tra service bean được proxy và repository mock nhận lời gọi. Nếu muốn xác nhận một advice cụ thể, cần thêm assertion về hành vi do advice tạo ra. **isAopProxy** chỉ xác nhận proxy tồn tại, không chứng minh mọi advisor đã được cấu hình đúng.

## 13. Chọn mock, spy hay real bean trong từng tình huống

| Mục tiêu kiểm thử | Lựa chọn phù hợp | Điều cần giữ |
|---|---|---|
| Kiểm tra logic service | Service thật, mock/fake collaborator | Implementation service |
| Kiểm tra transaction của service | Service thật qua proxy, database hoặc transaction manager test | Transaction interceptor và target thật |
| Kiểm tra cache advice | Service thật qua proxy, mock repository | Cache interceptor và cache manager |
| Kiểm tra security advice | Bean được bảo vệ thật qua proxy | Method security configuration |
| Quan sát lời gọi của bean thật | @MockitoSpyBean | Đúng spy reference và đường gọi |
| Quan sát collaborator của aspect | @MockitoSpyBean trên collaborator | Service và aspect thật |
| Thay một dịch vụ ngoài | @MockitoBean trên gateway/client | Service đang được kiểm tra |
| Kiểm tra aspect độc lập | Aspect test với proxy và probe rõ ràng | Pointcut, advice và kết quả quan sát |

Không nên thay bean chỉ vì nó có nhiều dependency. Hãy xác định bean nào là đối tượng cần kiểm tra và bean nào là ranh giới có thể thay thế.

## 14. Các lỗi thường gặp khi bean override tương tác với AOP

### Thay chính bean cần kiểm tra bằng mock

Test có thể xanh vì mock trả về giá trị được cấu hình, trong khi logic thật và advice không được xác minh. Hãy giữ bean cần kiểm tra thật và thay collaborator.

### Cho rằng @MockitoBean giữ nguyên target và advice

Mock thay thế bean thực tế được context cung cấp. Không nên dựa vào tên kiểu bean để kết luận target và toàn bộ proxy chain vẫn hoạt động như production. Hãy kiểm tra cấu trúc proxy và hành vi advice cụ thể.

### Verify nhầm proxy hoặc target

Mockito chỉ xác minh được mock/spy tương ứng. Nếu test gọi proxy nhưng verify một target khác, assertion có thể không quan sát lời gọi. Hãy dùng cùng tham chiếu đã được Spring inject hoặc xác định rõ lớp wrapper.

### Gọi target trực tiếp

Lấy target bằng **AopTestUtils** rồi gọi method có thể bỏ qua advice. Chỉ gọi qua target khi mục tiêu không phải kiểm tra AOP.

### Spy một bean có side effect

Spy thường giữ implementation thật. Method có thể mở transaction, gửi request, ghi file hoặc phát message. Hãy kiểm soát collaborator và dữ liệu trước khi gọi.

### Inject concrete class trong khi bean dùng JDK proxy

JDK proxy có thể chỉ triển khai interface. Hãy inject qua interface hoặc cấu hình proxy class-based nếu kiến trúc thực sự cần và class/method đáp ứng giới hạn CGLIB.

### Nhầm self-invocation với lời gọi qua proxy

Method gọi method khác trên cùng target không tự quay lại proxy. Spy không làm thay đổi quy tắc này. Hãy tách collaborator hoặc thiết kế ranh giới method phù hợp.

### Chỉ kiểm tra proxy tồn tại

**AopUtils.isAopProxy(bean)** không chứng minh transaction, cache hoặc security advice đã chạy đúng. Hãy kiểm tra trạng thái transaction, số lần truy cập repository, kết quả cache hoặc quyền truy cập thực tế.

### Dùng spy thay cho một test aspect rõ ràng

Nếu mục tiêu là kiểm tra pointcut hoặc thứ tự advice, spy một service có thể tạo nhiều phụ thuộc vào cấu trúc proxy. Một probe hoặc collaborator được spy thường làm bằng chứng dễ hiểu hơn.

## 15. Quy trình chẩn đoán khi test AOP thất bại

Khi test có bean override và AOP nhưng kết quả không như mong đợi, hãy kiểm tra theo thứ tự:

1. **Xác định bean cần kiểm tra**: service thật, collaborator hay aspect?
2. **Xác định chiến lược override**: mock thay bean hay spy bọc bean?
3. **Kiểm tra context**: bean có được đăng ký và đúng profile không?
4. **Kiểm tra proxy**: dùng **AopUtils.isAopProxy** và **AopUtils.getTargetClass**.
5. **Kiểm tra kiểu proxy**: JDK hay CGLIB; test đang inject qua kiểu phù hợp không?
6. **Kiểm tra đường gọi**: lời gọi có đi qua bean từ ApplicationContext hay gọi trực tiếp target?
7. **Kiểm tra pointcut**: method và class có khớp biểu thức pointcut không?
8. **Kiểm tra advisor**: aspect hoặc transaction/cache/security configuration đã được bật chưa?
9. **Kiểm tra self-invocation**: method có được gọi từ bên ngoài target không?
10. **Kiểm tra Mockito reference**: verify đúng mock/spy đã được cấu hình và dùng trong test chưa?

Khi chẩn đoán, log tên bean, target class và trạng thái proxy có thể hữu ích. Không log dữ liệu nhạy cảm hoặc thông tin xác thực của collaborator.

## 16. Checklist thiết kế test có bean override và AOP

Trước khi hoàn tất test, hãy xác nhận:

- Bean đang được kiểm tra có phải implementation thật cần giữ lại không?
- Có đang thay nhầm service có advice bằng **@MockitoBean** không?
- Collaborator nào có thể được mock mà không làm mất hành vi cần kiểm tra?
- Nếu dùng **@MockitoSpyBean**, bean có tồn tại và là singleton không?
- Test đang gọi bean qua tham chiếu do Spring cung cấp hay gọi target trực tiếp?
- Bean có JDK proxy hay CGLIB proxy?
- Dependency được inject qua interface khi cần tương thích với JDK proxy chưa?
- Assertion có chứng minh advice chạy, thay vì chỉ chứng minh proxy tồn tại không?
- Nếu verify thất bại, Mockito đang theo dõi đúng spy reference không?
- Test có bị ảnh hưởng bởi self-invocation, cache state, transaction hoặc side effect không?
- Dữ liệu và trạng thái phụ thuộc có được cô lập giữa các test không?

## 17. Nguyên tắc lựa chọn

Khi test cần kiểm tra logic nghiệp vụ và AOP cùng lúc, hãy giữ bean mục tiêu thật trong ApplicationContext và thay những collaborator không phải trọng tâm bằng **@MockitoBean**. Nếu cần quan sát bean thật, dùng **@MockitoSpyBean** có chủ đích và xác định đúng tham chiếu spy. Khi cần kiểm tra advice, gọi method qua bean proxy do Spring cung cấp và xác minh hiệu ứng do advice tạo ra.

Mock, spy và AOP proxy giải quyết những vấn đề khác nhau. Mock thay hành vi của bean bằng phản hồi do test kiểm soát; spy theo dõi một implementation đang tồn tại; AOP proxy điều phối advice trước khi lời gọi đến target. Hiểu được vị trí của từng đối tượng trong đường đi của method giúp test xác minh đúng logic, đúng tương tác và đúng hành vi xuyên suốt của Spring.

