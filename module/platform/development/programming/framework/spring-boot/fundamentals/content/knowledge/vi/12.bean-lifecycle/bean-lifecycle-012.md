# Giới hạn của callback bean với tác vụ cần ứng dụng đã khởi động xong

Trong Spring Boot, một bean có thể thực hiện công việc ngay sau khi được tạo thông qua **@PostConstruct**, **InitializingBean.afterPropertiesSet()** hoặc thuộc tính **initMethod** của **@Bean**. Những callback này hữu ích để kiểm tra cấu hình của chính bean, chuẩn bị trạng thái nội bộ và hoàn tất khởi tạo tài nguyên mà bean sở hữu.

Tuy nhiên, **bean đã khởi tạo xong không có nghĩa toàn bộ ứng dụng đã khởi động xong**. Khi một callback của bean chạy, Spring có thể vẫn đang tạo những singleton khác, hoàn tất ApplicationContext, phát các sự kiện startup hoặc chuẩn bị gọi các startup runner. Nếu một tác vụ phụ thuộc vào việc tất cả thành phần đã sẵn sàng, cần chọn đúng mốc trong vòng đời ứng dụng.

Ví dụ, các công việc sau thường không phù hợp để đặt tùy tiện trong @PostConstruct:

- Gọi một service khác với giả định mọi bean trong ứng dụng đã sẵn sàng.
- Quét dữ liệu lớn hoặc làm ấm cache cần nhiều thời gian.
- Chạy một quy trình khởi tạo phụ thuộc vào toàn bộ context.
- Gọi dịch vụ bên ngoài mà có thể chậm hoặc tạm thời chưa khả dụng.
- Phát sinh tác vụ nền và mong rằng ứng dụng chỉ nhận traffic sau khi tác vụ hoàn tất.

Để chọn đúng cơ chế, cần phân biệt **vòng đời của một bean** với **vòng đời khởi động của Spring ApplicationContext và Spring Boot application**.

## 1. Callback bean chỉ nói về vòng đời của bean

Một bean do Spring quản lý có thể đi qua các giai đoạn như:

1. Spring đọc bean definition và xác định cách tạo object.
2. Container tạo instance bằng constructor hoặc factory method.
3. Dependency được inject và các callback Aware phù hợp được gọi.
4. BeanPostProcessor xử lý object trước giai đoạn initialization.
5. Các initialization callback được gọi.
6. BeanPostProcessor tiếp tục xử lý sau initialization; một số cơ chế có thể tạo proxy.
7. Bean được cung cấp cho các thành phần khác theo scope và thời điểm sử dụng.

Ở giai đoạn này, callback đang nói về **một bean cụ thể**. Spring bảo đảm các dependency cần thiết cho quá trình tạo bean đó được resolve theo cơ chế container, nhưng không có nghĩa mọi bean khác trong application đã được khởi tạo.

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class CacheMetadata {

    @PostConstruct
    void initialize() {
        System.out.println("CacheMetadata đã được khởi tạo");
    }
}
~~~

Thông báo này chỉ xác nhận callback của CacheMetadata đã chạy. Nó không xác nhận:

- Tất cả singleton bean khác đã được tạo.
- Các startup runner đã hoàn thành.
- Các tác vụ khởi động của những bean khác đã kết thúc.
- Ứng dụng đã chuyển sang trạng thái sẵn sàng nhận traffic.

Đây là giới hạn quan trọng nhất cần nhớ khi chọn callback.

## 2. Các initialization callback phổ biến

Spring hỗ trợ nhiều cách khai báo hành động khởi tạo bean. Chúng có thể phục vụ cùng một mục đích nhưng khác cách gắn với class và container.

### 2.1. @PostConstruct

Với Spring Boot 3.x, import annotation từ Jakarta:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexMetadata {

    @PostConstruct
    void initialize() {
        // Chuẩn bị trạng thái nội bộ của bean.
    }
}
~~~

@PostConstruct được gọi sau khi dependency injection cho bean hoàn tất và trước khi bean được đưa qua các bước post-processing sau initialization. Đây là nơi phù hợp cho công việc khởi tạo cục bộ, nhanh và không cần toàn bộ ứng dụng đã sẵn sàng.

Trong các dòng Spring Boot cũ dựa trên Spring Framework 5, code có thể dùng package **javax.annotation.PostConstruct**. Từ Spring Framework 6 và Spring Boot 3, annotation tương ứng thuộc **jakarta.annotation**.

### 2.2. InitializingBean.afterPropertiesSet()

Bean có thể implement giao diện:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class ReportSettings implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Kiểm tra trạng thái sau khi dependency đã được thiết lập.
    }
}
~~~

Spring gọi **afterPropertiesSet()** trong giai đoạn initialization sau khi các property/dependency được thiết lập. Cơ chế này gắn class trực tiếp với Spring API, vì vậy thường ít được ưu tiên hơn callback annotation hoặc init method nếu muốn giữ class nghiệp vụ độc lập framework.

### 2.3. initMethod trong @Bean

Với một class bên thứ ba hoặc class không muốn gắn annotation Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "initialize")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Spring gọi method được chỉ định sau khi tạo và cấu hình bean theo vòng đời initialization. Cách này hữu ích khi bạn không thể sửa source của ExternalClient.

### 2.4. Thứ tự callback khởi tạo

Trong một luồng tạo bean điển hình, các bước thường có thứ tự khái niệm:

~~~text
Tạo instance
     │
     ▼
Dependency injection
     │
     ▼
Aware callbacks (nếu có)
     │
     ▼
BeanPostProcessor trước initialization
     │
     ▼
@PostConstruct
     │
     ▼
InitializingBean.afterPropertiesSet()
     │
     ▼
Custom initMethod
     │
     ▼
BeanPostProcessor sau initialization
     │
     ▼
Bean được cung cấp cho consumer
~~~

Thứ tự chi tiết chịu ảnh hưởng của cơ chế container và các processor đã đăng ký; sơ đồ trên mô tả đường đi phổ biến của một bean do Spring quản lý. Không nên dùng việc đặt nhiều callback khác nhau để tạo một quy trình khởi động toàn ứng dụng phức tạp.

## 3. Callback hủy bean cũng có phạm vi riêng

Spring hỗ trợ các cơ chế như:

- **@PreDestroy**.
- **DisposableBean.destroy()**.
- **destroyMethod** trên @Bean.

Ví dụ:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ConnectionManager {

    @PreDestroy
    void shutdown() {
        // Đóng tài nguyên do bean sở hữu.
    }
}
~~~

Đây là callback dọn dẹp khi bean được container hủy theo lifecycle phù hợp, thường là khi ApplicationContext đóng bình thường đối với singleton bean.

