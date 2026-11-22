# Thứ tự khởi tạo bean và expression evaluation trong Spring

Trong Spring, thời điểm một biểu thức Spring Expression Language (SpEL) được đánh giá phụ thuộc vào nơi biểu thức được sử dụng. Biểu thức trong bean definition hoặc `@Value` thường được đánh giá khi container đang tạo và nạp dependency cho bean. Biểu thức trong method security được đánh giá khi method được gọi. Với SpEL dùng trực tiếp trong Java, ứng dụng quyết định thời điểm gọi `getValue()`.

Vì vậy, expression evaluation không phải một bước độc lập luôn chạy ở đầu hoặc cuối quá trình khởi động. Nó xảy ra tại điểm Spring hoặc ứng dụng cần giá trị của expression. Nếu biểu thức tham chiếu bean bằng `@beanName`, việc resolve đó còn có thể kích hoạt quá trình tạo bean được tham chiếu.

## 1. Bức tranh tổng thể của ApplicationContext refresh

Khi ApplicationContext được refresh, Spring chuẩn bị BeanFactory, xử lý các bean definition và đăng ký những thành phần hạ tầng trước khi khởi tạo phần lớn singleton thông thường.

Có thể hình dung các giai đoạn chính như sau:

1. Tạo hoặc nạp BeanFactory và các BeanDefinition.
2. Chạy BeanFactoryPostProcessor và BeanDefinitionRegistryPostProcessor để điều chỉnh metadata bean.
3. Đăng ký BeanPostProcessor để tham gia vào quá trình tạo bean.
4. Khởi tạo các singleton eager còn lại trong giai đoạn hoàn tất refresh.
5. Phát các callback khởi tạo, hoàn tất refresh và công bố context sẵn sàng.

Đây là thứ tự tổng quát; một số bean hạ tầng được tạo sớm hơn để phục vụ chính các giai đoạn trên. Không phải tất cả bean đều được tạo cùng lúc, và bean lazy có thể chỉ được tạo khi có lần truy cập đầu tiên.

SpEL có thể được đánh giá ở nhiều điểm trong chuỗi này. Ví dụ, giá trị SpEL trong một bean definition có thể được resolve khi bean đó được tạo; `@Value` được resolve trong quá trình inject dependency; còn expression trong `@PreAuthorize` chỉ được đánh giá khi method security xử lý một lời gọi method.

## 2. Lifecycle của một bean thông thường

Với một bean được tạo trong quá trình khởi động, trình tự thường gồm các bước:

1. **Instantiate:** gọi constructor hoặc factory method để tạo instance.
2. **Populate properties:** gán property và thực hiện dependency injection, bao gồm field/setter injection.
3. **Aware callbacks:** gọi các callback như `BeanNameAware`, `BeanClassLoaderAware` và `BeanFactoryAware` khi bean triển khai các interface tương ứng.
4. **Before-initialization post-processors:** chạy các BeanPostProcessor trước init callback.
5. **Initialization callbacks:** gọi `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method theo cơ chế lifecycle đã cấu hình.
6. **After-initialization post-processors:** chạy BeanPostProcessor sau init; các processor có thể trả về proxy thay cho instance ban đầu.

Các chi tiết cụ thể phụ thuộc vào loại bean và cấu hình, nhưng điểm quan trọng là dependency injection và các giá trị cần thiết cho bean được xử lý trước các init callback.

Một expression được dùng để cung cấp giá trị cho field hoặc setter của bean thường được đánh giá trong giai đoạn populate properties. Vì thế, init method có thể đọc giá trị đã inject. Nếu expression gọi một bean khác, bean đó có thể được resolve và tạo trước khi bean hiện tại hoàn tất khởi tạo.

## 3. SpEL trong bean definition

Spring hỗ trợ expression trong giá trị bean definition. Ví dụ XML:

    <bean id="serviceConfig"
          class="com.example.ServiceConfig">
        <property name="timeout"
                  value="#{systemProperties['service.timeout']}" />
    </bean>

Khi container cần tạo bean và gán property, BeanFactory sử dụng BeanExpressionResolver để đánh giá expression. Kết quả được chuyển sang kiểu property nếu cần rồi mới được ghi.

Trong cấu hình Java, có thể dùng SpEL trong các giá trị được resolve bởi container, chẳng hạn thông qua `@Value` hoặc các cơ chế cấu hình tương ứng. Không nên nhầm thời điểm parse expression với thời điểm tạo bean: container có thể parse/cached expression trước, nhưng giá trị vẫn được đánh giá tại lúc cần resolve cho bean.

Nếu expression trong bean definition tham chiếu một bean khác, ví dụ `@pricingPolicy.defaultRate`, resolver cần lấy bean đó từ BeanFactory. Lần resolve này có thể khiến bean được tạo sớm hơn thời điểm nó được khởi tạo trong luồng pre-instantiation thông thường.

## 4. Thời điểm đánh giá @Value

`@Value` có thể chứa property placeholder hoặc SpEL:

    @Value("${app.region}")
    private String region;

    @Value("#{systemProperties['user.timezone']}")
    private String timeZone;

Placeholder `${...}` lấy giá trị từ nguồn cấu hình được Spring đăng ký. SpEL `#{...}` đánh giá một expression. Hai cơ chế có thể được kết hợp trong cùng một cấu hình, nhưng chúng có mục đích khác nhau.