Callback hủy bean không phải nơi để khởi chạy công việc sau khi ứng dụng đã dừng. Khi @PreDestroy chạy, các thành phần phụ thuộc có thể đang đi vào giai đoạn shutdown; việc gọi những service khác có thể không còn an toàn.

Ngoài ra:

- JVM bị kill đột ngột, mất điện hoặc process crash không bảo đảm callback hủy sẽ chạy.
- Với prototype scope, container tạo và khởi tạo instance nhưng không tự quản lý đầy đủ destruction callback cho mọi prototype instance sau khi giao chúng cho caller.
- Nếu bean sở hữu thread pool, socket hoặc client, cần xác định rõ ai sở hữu và ai đóng tài nguyên.

## 4. Vì sao @PostConstruct chưa phải mốc ứng dụng sẵn sàng?

Spring tạo bean theo đồ thị dependency. Khi tạo một bean, container phải tạo hoặc resolve những dependency mà bean cần. Nhưng các bean không nằm trên nhánh dependency đó có thể chưa được tạo.

Ví dụ:

~~~text
ApplicationContext đang refresh
          │
          ├── tạo OrderService
          │      └── tạo OrderRepository
          │             └── @PostConstruct của repository
          │
          ├── chưa tạo SearchService
          │
          ├── chưa tạo NotificationService
          │
          └── chưa hoàn tất toàn bộ singleton
~~~

Nếu callback của OrderRepository gọi SearchService bằng cách tra cứu context, nó có thể vô tình buộc container tạo thêm bean trong lúc refresh. Nếu bean đó lại phụ thuộc ngược vào nhánh đang khởi tạo, ứng dụng có thể gặp vấn đề về thứ tự, circular dependency hoặc trạng thái chưa sẵn sàng.

Một callback của bean chỉ nên dựa vào những dependency mà bean đã được inject và các hợp đồng lifecycle đã được xác định. Không nên suy ra rằng toàn bộ hệ thống đã hoàn tất chỉ vì một callback đã chạy.

### 4.1. Dependency đã được inject không có nghĩa mọi dịch vụ đã sẵn sàng về nghiệp vụ

Giả sử:

~~~java
@Component
public class ProductCache {
    private final ProductRepository repository;

    public ProductCache(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void load() {
        // Đọc dữ liệu và đưa vào cache.
    }
}
~~~

ProductRepository đã được inject khi ProductCache chạy @PostConstruct. Nhưng điều đó không bảo đảm:

- Database đã có đầy đủ dữ liệu nền.
- Các migration hoặc import dữ liệu khác đã hoàn tất.
- Một service đồng bộ dữ liệu đã chạy xong.
- Các bean khác đã sẵn sàng cho quy trình cache.
- Việc đọc dữ liệu không làm kéo dài hoặc thất bại startup.

Nếu cache cần một quy trình khởi động sau khi context refresh, hãy chuyển phần điều phối sang một mốc startup thích hợp và giữ callback bean tập trung vào khởi tạo nội bộ.

### 4.2. Bean callback có thể chạy trước khi proxy hoàn tất

Các proxy AOP như transaction, cache hoặc custom aspect thường được tạo trong quá trình post-processing sau initialization. Vì vậy, gọi một method được kỳ vọng có @Transactional ngay bên trong @PostConstruct của chính bean có thể không đi qua proxy transaction như mong muốn.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Service
public class ImportService {

    @PostConstruct
    void initialize() {
        importInitialData();
    }

    @Transactional
    public void importInitialData() {
        // Ghi dữ liệu.
    }
}
~~~

Lời gọi importInitialData() ở trên là lời gọi nội bộ trên instance đang khởi tạo, không đi qua proxy của bean. Hơn nữa, callback chạy trước giai đoạn post-processing cuối cùng có thể tạo proxy. Vì vậy không nên dựa vào @Transactional được áp dụng cho lời gọi đó.

Nếu tác vụ cần transaction, hãy gọi một service transaction riêng từ một startup runner hoặc listener sau khi context đã refresh và bean proxy đã sẵn sàng:

~~~java
@Service
public class InitialImportService {
    @Transactional
    public void importInitialData() {
        // Thực hiện import trong transaction.
    }
}
~~~

~~~java
@Component
public class StartupImportRunner implements ApplicationRunner {
    private final InitialImportService importService;

    public StartupImportRunner(InitialImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importInitialData();
    }
}
~~~

Đây là ví dụ minh họa cho một tác vụ cần chạy sau khi context đã refresh. Hạ tầng transaction, datasource và chính sách rollback vẫn phải được cấu hình đúng.

## 5. Các mốc quan trọng trong quá trình khởi động Spring Boot

Để chọn đúng callback, hãy nhìn rộng hơn vòng đời của một bean. Spring Boot có các mốc sự kiện riêng trong quá trình chạy ứng dụng.

Một trình tự khái niệm:

~~~text
SpringApplication.run(...)
          │
          ▼
Chuẩn bị Environment và ApplicationContext
          │
          ▼
Đăng ký bean definitions / xử lý cấu hình
          │
          ▼
ApplicationContext.refresh()
          │
          ├── Tạo các singleton eager
          │      └── Callback bean: @PostConstruct,
          │          afterPropertiesSet, initMethod
          │
          ├── SmartInitializingSingleton
          │
          └── ContextRefreshedEvent
          │
          ▼
ApplicationStartedEvent
          │
          ▼
ApplicationRunner / CommandLineRunner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
ReadinessState.ACCEPTING_TRAFFIC
          │
          ▼
SpringApplication.run(...) hoàn tất
~~~

Sơ đồ mô tả các mốc startup tiêu biểu của một Spring Boot application. Một số sự kiện chuẩn bị khác có thể xuất hiện trước refresh; các chi tiết nội bộ phụ thuộc phiên bản và loại ứng dụng. Điều cần nắm là **callback bean nằm trong quá trình tạo bean, còn runner và ApplicationReadyEvent thuộc giai đoạn khởi động ứng dụng rộng hơn**.

### 5.1. ContextRefreshedEvent

Spring phát **ContextRefreshedEvent** khi ApplicationContext được khởi tạo hoặc refresh. Đây là mốc cho biết quá trình refresh của context đã hoàn tất theo cơ chế Spring.

Ví dụ:

~~~java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // Context đã refresh.
    }
}
~~~

Mốc này rộng hơn @PostConstruct của một bean, nhưng vẫn chưa phải mốc ứng dụng Spring Boot đã chạy xong startup runner.

Các giới hạn cần nhớ:

- Context có thể được refresh nhiều lần trong một số cấu trúc hoặc trường hợp đặc biệt.
- Ứng dụng có thể có parent và child context; event được phát trong một context cụ thể và có thể được truyền theo cơ chế event hierarchy.
- Spring Boot còn các giai đoạn runner và application-ready sau khi context refresh.

Vì vậy, nếu tác vụ cần chạy sau khi **toàn bộ startup runner hoàn tất**, ContextRefreshedEvent chưa phải lựa chọn chính xác.

### 5.2. SmartInitializingSingleton

**SmartInitializingSingleton.afterSingletonsInstantiated()** được gọi sau khi BeanFactory hoàn tất việc khởi tạo các singleton eager thông thường trong quá trình pre-instantiation.

Ví dụ:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class SingletonRegistryCheck
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Các singleton eager thông thường đã được pre-instantiate.
    }
}
~~~

Callback này hữu ích cho một số hạ tầng cần quan sát các singleton đã được tạo. Nhưng nó vẫn chạy trong quá trình refresh context, trước ContextRefreshedEvent và trước các runner của Spring Boot.

Nó cũng không có nghĩa mọi bean lazy, prototype hoặc mọi tác vụ startup đã hoàn thành. Không dùng nó thay cho ApplicationReadyEvent nếu yêu cầu thật sự là ứng dụng đã qua các runner.

### 5.3. ApplicationStartedEvent

Spring Boot phát **ApplicationStartedEvent** sau khi ApplicationContext đã refresh và trước khi ApplicationRunner/CommandLineRunner được gọi.

Do đó, nếu listener xử lý tại ApplicationStartedEvent, context đã refresh nhưng các runner vẫn chưa chạy xong. Đây không phải mốc phù hợp cho công việc phụ thuộc kết quả do runner chuẩn bị.

### 5.4. ApplicationReadyEvent

Spring Boot phát **ApplicationReadyEvent** sau khi các ApplicationRunner và CommandLineRunner hoàn tất. Đây là mốc phù hợp khi tác vụ cần biết phần startup thông thường đã đi qua và ứng dụng sắp được xem là sẵn sàng nhận traffic.

Ví dụ:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application đã đến mốc ready");
    }
}
~~~

Trong trình tự mặc định của Spring Boot, trạng thái availability **ACCEPTING_TRAFFIC** được công bố sau ApplicationReadyEvent. Vì event listener thông thường được gọi đồng bộ, công việc chạy trong listener có thể hoàn tất trước khi quá trình phát event ready kết thúc và trạng thái nhận traffic được công bố.

Nếu event multicaster hoặc listener được cấu hình bất đồng bộ, thứ tự hoàn tất công việc có thể khác. Không nên mặc định mọi listener đều chặn readiness khi hệ thống đã thay đổi cơ chế dispatch event.

## 6. Dùng ApplicationRunner hoặc CommandLineRunner cho tác vụ startup

Nếu công việc phải chạy **sau khi context đã refresh nhưng trước khi ứng dụng báo ready**, hai giao diện thường phù hợp là:

- **ApplicationRunner**: nhận đối tượng ApplicationArguments đã phân tích tham số dòng lệnh.
- **CommandLineRunner**: nhận trực tiếp mảng String chứa các tham số dòng lệnh.

Spring Boot gọi các runner sau khi context refresh và trước ApplicationReadyEvent.

### 6.1. Ví dụ ApplicationRunner

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class ReferenceDataLoader implements ApplicationRunner {
    private final ReferenceDataService dataService;

    public ReferenceDataLoader(ReferenceDataService dataService) {
        this.dataService = dataService;
    }

    @Override
    public void run(ApplicationArguments args) {
        dataService.loadRequiredReferenceData();
    }
}
~~~

Trong ví dụ này, ReferenceDataService được inject như một bean bình thường. Khi run() được gọi, ApplicationContext đã refresh; bean và các proxy được tạo trong quá trình refresh đã sẵn sàng theo cơ chế container.

Nếu việc nạp reference data là bắt buộc để ứng dụng phục vụ request đúng, thực hiện đồng bộ trong runner giúp startup chỉ đi tiếp tới ApplicationReadyEvent sau khi tác vụ kết thúc.

### 6.2. Ví dụ CommandLineRunner

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupArgumentLogger implements CommandLineRunner {

    @Override
    public void run(String... args) {
        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
~~~

CommandLineRunner phù hợp khi chỉ cần chuỗi tham số thô. ApplicationRunner tiện hơn nếu cần truy vấn option đã được Spring Boot phân tích.

### 6.3. Thứ tự giữa nhiều runner

Nếu có nhiều ApplicationRunner hoặc CommandLineRunner, có thể sắp xếp bằng:

- **@Order**.
- Interface **Ordered**.

Ví dụ:

~~~java
@Component
@Order(1)
public class DatabasePreparationRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Bước chuẩn bị đầu tiên.
    }
}
~~~

~~~java
@Component
@Order(2)
public class CacheWarmupRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Bước chuẩn bị tiếp theo.
    }
}
~~~

Giá trị order nhỏ hơn được ưu tiên trước trong thứ tự sắp xếp thông thường. Nếu một tác vụ phụ thuộc kết quả tác vụ khác, có thể dùng cùng một runner điều phối rõ ràng hoặc sắp xếp runner theo hợp đồng cụ thể.

Không nên dựa vào thứ tự tình cờ của component scan để quyết định trình tự runner.

### 6.4. Nếu runner ném exception thì sao?

Runner chạy trong quá trình startup. Nếu một runner ném exception không được xử lý, quá trình khởi động thường thất bại và ApplicationReadyEvent không được phát theo luồng thành công thông thường.

Điều này phù hợp với tác vụ **bắt buộc**: nếu thiếu dữ liệu nền hoặc không thể hoàn thành một điều kiện thiết yếu, ứng dụng không nên giả vờ đã sẵn sàng.

Với tác vụ tùy chọn, cần quyết định rõ:

- Có thể bỏ qua và ghi nhận trạng thái degraded?
- Có thể retry trong một khoảng thời gian?
- Ứng dụng có được phép nhận traffic khi tác vụ chưa hoàn tất?
- Nếu lỗi xảy ra, ai chịu trách nhiệm cảnh báo và phục hồi?

Đừng bắt rộng exception rồi chỉ log để runner luôn kết thúc thành công nếu điều đó khiến ứng dụng phục vụ request với dữ liệu không hợp lệ.

## 7. Khi nào dùng ApplicationReadyEvent?

**ApplicationReadyEvent** phù hợp với tác vụ cần đợi các runner hoàn tất. Ví dụ:

- Gửi một tín hiệu nội bộ rằng application đã đi qua giai đoạn startup.
- Bắt đầu một công việc chỉ có ý nghĩa sau khi cấu hình và runner đã xong.
- Kích hoạt một bước warm-up cuối cùng trước khi availability chuyển sang trạng thái nhận traffic.
- Ghi nhận thời điểm ứng dụng đến mốc ready.

Ví dụ:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class FinalWarmupListener {
    private final SearchWarmupService warmupService;

    public FinalWarmupListener(SearchWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        warmupService.warmUp();
    }
}
~~~