Với field hoặc setter injection, `@Value` được xử lý trong giai đoạn populate properties thông qua BeanPostProcessor chuyên trách. Giá trị được resolve trước khi các init callback của bean chạy.

Với constructor parameter:

    public ReportService(
            @Value("${reports.default-format}") String format) {
        this.format = format;
    }

Spring phải resolve đối số trước khi gọi constructor. Nếu biểu thức constructor parameter tham chiếu bean khác, bean được tham chiếu có thể phải được resolve trước khi instance ReportService được tạo.

Giá trị `@Value` thông thường là giá trị được inject tại thời điểm tạo bean. Nếu property source thay đổi sau đó, field đã inject không tự động được tính lại. Muốn có cấu hình động, cần dùng cơ chế quản lý cấu hình hoặc bean có hành vi cập nhật phù hợp.

## 5. Bean reference có thể kích hoạt tạo bean khác

Trong expression:

    @Value("#{ @pricingPolicy.defaultRate }")
    private BigDecimal defaultRate;

Spring cần resolve bean có tên `pricingPolicy` để đọc property `defaultRate`. Nếu bean đó chưa tồn tại và là bean cần được tạo theo yêu cầu, BeanFactory có thể khởi tạo nó ngay trong lúc đang tạo bean hiện tại.

Điều này có một số hệ quả:

- Bean được tham chiếu có thể được khởi tạo sớm hơn dự kiến.
- Constructor, dependency injection, init callback và BeanPostProcessor của bean được tham chiếu có thể chạy lồng trong quá trình tạo bean hiện tại.
- Nếu bean được tham chiếu phụ thuộc ngược lại bean hiện tại, có thể phát sinh circular dependency.
- Nếu bean có side effect trong constructor hoặc init callback, những side effect đó cũng xảy ra tại thời điểm expression được resolve.

Do đó, nên dùng bean reference trong SpEL cho các giá trị hoặc thao tác tính toán có phạm vi rõ ràng. Tránh gọi method khởi tạo workflow, ghi dữ liệu hoặc thực hiện I/O trong expression dùng để inject một giá trị cấu hình.

## 6. Thể hiện dependency và thứ tự khởi tạo một cách tường minh

Nếu bean A thực sự phụ thuộc bean B, dependency injection là cách thể hiện mối quan hệ rõ ràng nhất:

    @Service
    public class ReportService {

        private final PricingPolicy pricingPolicy;

        public ReportService(PricingPolicy pricingPolicy) {
            this.pricingPolicy = pricingPolicy;
        }
    }

Spring phải resolve PricingPolicy trước khi hoàn tất việc tạo ReportService. Mối quan hệ được thể hiện trực tiếp trong constructor và dễ theo dõi hơn một tham chiếu ẩn bên trong chuỗi SpEL.

Khi cần bảo đảm một bean khác được khởi tạo trước vì một lý do lifecycle cụ thể mà dependency injection không thể hiện, có thể dùng `@DependsOn`:

    @Component
    @DependsOn("databaseInitializer")
    public class ImportService {
        // ...
    }

`@DependsOn` khai báo thứ tự khởi tạo bean được chỉ định trước bean hiện tại. Với singleton, Spring cũng dùng quan hệ này để xác định thứ tự hủy bean phù hợp.

Không nên dùng `@DependsOn` để che giấu một dependency dữ liệu thông thường; hãy inject dependency qua constructor hoặc setter. `@DependsOn` cũng không giải quyết được circular dependency về mặt thiết kế.

Nếu chỉ tình cờ gọi `@beanName` trong một expression, đừng dựa vào thứ tự khởi tạo ngầm đó để biểu đạt một yêu cầu lifecycle quan trọng. Hãy khai báo quan hệ phụ thuộc rõ ràng trong cấu hình.