Với event listener đồng bộ theo cấu hình mặc định, lời gọi warmUp() kết thúc trước khi listener hoàn tất. Spring Boot sau đó mới tiếp tục công bố readiness ACCEPTING_TRAFFIC theo trình tự startup thông thường.

Nếu warmUp() kéo dài nhiều phút, listener đồng bộ cũng kéo dài giai đoạn ứng dụng chưa được đánh dấu accepting traffic. Điều này có thể là chủ ý nếu warm-up là điều kiện bắt buộc, nhưng không phù hợp nếu công việc có thể chạy nền sau khi app đã phục vụ request.

### 7.1. ApplicationReadyEvent không có nghĩa mọi hệ thống ngoài đều khỏe mạnh

Event này chỉ phản ánh ứng dụng đã đi qua các bước startup do Spring Boot điều phối. Nó không bảo đảm:

- Database hoặc dịch vụ bên ngoài sẽ luôn hoạt động sau đó.
- Mọi message consumer đã nhận được message.
- Mọi tác vụ nền dài hạn đã hoàn tất.
- Các endpoint bên ngoài đều có thể truy cập từ mọi network.
- Nghiệp vụ thực tế không còn lỗi.

Nếu yêu cầu readiness phụ thuộc một dịch vụ ngoài, cần có health/readiness check phù hợp và chính sách xử lý khi dịch vụ đó mất kết nối sau startup.

## 8. Chọn callback theo thời điểm cần thiết

Bảng dưới đây giúp phân biệt các cơ chế:

| Cơ chế | Mốc chạy | Phù hợp với |
|---|---|---|
| Constructor | Khi tạo instance | Thiết lập trạng thái bắt buộc từ tham số; không gọi dịch vụ ngoài. |
| **@PostConstruct** | Sau injection của bean, trong initialization | Kiểm tra/chuẩn bị nội bộ bean, công việc ngắn. |
| **afterPropertiesSet()** | Giai đoạn initialization của bean | Callback khởi tạo gắn với Spring InitializingBean. |
| **@Bean(initMethod=...)** | Giai đoạn initialization của bean | Khởi tạo object bên thứ ba hoặc object cấu hình qua factory method. |
| **SmartInitializingSingleton** | Sau pre-instantiation của singleton eager, trong refresh | Tác vụ hạ tầng cần biết các singleton thông thường đã được tạo. |
| **ContextRefreshedEvent** | Sau khi context refresh | Logic phụ thuộc context đã refresh, nếu chấp nhận giới hạn của event context. |
| **ApplicationStartedEvent** | Sau refresh, trước runner | Phản ứng với mốc app started nhưng runner chưa hoàn tất. |
| **ApplicationRunner / CommandLineRunner** | Sau refresh, trước ApplicationReadyEvent | Tác vụ startup cần chạy xong trước mốc ready. |
| **ApplicationReadyEvent** | Sau khi runner hoàn tất | Tác vụ cần đợi giai đoạn startup thông thường hoàn thành. |
| **@PreDestroy / destroyMethod** | Khi bean được hủy theo lifecycle | Giải phóng tài nguyên do bean sở hữu. |

Không có callback “tốt nhất” cho mọi tác vụ. Hãy xác định điều kiện tiên quyết của công việc rồi chọn mốc đầu tiên bảo đảm các điều kiện đó đã được đáp ứng.

## 9. Ví dụ: tác vụ cần chạy sau khi tất cả bean đã sẵn sàng

Giả sử ứng dụng cần đọc một danh mục cấu hình từ database và làm ấm cache trước khi nhận request.

Không nên mặc định đặt toàn bộ quy trình trong @PostConstruct của cache:

~~~java
@Component
public class ProductCache {
    private final ProductRepository repository;

    public ProductCache(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        // Có thể chạy quá sớm đối với quy trình startup tổng thể.
        repository.findAll();
    }
}
~~~

Thay vào đó, giữ cache là một bean có API rõ ràng:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ProductCache {
    private volatile java.util.Map<Long, Product> products =
            java.util.Map.of();

    public void replaceAll(java.util.Map<Long, Product> values) {
        this.products = java.util.Map.copyOf(values);
    }

    public Product find(long id) {
        return products.get(id);
    }
}
~~~

Service chịu trách nhiệm tải dữ liệu và chuẩn bị cache:

~~~java
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWarmupService {
    private final ProductRepository repository;
    private final ProductCache cache;

    public ProductCacheWarmupService(
            ProductRepository repository,
            ProductCache cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public void warmUp() {
        Map<Long, Product> values = repository.findAll().stream()
                .collect(Collectors.toMap(Product::getId, product -> product));
        cache.replaceAll(values);
    }
}
~~~

Runner điều phối:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheWarmupRunner implements ApplicationRunner {
    private final ProductCacheWarmupService warmupService;

    public ProductCacheWarmupRunner(
            ProductCacheWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.warmUp();
    }
}
~~~

Với cách này:

1. Spring tạo các bean và hoàn tất dependency injection.
2. ApplicationContext refresh.
3. Runner tải dữ liệu và cập nhật cache.
4. Nếu warm-up thành công, Spring Boot tiếp tục đến ApplicationReadyEvent.
5. Ứng dụng mới chuyển sang mốc readiness accepting traffic theo luồng mặc định.

Nếu warm-up thất bại và exception được để lan ra ngoài runner, startup không báo thành công. Điều này thích hợp khi cache là điều kiện bắt buộc để phục vụ request.

## 10. Công việc đồng bộ và bất đồng bộ có ý nghĩa khác nhau

Một tác vụ startup có thể thuộc một trong hai loại:

**Bắt buộc hoàn thành trước khi nhận traffic**

- Dữ liệu nền phải có để xử lý request đúng.
- Một cấu hình cần kiểm tra và fail-fast.
- Một bước khởi tạo thiết yếu mà thiếu nó ứng dụng không thể hoạt động.

Với loại này, thực hiện đồng bộ trong ApplicationRunner/CommandLineRunner hoặc listener đồng bộ ở mốc phù hợp. Thời gian thực hiện sẽ nằm trong startup time.

**Có thể tiếp tục chạy sau khi ứng dụng đã nhận traffic**

- Làm ấm một cache tùy chọn mà request vẫn có fallback.
- Tải dữ liệu thống kê không bắt buộc.
- Gửi một báo cáo startup.
- Bắt đầu một tác vụ đồng bộ định kỳ có cơ chế quan sát và retry.

Với loại này, có thể chuyển việc xử lý sang executor/background worker. Nhưng phải xác định rõ trạng thái của tính năng trong thời gian tác vụ chưa xong.

### 10.1. @Async không tự làm ứng dụng chờ công việc hoàn tất

Spring hỗ trợ @Async khi asynchronous method execution đã được bật bằng cấu hình phù hợp, thường là **@EnableAsync**.

Ví dụ:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BackgroundWarmupService {

    @Async
    public CompletableFuture<Void> warmUp() {
        // Công việc có thể chạy trên executor.
        performWarmup();
        return CompletableFuture.completedFuture(null);
    }

    private void performWarmup() {
        // Tải dữ liệu hoặc làm ấm cache.
    }
}
~~~

Cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Nếu gọi phương thức @Async qua bean proxy, lời gọi được chuyển tới executor theo cấu hình. Nhưng caller có thể tiếp tục trước khi công việc hoàn tất.

### 10.2. Gọi @Async từ chính bean không đi qua proxy

Ví dụ:

~~~java
@Component
public class WarmupComponent {

    public void start() {
        warmAsync();
    }

    @Async
    public void warmAsync() {
        // ...
    }
}
~~~

Trong proxy mode thông dụng, lời gọi nội bộ từ start() tới warmAsync() không đi qua proxy, nên @Async có thể không được áp dụng. Đây là self-invocation, tương tự giới hạn của nhiều cơ chế Spring AOP khác.

Một thiết kế dễ hiểu hơn là tách tác vụ async sang một bean riêng rồi gọi bean đó từ runner hoặc listener.

### 10.3. ApplicationReadyEvent kết hợp tác vụ nền

Ví dụ listener:

~~~java
@Component
public class BackgroundWarmupListener {
    private final BackgroundWarmupService warmupService;

    public BackgroundWarmupListener(
            BackgroundWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        warmupService.warmUp();
    }
}
~~~

Listener gọi service async qua một bean khác. Listener có thể kết thúc ngay sau khi submit công việc; ứng dụng tiếp tục hoàn tất quá trình phát ApplicationReadyEvent và công bố readiness.

Điều đó có nghĩa **ApplicationReadyEvent không chờ tác vụ async hoàn thành**. Nếu request cần dữ liệu mà warm-up đang tạo, cần có fallback hoặc readiness gate riêng. Không nên giả định chỉ vì công việc bắt đầu từ ApplicationReadyEvent nên mọi request sẽ đợi nó.

### 10.4. Quản lý lỗi của tác vụ nền

Khi tác vụ chạy async:

- Xác định nơi nhận kết quả hoặc exception.
- Ghi log có ngữ cảnh, không nuốt lỗi.
- Có retry policy với giới hạn và backoff nếu nghiệp vụ cho phép.
- Cung cấp trạng thái tiến độ/hoàn tất để quan sát.
- Đặt timeout và giới hạn tài nguyên executor.
- Có chiến lược shutdown để không bỏ dở tài nguyên quan trọng.

Nếu method trả về CompletableFuture, caller có thể gắn callback hoặc lưu Future để theo dõi kết quả. Nếu dùng method void, exception không thể được caller nhận trực tiếp qua return value; cần cơ chế xử lý lỗi async phù hợp.

## 11. Readiness khác với liveness

Spring Boot Actuator có khái niệm **availability** để diễn đạt ứng dụng có thể nhận traffic hay không và process còn hoạt động hay không.

- **Liveness:** process/application có đang ở trạng thái có thể tiếp tục chạy hay nên được khởi động lại?
- **Readiness:** ứng dụng có sẵn sàng nhận request/traffic ở thời điểm này không?

Một ứng dụng có thể đang sống nhưng chưa sẵn sàng:

~~~text
Process đang chạy
      │
      ▼
Liveness = UP
      │
      ▼
Đang tải dữ liệu bắt buộc
      │
      ▼
Readiness = REFUSING_TRAFFIC
      │
      ▼
Hoàn tất khởi tạo bắt buộc
      │
      ▼
Readiness = ACCEPTING_TRAFFIC
~~~

Trong Spring Boot, readiness state có thể được quan sát qua Actuator health group khi đã cấu hình phù hợp. Nền tảng triển khai như Kubernetes có thể dùng readiness probe để quyết định có gửi traffic đến instance hay không.

### 11.1. Runner đồng bộ giúp readiness chờ startup task

Trong luồng startup mặc định, Boot gọi runners trước ApplicationReadyEvent và sau đó mới công bố readiness accepting traffic. Vì vậy, nếu một runner chạy đồng bộ và chỉ trả về sau khi công việc bắt buộc hoàn tất, ứng dụng chưa đi tới mốc ready trong lúc công việc còn chạy.

Đây là cách đơn giản cho tác vụ khởi động cần hoàn tất trước traffic. Đổi lại, thời gian startup tăng lên và nếu tác vụ treo, ứng dụng có thể không bao giờ báo ready.

### 11.2. Tác vụ nền sau ready cần readiness gate riêng nếu vẫn phải chặn traffic

Nếu tác vụ được chạy bất đồng bộ sau ApplicationReadyEvent nhưng request chưa được phép sử dụng tính năng đó, chỉ dùng @Async là không đủ để chặn traffic. Cần một cơ chế readiness/health được thiết kế để phản ánh trạng thái thật của tác vụ.

Một cách là tạo một **HealthIndicator** hoặc health contributor thuộc readiness group, chỉ báo UP khi warm-up bắt buộc đã hoàn tất. Nền tảng triển khai sẽ tiếp tục coi instance chưa sẵn sàng trong khi contributor đó chưa UP.

Ví dụ minh họa một trạng thái riêng:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean complete = new AtomicBoolean(false);

    public boolean isComplete() {
        return complete.get();
    }

    public void markComplete() {
        complete.set(true);
    }
}
~~~

Health contributor có thể đọc state này:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {
    private final WarmupState state;

    public WarmupHealthIndicator(WarmupState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isComplete()) {
            return Health.up().build();
        }
        return Health.outOfService()
                .withDetail("warmup", "in progress")
                .build();
    }
}
~~~

Sau đó cấu hình readiness group bao gồm contributor này theo quy ước Actuator của phiên bản Boot đang dùng. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,warmup
~~~

Đây là phần minh họa về thiết kế health gate; cần kiểm tra endpoint health, group và cơ chế probe thực tế của môi trường. Contributor chỉ có tác dụng nếu readiness probe thực sự đọc readiness group tương ứng.

### 11.3. Đừng đưa mọi dependency ngoài vào liveness

Nếu database tạm thời mất kết nối, điều đó thường không có nghĩa process phải bị khởi động lại ngay. Đưa dependency bên ngoài vào liveness một cách thiếu cân nhắc có thể khiến nền tảng restart hàng loạt instance trong lúc dịch vụ phụ trợ đang gặp sự cố.

Readiness thường phù hợp hơn để tạm ngừng nhận traffic khi một dependency bắt buộc không sẵn sàng. Liveness nên phản ánh khả năng process tiếp tục hoạt động, tránh tạo vòng lặp restart vô ích.