## 7. Bean lazy và scope ảnh hưởng thế nào?

Bean singleton không lazy thường được tạo trong giai đoạn ApplicationContext hoàn tất refresh. Bean được đánh dấu lazy có thể được tạo khi lần đầu được yêu cầu.

Tuy nhiên, nếu một expression được đánh giá trong lúc khởi tạo bean và tham chiếu trực tiếp tới bean lazy:

    @Value("#{ @largeCatalog.defaultCategory }")
    private String defaultCategory;

thì việc resolve `@largeCatalog` có thể trở thành lần truy cập đầu tiên và kích hoạt tạo bean đó. Đừng giả định rằng đánh dấu bean lazy sẽ trì hoãn việc tạo bean nếu expression đã yêu cầu bean ngay trong startup.

Với prototype, mỗi lần BeanFactory resolve bean có thể tạo instance mới. Với request/session scope, việc resolve phụ thuộc scope tương ứng đang hoạt động. Nếu expression được đánh giá ngoài request đang hoạt động mà lại truy cập request-scoped bean, việc resolve có thể thất bại.

Nếu bean được bọc bằng scoped proxy, expression thường nhận object proxy do container quản lý; lời gọi method qua proxy sẽ được chuyển tới target phù hợp với scope. Không tự unwrap proxy nếu cần giữ các hành vi scope hoặc AOP.

## 8. Circular dependency do expression

Một circular dependency có thể hình thành khi bean A cần bean B trong lúc khởi tạo, còn bean B lại cần bean A:

    @Component
    public class A {
        @Value("#{ @beanB.name }")
        private String name;
    }

    @Component
    public class BeanB {
        private final A a;

        public BeanB(A a) {
            this.a = a;
        }
    }

Trong ví dụ, việc resolve `@beanB` khi inject A có thể kích hoạt tạo B; constructor của B lại yêu cầu A. Với constructor cycle, Spring không thể tạo xong object nào trước để đáp ứng object còn lại và sẽ báo lỗi circular dependency.

Một số circular dependency dựa trên setter/field injection có thể được xử lý bằng cơ chế early singleton reference trong những cấu hình phù hợp, nhưng không nên dựa vào khả năng này. Proxy, BeanPostProcessor và các thay đổi lifecycle cũng có thể làm vòng phụ thuộc khó dự đoán hơn.

Cách xử lý tốt hơn là tách phần logic chung sang bean thứ ba, đảo chiều dependency qua interface hoặc dùng một API gọi tại thời điểm runtime thay vì đọc bean kia trong lúc inject giá trị. Nếu cần trì hoãn truy cập, có thể cân nhắc `ObjectProvider` hoặc một cơ chế lazy rõ ràng trong Java; không nên dùng SpEL để che giấu vòng phụ thuộc.

## 9. BeanPostProcessor và BeanFactoryPostProcessor được tạo rất sớm

BeanFactoryPostProcessor và BeanPostProcessor là thành phần hạ tầng tham gia vào quá trình chuẩn bị BeanFactory hoặc tạo bean. Spring phải tạo chúng sớm để chúng có thể xử lý các bean khác.

Vì `@Value` và `@Autowired` cũng được xử lý bởi BeanPostProcessor, không nên dựa vào các annotation này để inject dependency vào chính một class triển khai BeanPostProcessor hoặc BeanFactoryPostProcessor. Những class hạ tầng đó cần được cấu hình qua constructor hoặc factory method với các dependency phù hợp, hoặc dùng trực tiếp các API Environment/BeanFactory khi đúng mục đích.

Tránh để một BeanFactoryPostProcessor gọi tới các service nghiệp vụ thông thường chỉ để đánh giá expression. Việc đó có thể khởi tạo các bean quá sớm, trước khi toàn bộ BeanPostProcessor cần thiết đã được đăng ký. Bean được tạo sớm có thể không trải qua đầy đủ các post-processing mà bean thông thường nhận được.

Khi khai báo bean hạ tầng bằng `@Bean`, hãy tuân theo yêu cầu về static factory method và thứ tự đăng ký mà Spring quy định cho loại processor đó.

## 10. Expression evaluation ở runtime khác với lúc khởi tạo bean

Không phải mọi SpEL đều chạy trong startup. Ví dụ method security:

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice getInvoice(Long id) {
        return invoiceRepository.findById(id).orElseThrow();
    }