## 12. Vì sao không nên đặt tác vụ nặng trong @PostConstruct?

### 12.1. Làm chậm quá trình tạo context

Nếu một bean mất 90 giây để tải dữ liệu trong @PostConstruct, việc tạo bean và refresh context phải chờ callback đó. Các bean phía sau chưa được khởi tạo, và ứng dụng chưa tới những mốc startup tiếp theo.

Khi có nhiều bean làm công việc nặng trong callback, startup time tăng theo thứ tự và các dependency có thể tạo ra chuỗi chờ khó dự đoán.

### 12.2. Gọi dịch vụ ngoài có thể làm startup không ổn định

Một HTTP API, database hoặc message broker có thể:

- Chưa mở cổng khi ứng dụng bắt đầu.
- Chậm do mạng.
- Trả lỗi tạm thời.
- Đòi hỏi retry.
- Giới hạn kết nối.

Nếu gọi ngay trong callback mà không có timeout và retry policy phù hợp, ứng dụng có thể startup thất bại hoặc treo lâu. Tác vụ cần retry/timeout thường phù hợp hơn với một service điều phối startup rõ ràng.

### 12.3. Tạo vòng phụ thuộc hoặc gọi bean khi context chưa hoàn tất

Callback có thể gọi ApplicationContext.getBean() để lấy một bean khác. Điều này tạo dependency ẩn, khiến thứ tự tạo bean khó đọc và có thể kích hoạt khởi tạo sớm. Nếu có chu trình, context có thể thất bại vì circular dependency hoặc bean chưa sẵn sàng.

Hãy ưu tiên khai báo dependency qua constructor. Nếu công việc cần toàn bộ context, chọn một lifecycle hook sau refresh thay vì tra cứu bean tùy ý từ @PostConstruct.

### 12.4. Gọi transaction hoặc AOP không đúng thời điểm

Trong initialization callback, proxy của bean hiện tại có thể chưa hoàn tất và lời gọi nội bộ không đi qua proxy. Điều này làm các annotation như @Transactional hoặc @Async không hoạt động như dự định.

Tách công việc sang một bean khác và gọi nó ở runner/event phù hợp thường rõ ràng hơn.

### 12.5. Khó phân biệt lỗi cấu hình với lỗi tác vụ nghiệp vụ

Nếu @PostConstruct thực hiện đồng thời việc kiểm tra property, gọi API ngoài, import dữ liệu và làm ấm cache, startup log có thể chỉ cho thấy bean creation failed. Việc tìm nguyên nhân và quyết định có nên fail startup trở nên khó hơn.

Chia nhỏ trách nhiệm:

- Callback bean: xác nhận cấu hình và trạng thái nội bộ.
- Startup service: điều phối một tác vụ có ý nghĩa toàn ứng dụng.
- Runner/event listener: chọn đúng mốc chạy.
- Health/readiness: biểu diễn ứng dụng đã sẵn sàng tới mức nào.

## 13. Thiết kế tác vụ startup theo mức độ bắt buộc

Trước khi chọn hook, hãy phân loại công việc:

| Loại tác vụ | Ví dụ | Cách tổ chức thường phù hợp |
|---|---|---|
| Khởi tạo nội bộ, nhanh | Tạo immutable lookup table từ property đã bind | Constructor hoặc @PostConstruct. |
| Kiểm tra invariant của một bean | Xác nhận tham số bắt buộc, cấu hình local | @PostConstruct hoặc initMethod; fail-fast nếu bean không hợp lệ. |
| Kiểm tra sau khi singleton eager được tạo | Xác nhận registry nội bộ đã thu thập các bean | SmartInitializingSingleton. |
| Tác vụ cần context refresh xong | Một bước tích hợp cần bean graph đã hoàn chỉnh | ContextRefreshedEvent, nếu không cần đợi runner. |
| Tác vụ bắt buộc trước khi báo ready | Nạp reference data, warm-up cache bắt buộc | ApplicationRunner/CommandLineRunner đồng bộ. |
| Tác vụ cần đợi runner khác | Gửi tín hiệu hoặc bước cuối sau startup runner | ApplicationReadyEvent. |
| Tác vụ dài có thể chạy nền | Đồng bộ dữ liệu không ảnh hưởng request hiện tại | Executor/@Async, kèm trạng thái và xử lý lỗi. |
| Tác vụ phải xong trước traffic nhưng chạy bất đồng bộ | Warm-up lớn có thể tiếp tục sau startup process | Readiness gate/health contributor được thiết kế rõ. |
| Giải phóng tài nguyên của bean | Đóng client, executor, connection wrapper | @PreDestroy, destroyMethod hoặc lifecycle phù hợp. |

Một tác vụ có thể thuộc nhiều nhóm theo yêu cầu nghiệp vụ. Ví dụ cache có thể là bắt buộc đối với một endpoint nhưng tùy chọn đối với endpoint khác; khi đó cần thiết kế readiness và fallback theo tính năng, không chỉ theo tên “cache warm-up”.

## 14. Tránh chạy lặp tác vụ không mong muốn

Startup callback không phải lúc nào cũng tương ứng một lần duy nhất trong toàn bộ vòng đời JVM.

Các tình huống cần lưu ý:

- Một ứng dụng test có thể tạo nhiều ApplicationContext trong cùng JVM.
- Context có thể được refresh lại trong cấu trúc đặc biệt.
- Nhiều instance của ứng dụng chạy song song trong deployment.
- Một runner có thể chạy lại nếu ứng dụng được khởi động lại.
- Một message hoặc external trigger có thể lặp lại cùng một yêu cầu khởi tạo.

Nếu tác vụ có side effect như ghi dữ liệu, tạo tài khoản mặc định hoặc gửi thông báo, cần thiết kế **idempotency** và transaction phù hợp. Không nên chỉ dựa vào một static boolean trong JVM để bảo đảm tác vụ toàn hệ thống chỉ chạy một lần.

Ví dụ:

~~~java
@Component
public class InitialCatalogRunner implements ApplicationRunner {
    private final CatalogInitializationService service;

    public InitialCatalogRunner(CatalogInitializationService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.initializeIfRequired();
    }
}
~~~

Tên initializeIfRequired gợi ý một hợp đồng idempotent: service phải kiểm tra trạng thái bền vững hoặc dùng unique constraint/lock thích hợp trước khi ghi dữ liệu. Chi tiết triển khai phụ thuộc database và nghiệp vụ.

### 14.1. Nhiều replica cùng chạy runner

Nếu triển khai 5 replica của một service, mỗi replica đều có thể chạy ApplicationRunner. Vì vậy, runner không tự động là cơ chế leader election hoặc distributed lock.

Nếu tác vụ phải chạy đúng một lần cho toàn hệ thống, hãy dùng một cơ chế phân tán phù hợp như:

- Job/migration chạy riêng trong pipeline triển khai.
- Distributed lock có lease và xử lý lỗi.
- Leader election.
- Hàng đợi tác vụ với cơ chế idempotency.
- Một scheduler/worker được triển khai riêng với quyền sở hữu rõ ràng.

Đừng dùng callback bean hoặc ApplicationRunner để thay thế một bộ điều phối tác vụ phân tán.

## 15. Sự khác nhau giữa startup runner và scheduler

**ApplicationRunner** và **CommandLineRunner** thường chạy một lần trong mỗi lần SpringApplication khởi động thành công đến giai đoạn runner.

**@Scheduled** dùng để chạy công việc theo lịch sau khi scheduling được bật và scheduler được cấu hình:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class CatalogRefreshJob {

    @Scheduled(fixedDelayString = "PT5M")
    public void refresh() {
        // Làm mới catalog theo lịch.
    }
}
~~~

~~~java
@Configuration
@org.springframework.scheduling.annotation.EnableScheduling
class SchedulingConfiguration {
}
~~~

Runner thích hợp cho **bước khởi tạo lúc startup**. Scheduler thích hợp cho **công việc lặp theo lịch**. Có thể runner thực hiện lần chạy đầu tiên rồi scheduler tiếp tục cập nhật, nhưng phải tránh hai tác vụ cạnh tranh trên cùng dữ liệu.

## 16. Thực hành: chọn đúng mốc cho từng yêu cầu

### Tình huống A: Kiểm tra property bắt buộc của một client

Client cần base URL và API key. Nếu thiếu một trong hai, bean không hợp lệ.

**Lựa chọn:** constructor validation hoặc @PostConstruct. Đây là invariant của chính bean, nên fail-fast trong lifecycle của bean là hợp lý.

~~~java
@Component
public class PartnerClient {
    private final PartnerProperties properties;

    public PartnerClient(PartnerProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    void validateConfiguration() {
        if (properties.getBaseUrl() == null
                || properties.getBaseUrl().isBlank()) {
            throw new IllegalStateException("Thiếu partner.base-url");
        }
    }
}
~~~

Không cần đợi toàn bộ ứng dụng ready để phát hiện cấu hình local sai.

### Tình huống B: Nạp dữ liệu nền trước khi nhận request

Dữ liệu cần thiết để xử lý mọi request phải có trước khi app nhận traffic.

**Lựa chọn:** ApplicationRunner đồng bộ. Nếu tác vụ thất bại, startup không đi tới mốc ready.

### Tình huống C: Gửi thông báo sau khi các runner hoàn tất

Một thông báo nội bộ chỉ có ý nghĩa khi quá trình startup thông thường đã thành công.

**Lựa chọn:** ApplicationReadyEvent. Nếu gửi thông báo không được phép làm startup thất bại, hãy xử lý lỗi theo chính sách rõ ràng và ghi nhận kết quả.

### Tình huống D: Warm-up cache mất nhiều phút nhưng API có fallback

Ứng dụng có thể nhận request bằng cách truy vấn nguồn dữ liệu trực tiếp trong khi cache đang warm-up.

**Lựa chọn:** executor hoặc @Async sau một mốc phù hợp, kèm trạng thái tiến độ và fallback. Nếu endpoint nào không có fallback, có thể dùng readiness gate cho endpoint/tính năng hoặc toàn instance tùy kiến trúc.

### Tình huống E: Mở kết nối hoặc thread pool dùng chung

Một bean sở hữu tài nguyên cần khởi tạo và đóng theo lifecycle của chính nó.

**Lựa chọn:** factory method/init callback hoặc cơ chế lifecycle thích hợp; đóng tài nguyên bằng destroy callback. Nếu mở kết nối phụ thuộc dịch vụ ngoài và có retry dài, cân nhắc startup coordinator thay vì nhét logic vào @PostConstruct.

### Tình huống F: Cần kiểm tra mọi singleton eager đã được tạo

Một registry cần thu thập metadata của các singleton thông thường sau pre-instantiation.

**Lựa chọn:** SmartInitializingSingleton. Nhưng nếu cần đợi runner hoặc readiness, hãy dùng hook sau đó.

## 17. Những lỗi thường gặp và cách nhận biết

### 17.1. @PostConstruct chạy trước tác vụ của bean khác

**Dấu hiệu:** log của bean A xuất hiện trước khi bean B hoàn tất tác vụ khởi tạo.

**Giải thích:** container đang tạo bean theo dependency/lifecycle; @PostConstruct của A không phải barrier toàn ứng dụng.

**Cách xử lý:** nếu tác vụ cần toàn context, chuyển điều phối sang hook sau refresh hoặc runner. Nếu chỉ cần dependency cụ thể, khai báo dependency tường minh.

### 17.2. @Transactional không hoạt động trong @PostConstruct

**Dấu hiệu:** dữ liệu ghi trong callback không nằm trong transaction như mong đợi.

**Giải thích:** bean hiện tại có thể chưa được bọc proxy; lời gọi nội bộ không qua proxy.

**Cách xử lý:** gọi một transactional service riêng từ runner hoặc listener sau khi context refresh.

### 17.3. ContextRefreshedEvent đến nhưng startup runner chưa chạy

**Dấu hiệu:** listener thấy context đã refresh nhưng dữ liệu do runner chuẩn bị chưa có.

**Giải thích:** ContextRefreshedEvent xuất hiện trước ApplicationStartedEvent và trước runner.

**Cách xử lý:** dùng ApplicationRunner nếu công việc phải diễn ra trước ready; dùng ApplicationReadyEvent nếu cần đợi runner hoàn tất.

### 17.4. ApplicationReadyEvent đã phát nhưng async warm-up chưa xong

**Dấu hiệu:** ứng dụng nhận traffic trong khi dữ liệu cache còn thiếu.

**Giải thích:** listener đã submit công việc async và trả về; Boot không tự đợi Future hoàn tất.

**Cách xử lý:** nếu công việc bắt buộc, chạy đồng bộ trước ready hoặc tích hợp readiness gate; nếu tùy chọn, cung cấp fallback và trạng thái rõ ràng.

### 17.5. Startup kéo dài hoặc bị treo

**Dấu hiệu:** log không tới ApplicationReadyEvent, runner hoặc callback chạy rất lâu.

**Giải thích:** tác vụ đồng bộ đang giữ quá trình startup, có thể do I/O, retry không giới hạn hoặc deadlock.

**Cách xử lý:** thêm timeout, giới hạn retry, đo thời gian, ghi log theo giai đoạn và tách công việc không bắt buộc sang nền.

### 17.6. Runner chạy trên mọi replica

**Dấu hiệu:** dữ liệu khởi tạo hoặc thông báo bị tạo lặp khi scale deployment.

**Giải thích:** mỗi process chạy runner của riêng mình.

**Cách xử lý:** idempotency, lock phân tán hoặc chuyển tác vụ sang job/worker chuyên biệt.

### 17.7. @PreDestroy không được gọi khi process bị kill

**Dấu hiệu:** tài nguyên bên ngoài còn tồn tại sau khi process bị dừng đột ngột.

**Giải thích:** callback hủy bean chỉ chạy khi lifecycle shutdown được thực hiện phù hợp; nó không bảo đảm trong mọi sự cố.

**Cách xử lý:** thiết kế timeout/lease ở phía dịch vụ ngoài, cơ chế cleanup có thể phục hồi và shutdown grace period phù hợp.

## 18. Cách quan sát các mốc startup

Để hiểu ứng dụng thực sự chạy qua giai đoạn nào, có thể ghi log trong từng hook:

~~~java
@Component
public class LifecycleTrace implements ApplicationRunner {