Expression này được Spring Security đánh giá khi lời gọi method đi qua method-security interceptor. Nó không được đánh giá một lần trong lúc bean InvoiceService được khởi tạo.

Tương tự, với SpEL dùng trực tiếp trong Java:

    Expression expression =
            parser.parseExpression("#order.total * 1.1");

    Object value = expression.getValue(context);

thời điểm đánh giá là lúc ứng dụng gọi `getValue(context)`. Một Expression đã parse có thể được tái sử dụng, nhưng mỗi lần `getValue` vẫn thực hiện đánh giá trên context và dữ liệu tại thời điểm gọi.

Phân biệt ba thời điểm thường gặp:

| Nơi dùng expression | Thời điểm đánh giá |
|---|---|
| Bean definition value | Khi container resolve giá trị trong quá trình tạo/configure bean |
| `@Value("#{...}")` | Khi Spring inject giá trị vào constructor, field hoặc setter |
| `@PreAuthorize` | Khi method-security interceptor xử lý lời gọi method |
| SpEL gọi bằng Java | Khi ứng dụng gọi `getValue()` hoặc API đánh giá tương ứng |

## 11. Cẩn trọng với method có tác dụng phụ trong expression khởi tạo

Một expression có thể gọi method trên bean:

    @Value("#{ @startupService.prepareDefaultRegion() }")
    private String region;

Nếu method này chỉ tính một giá trị thuần túy, việc gọi trong lúc khởi tạo có thể phù hợp. Nhưng nếu method ghi database, gửi message, gọi API hoặc thay đổi trạng thái dùng chung, việc inject một field có thể vô tình kích hoạt hành động bên ngoài.

Các rủi ro thường gặp:

- Method có thể chạy trong lúc container đang tạo một chuỗi dependency.
- Một lỗi khởi tạo có thể xảy ra sau khi side effect đã hoàn thành.
- Nếu bean được tạo lại trong context khác hoặc test khác, hành động có thể lặp lại.
- Thứ tự side effect có thể phụ thuộc vào bean nào được resolve trước.
- Circular dependency có thể xuất hiện nếu method gọi lại một bean đang khởi tạo.

Hãy giữ expression trong bean definition và `@Value` đơn giản, chủ yếu đọc property hoặc tính giá trị. Đặt hành động nghiệp vụ vào service method được gọi tại một thời điểm rõ ràng sau khi context đã sẵn sàng.

## 12. Debug lỗi liên quan tới thứ tự khởi tạo

Khi một expression không resolve được bean hoặc property trong startup, hãy xác định điểm xảy ra lỗi:

1. Lỗi xuất hiện khi parse expression hay khi đánh giá expression?
2. Bean chứa expression đã được instantiate chưa?
3. Expression đang được resolve trong constructor injection hay field/setter injection?
4. Bean được tham chiếu có tồn tại, có lazy hoặc scope đặc biệt không?
5. Có dependency ngược tạo thành vòng circular dependency không?
6. BeanPostProcessor cần thiết đã được đăng ký trước khi bean đó được tạo chưa?
7. Method được gọi có phụ thuộc vào trạng thái chỉ sẵn sàng sau init callback không?

Đọc stack trace để xác định bean nào đang được tạo và bean nào được yêu cầu trong quá trình đó. Có thể bật log phù hợp của Spring bean factory để theo dõi quá trình tạo bean, nhưng tránh ghi dữ liệu nhạy cảm hoặc giá trị cấu hình bí mật vào log.

Một test dùng `ApplicationContextRunner` hoặc context test phù hợp có thể giúp tái hiện thứ tự tạo bean và kiểm tra expression ngay trong quá trình refresh. Với method-security expression, hãy kiểm thử riêng lời gọi method sau khi context đã khởi động.

## 13. Ghi nhớ

SpEL được đánh giá tại nơi Spring hoặc ứng dụng cần giá trị của expression. Giá trị trong bean definition và `@Value` thường được resolve trong quá trình tạo bean, trước init callback; tham chiếu `@beanName` có thể kích hoạt tạo bean khác và làm lộ circular dependency hoặc side effect khởi tạo. Method-security expression được đánh giá khi method được gọi, còn SpEL dùng trực tiếp trong Java được đánh giá khi gọi `getValue()`. Hãy thể hiện dependency thật bằng constructor/setter injection, dùng `@DependsOn` cho thứ tự lifecycle đặc biệt, giữ expression khởi tạo đơn giản và tránh phụ thuộc vào bean hạ tầng chưa sẵn sàng.