    @PostConstruct
    void postConstruct() {
        System.out.println("1. Bean PostConstruct");
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("4. ApplicationRunner");
    }

    @EventListener
    public void onContextRefresh(ContextRefreshedEvent event) {
        System.out.println("3. ContextRefreshedEvent");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("5. ApplicationReadyEvent");
    }
}
~~~

Trong ứng dụng thực tế, thứ tự log của nhiều bean có thể xen kẽ vì có nhiều nhánh dependency và listener. Ví dụ này chỉ giúp quan sát các mốc, không phải test thứ tự chi tiết của mọi bean.

Để log có ý nghĩa hơn, ghi timestamp, tên thread, tên bean hoặc giai đoạn startup. Khi tác vụ async được dùng, tên thread giúp nhận ra nó có đang chạy trên executor hay vẫn chặn thread startup.

## 19. Các nguyên tắc thiết kế callback và startup task

1. **Giữ callback bean ngắn và cục bộ.** Constructor, @PostConstruct và initMethod nên chuẩn bị trạng thái của chính bean, xác thực cấu hình và hoàn thành việc cần thiết để bean hợp lệ.
2. **Không dùng @PostConstruct như một barrier toàn ứng dụng.** Nó không có nghĩa mọi singleton, runner hoặc dịch vụ ngoài đã sẵn sàng.
3. **Khai báo dependency tường minh.** Tránh gọi ApplicationContext.getBean() tùy tiện trong callback để tạo thứ tự ẩn.
4. **Dùng runner cho tác vụ cần hoàn tất trước ready.** Runner đồng bộ giúp fail-fast và giữ ứng dụng chưa báo ready cho tới khi xong.
5. **Dùng ApplicationReadyEvent khi cần đợi runner.** Đây là mốc rộng hơn ContextRefreshedEvent.
6. **Tách tác vụ nền ra khỏi startup thread.** Có executor, timeout, retry và xử lý exception phù hợp.
7. **Biểu diễn readiness đúng với khả năng phục vụ request.** Nếu tác vụ async vẫn là điều kiện bắt buộc, cần health/readiness gate thực sự.
8. **Thiết kế tác vụ idempotent.** Startup có thể lặp qua restart, test context hoặc nhiều replica.
9. **Quản lý tài nguyên theo lifecycle.** Callback hủy hữu ích nhưng không thay thế timeout, lease và cleanup có thể phục hồi.
10. **Đo thời gian startup.** Biết callback hoặc runner nào chiếm thời gian giúp quyết định công việc nào nên đồng bộ và công việc nào có thể chạy nền.

## 20. Những hiểu nhầm thường gặp

**“@PostConstruct nghĩa là ứng dụng đã khởi động xong.”**  
Không. Nó chỉ là callback sau injection của một bean cụ thể.

**“Sau khi một bean chạy @PostConstruct thì mọi bean khác đã sẵn sàng.”**  
Không. Bean khác có thể chưa được tạo hoặc chưa hoàn tất tác vụ riêng.

**“ContextRefreshedEvent và ApplicationReadyEvent là cùng một mốc.”**  
Không. ContextRefreshedEvent báo context đã refresh; ApplicationReadyEvent được phát sau khi Spring Boot gọi xong ApplicationRunner và CommandLineRunner.

**“SmartInitializingSingleton là callback sau khi toàn ứng dụng ready.”**  
Không. Nó chạy sau pre-instantiation của singleton eager, vẫn trong quá trình refresh context.

**“ApplicationRunner chạy sau ApplicationReadyEvent.”**  
Không. Runner chạy trước ApplicationReadyEvent.

**“@Async được gọi từ bất kỳ nơi nào cũng chạy nền.”**  
Không. Trong proxy mode thông dụng, self-invocation không đi qua proxy; async processing còn cần được bật và executor phù hợp.

**“Listener của ApplicationReadyEvent luôn chờ mọi tác vụ nền.”**  
Không. Listener đồng bộ chỉ chờ phần code chạy đồng bộ trong listener. Nếu listener submit Future/async rồi trả về, công việc nền có thể vẫn tiếp tục.

**“Một runner chỉ chạy một lần cho toàn bộ deployment.”**  
Không. Nó chạy theo mỗi lần application process khởi động; nhiều replica có thể cùng chạy.

**“@PreDestroy chắc chắn chạy khi JVM dừng.”**  
Không. Shutdown bình thường mới có cơ hội thực hiện callback; crash hoặc kill đột ngột không bảo đảm.

**“Tác vụ startup nào cũng nên chạy đồng bộ để đơn giản.”**  
Không. Chỉ tác vụ cần hoàn tất trước readiness mới nên chặn mốc ready. Công việc tùy chọn hoặc dài hạn có thể chạy nền nếu có fallback và quan sát phù hợp.

## Ghi nhớ cốt lõi

**Callback bean** như @PostConstruct, afterPropertiesSet và initMethod phục vụ việc khởi tạo một bean. Chúng không bảo đảm toàn bộ ApplicationContext hoặc ứng dụng đã khởi động xong. **SmartInitializingSingleton** chạy sau khi các singleton eager thông thường được tạo, còn **ContextRefreshedEvent** báo context đã refresh; cả hai vẫn xuất hiện trước các startup runner.

Nếu tác vụ phải hoàn tất trước khi ứng dụng báo ready, dùng **ApplicationRunner** hoặc **CommandLineRunner** đồng bộ. Nếu cần đợi các runner hoàn tất, dùng **ApplicationReadyEvent**. Nếu công việc có thể chạy nền, quản lý executor, lỗi và trạng thái readiness rõ ràng; đừng giả định @Async sẽ giữ ứng dụng chưa nhận traffic. Chọn đúng mốc theo điều kiện tiên quyết của tác vụ giúp startup dễ dự đoán, tránh callback chạy quá sớm và làm cho trạng thái sẵn sàng của ứng dụng phản ánh đúng khả năng phục vụ request.
