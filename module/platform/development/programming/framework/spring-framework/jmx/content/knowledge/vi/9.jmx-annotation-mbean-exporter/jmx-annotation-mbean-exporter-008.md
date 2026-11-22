# Thứ tự khởi tạo AnnotationMBeanExporter với các bean phụ thuộc

## 1. Bài toán: exporter chạy ở đâu trong vòng đời Spring?

Trong Spring Framework, `AnnotationMBeanExporter` giúp phát hiện các bean được khai báo quản trị bằng annotation như `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, sau đó xuất chúng thành MBean vào `MBeanServer`. Vấn đề phát sinh khi bean cần được xuất ra JMX **phụ thuộc các thành phần khác**: datasource, cache, message consumer, scheduler, service khởi tạo kết nối hoặc cấu hình runtime.

Một câu hỏi tưởng đơn giản nhưng rất quan trọng: **khi exporter đăng ký MBean, các dependency của bean quản trị đã thực sự sẵn sàng đến mức nào?**

Cần tách ba mốc:

1. **Bean được tạo và dependency injection hoàn tất**: các đối tượng phụ thuộc đã được Spring resolve theo cơ chế khởi tạo singleton.
2. **Bean đã chạy callback khởi tạo của chính nó**: `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom init method; các callback được áp dụng theo vòng đời tương ứng.
3. **Hệ thống bên ngoài đã sẵn sàng phục vụ**: kết nối remote hoạt động, cache warm-up xong, listener đã subscribe, hoặc background task đã đạt trạng thái READY. Mốc thứ ba không nhất thiết trùng với hai mốc đầu.

MBean có thể đã xuất hiện trong JConsole trước khi một tài nguyên ngoại vi đạt trạng thái mong đợi. Khi đó client JMX gọi `getStatus()` hoặc một operation có thể thấy trạng thái `STARTING`, nhận kết quả chưa đầy đủ, hoặc gặp lỗi nếu code giả định hệ thống đã `READY`.

Bài này tập trung vào cách hiểu và kiểm soát **thứ tự khởi tạo**, không biến JMX exporter thành cơ chế điều phối toàn bộ hệ thống.

## 2. Những thành phần tham gia

Một sơ đồ điển hình:

```text
ApplicationContext.refresh()
          |
          +--> đăng ký BeanDefinition / BeanFactoryPostProcessor
          |
          +--> đăng ký BeanPostProcessor
          |
          +--> khởi tạo singleton không lazy
                  |
                  +--> DataSource / Cache / BusinessService
                  |
                  +--> ManagementFacade (@ManagedResource)
                  |
                  +--> AnnotationMBeanExporter
                             |
                             +--> tìm bean quản trị
                             +--> tạo MBeanInfo qua annotation metadata
                             +--> register MBean vào MBeanServer
          |
          +--> hoàn thành refresh / lifecycle startup
          |
       client JMX có thể truy cập MBean
```

Thứ tự chính xác giữa các singleton độc lập không nên được suy ra từ thứ tự tên class, thứ tự khai báo trong source hay thứ tự quét package. Spring tạo dependency trước khi có thể tạo đối tượng cần dependency; những singleton không có quan hệ phụ thuộc rõ ràng có thể được khởi tạo theo trật tự triển khai mà không nên coi là hợp đồng nghiệp vụ.

Các vai trò:

| Thành phần | Trách nhiệm | Điều cần lưu ý |
|---|---|---|
| `ManagementFacade` | Công bố trạng thái/operation quản trị | Không giả định mọi tài nguyên luôn READY |
| `BusinessService` | Chạy logic nghiệp vụ | Có thể cần datasource hoặc cache |
| `DataSource` / client bên ngoài | Truy cập hệ thống khác | Bean tồn tại không chứng minh kết nối đã hoạt động |
| `AnnotationMBeanExporter` | Khám phá và đăng ký MBean từ annotation | Có thể làm MBean nhìn thấy trong quá trình context khởi tạo |
| `MBeanServer` | Registry MBean, xử lý yêu cầu JMX | Không quản lý lifecycle nghiệp vụ của service |
| `SmartLifecycle` | Điều phối start/stop theo phase | Dành cho thành phần lifecycle, không thay thế dependency injection |

Đặc biệt, `AnnotationMBeanExporter` là một dạng tiện ích export. `@ManagedResource` chỉ nói bean muốn phơi bày giao diện quản trị; nó **không tự khởi động service nền** và không chứng minh rằng các tài nguyên mà service dùng đã hoàn toàn khỏe.

## 3. Dependency injection xác lập thứ tự nào?

Giả sử:

```java
@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }
}
```

và một bean quản trị phụ thuộc vào service:

```java
@Component
@ManagedResource(objectName = "demo.inventory:type=InventoryMonitor")
public class InventoryMonitor {
    private final InventoryService inventoryService;

    public InventoryMonitor(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ManagedAttribute
    public boolean isAvailable() {
        return inventoryService.isAvailable();
    }
}
```

Spring phải resolve `InventoryService` trước khi tạo xong `InventoryMonitor`; service lại cần `InventoryRepository`. Quan hệ constructor injection thể hiện **đồ thị phụ thuộc trực tiếp**:

```text
InventoryRepository
       -> InventoryService
              -> InventoryMonitor
```

Điều đó đảm bảo những dependency bắt buộc được cung cấp trước khi constructor của monitor hoàn thành. Nhưng nó không nhất thiết đảm bảo repository có thể kết nối database ngay lập tức, hoặc service đã xử lý xong một tác vụ background bắt đầu sau refresh.

Nếu một getter JMX gọi database để kiểm tra availability, nó có thể làm một thao tác mạng ngay trong luồng xử lý yêu cầu quản trị. Thiết kế vững hơn thường là trả một **trạng thái đã quan sát/được cập nhật** như `STARTING`, `READY`, `DEGRADED`, `STOPPED` thay vì kích hoạt quy trình khởi tạo trong getter.

## 4. Thời điểm AnnotationMBeanExporter tham gia

`AnnotationMBeanExporter` là biến thể tiện lợi của cơ chế `MBeanExporter` có sẵn hỗ trợ metadata từ các annotation quản trị. Exporter tích hợp với Spring bean lifecycle để đăng ký MBean khi context khởi tạo. Những chi tiết cụ thể về lúc quét, đăng ký và deferred registration phụ thuộc phiên bản Spring và cấu hình exporter, ví dụ `autodetect`, mapping được chỉ định và chế độ đăng ký.

Điều cần hiểu ở cấp mô hình:

- Exporter phải có `MBeanServer` để đăng ký các MBean.
- Bean được export phải được resolve và cung cấp theo cơ chế phù hợp của Spring.
- Việc đăng ký MBean chỉ thiết lập **khả năng truy cập quản trị**; nó không đợi mọi job nền hoàn tất.
- Một khi MBean đã được đăng ký, client JMX có thể đọc attribute hoặc gọi operation nếu có kết nối và quyền truy cập.
- Nếu initialization của bean hoặc registration thất bại, quá trình refresh có thể thất bại hoặc exporter có thể xử lý theo registration policy đã cấu hình.

Không nên dựa vào trật tự file cấu hình Java để mặc định `AnnotationMBeanExporter` sẽ luôn chạy sau mọi service. Cần mô hình dependency/lifecycle rõ ràng hoặc giao diện quản trị chịu được trạng thái chưa sẵn sàng.

## 5. @DependsOn: buộc bean được khởi tạo trước

Khi một bean cần bean khác **được khởi tạo trước**, nhưng không có constructor/property dependency trực tiếp, Spring cung cấp `@DependsOn`:

```java
@Configuration
public class InitializationConfig {

    @Bean("managementInfrastructure")
    public ManagementInfrastructure managementInfrastructure() {
        return new ManagementInfrastructure();
    }

    @Bean
    @DependsOn("managementInfrastructure")
    public InventoryMonitor inventoryMonitor(
            InventoryService inventoryService) {
        return new InventoryMonitor(inventoryService);
    }
}
```

`@DependsOn` cho Spring biết bean `managementInfrastructure` phải được khởi tạo trước `inventoryMonitor`. Với singleton trong cùng context, quan hệ này cũng có ý nghĩa đối với thứ tự hủy bean: đối tượng phụ thuộc thường được hủy trước bean mà nó phụ thuộc vào.

**Giới hạn quan trọng:** `@DependsOn` chờ quá trình **khởi tạo bean** hoàn tất theo hợp đồng Spring, không chờ một thao tác async bất kỳ kết thúc. Ví dụ, nếu `managementInfrastructure` trong `@PostConstruct` chỉ submit một task lên executor rồi trả về, `@DependsOn` không có nghĩa task đã hoàn thành.

Một pattern không phù hợp là:

```java
@PostConstruct
void start() {
    executor.submit(this::connectToRemoteSystem);
}
```

rồi suy luận rằng bean khác có `@DependsOn` đã có thể dùng kết nối remote ngay. Để phản ánh trạng thái, cần một cơ chế READY riêng hoặc một lifecycle barrier có hợp đồng chờ rõ ràng.

### 5.1. Có nên gắn @DependsOn lên exporter?

Nếu có yêu cầu rõ ràng rằng một bean hạ tầng phải được khởi tạo trước exporter, có thể khai báo dependency ở BeanDefinition của exporter. Nhưng không nên dùng `@DependsOn` như một “thuốc chữa mọi race condition”. Nó không tự chờ external readiness, và thay đổi thứ tự exporter đôi khi làm trễ quản trị hoặc tạo vòng phụ thuộc.

Thường dễ hiểu hơn khi để bean được export có dependency tường minh, dùng `SmartLifecycle` cho hoạt động background và cho MBean biết trạng thái chưa sẵn sàng. Nếu thực sự cần trì hoãn việc đăng ký MBean, hãy xác định chính xác mốc lifecycle và cơ chế registration thay vì dựa vào tên bean/annotation ngẫu nhiên.

## 6. @PostConstruct và InitializingBean diễn ra trước khi nào?

Trong quá trình khởi tạo Spring bean, constructor và injection xảy ra trước các callback init như `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()`. `BeanPostProcessor` có thể bao quanh những giai đoạn này; proxy cũng có thể được tạo trong post-processing.

Ví dụ:

```java
@Component
public class CacheManager {

    private volatile boolean initialized;

    @PostConstruct
    public void initialize() {
        // Chỉ minh họa việc khởi tạo đồng bộ.
        loadLocalConfiguration();
        initialized = true;
    }

    public boolean isInitialized() {
        return initialized;
    }

    private void loadLocalConfiguration() {
        // Load file/configuration một cách đồng bộ.
    }
}
```

Nếu `loadLocalConfiguration()` chạy đồng bộ và không trả về trước khi xong, những bean được tạo sau đó với dependency bắt buộc vào `CacheManager` sẽ nhận bean đã qua callback initialization thông thường.

Tuy nhiên, nếu `initialize()` chỉ kích hoạt một `CompletableFuture`, `initialized=true` phải được đặt **khi công việc thực sự hoàn thành**, không phải ngay sau khi submit. Cũng không nên cố đồng bộ hóa toàn bộ startup bằng cách chặn trong `@PostConstruct` vô thời hạn: có thể làm application context treo và tạo deadlock nếu phần việc đang chờ lại cần bean/context chưa hoàn thành refresh.

## 7. Ví dụ: xuất một trạng thái lifecycle rõ ràng

Thay vì để getter ném lỗi khi service chưa sẵn sàng, thiết kế trạng thái có thể quan sát:

```java
public enum StartupState {
    NEW, STARTING, READY, FAILED, STOPPED
}
```

Một service quản lý startup:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicReference<StartupState> state =
        new AtomicReference<>(StartupState.NEW);

    public StartupState getState() {
        return state.get();
    }

    public void markStarting() {
        state.set(StartupState.STARTING);
    }

    public void markReady() {
        state.set(StartupState.READY);
    }

    public void markFailed() {
        state.set(StartupState.FAILED);
    }

    public void markStopped() {
        state.set(StartupState.STOPPED);
    }
}
```

MBean quản trị chỉ đọc:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "demo.catalog:type=CatalogStatus",
    description = "Catalog startup state"
)
public class CatalogStatusMBean {
    private final CatalogService service;

    public CatalogStatusMBean(CatalogService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Current lifecycle state")
    public String getState() {
        return service.getState().name();
    }

    @ManagedAttribute(description = "Whether catalog can serve requests")
    public boolean isReady() {
        return service.getState() == StartupState.READY;
    }
}
```

Khi được export đúng cấu hình, client JMX có thể thấy `State=NEW`, `STARTING`, `READY`, `FAILED`, `STOPPED` tùy thời điểm. Getter không ép service tự khởi động hoặc mở kết nối. Điều này giúp vận hành phân biệt **MBean có thể truy cập** với **nghiệp vụ sẵn sàng**.

Nếu một operation quản trị chỉ hợp lệ khi READY, nó nên kiểm tra trạng thái:

```java
@ManagedOperation
public void refreshCatalog() {
    if (service.getState() != StartupState.READY) {
        throw new IllegalStateException("Catalog is not READY");
    }
    service.refresh();
}
```

Khi Spring/JMX gọi operation, exception cần được client xử lý theo cơ chế JMX. Không dùng việc MBean xuất hiện trong registry làm chứng cứ duy nhất để bật các thao tác có tác dụng phụ.

## 8. SmartLifecycle và phase: điều phối hoạt động start/stop

Spring cung cấp `SmartLifecycle` cho thành phần có hành vi start/stop. Một đặc điểm quan trọng là các bean `SmartLifecycle` có thể được start theo **phase** trong quá trình application context refresh; phase thấp hơn thường được start trước phase cao hơn, và shutdown thực hiện theo chiều ngược.

Ví dụ minh họa:

```java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class ConsumerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        // Start đồng bộ hoặc thiết lập readiness riêng nếu async.
        running.set(true);
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

`SmartLifecycle` còn có hợp đồng `stop(Runnable callback)` cho shutdown bất đồng bộ, tùy implementation và phiên bản; phải gọi callback khi công việc dừng kết thúc. Code ví dụ chỉ dùng stop đồng bộ đơn giản.

**Điểm dễ nhầm:** phase điều phối **lifecycle start/stop** của những bean tham gia cơ chế đó; nó không phải một quy tắc chung để sắp xếp bất kỳ `@Bean` nào hoặc tự động bảo đảm `AnnotationMBeanExporter` đăng ký sau mọi component. Nếu MBean cần báo trạng thái lúc `SmartLifecycle` chưa start, `State=STARTING` là kết quả hợp lệ.

Cần phân biệt:

```text
Dependency ordering: A phải được tạo trước B.
Lifecycle phasing:  A.start() chạy trước B.start() theo phase.
Operational readiness:  hệ thống phụ thuộc đã thực sự có thể phục vụ.
```

Ba quan hệ này có thể liên quan, nhưng không đồng nhất.

## 9. ApplicationReadyEvent và ContextRefreshedEvent

Trong Spring Framework, `ContextRefreshedEvent` được phát khi application context đã được khởi tạo hoặc refresh. Trong Spring Boot, `ApplicationReadyEvent` thường là dấu hiệu boot sequence đã hoàn thành và ứng dụng sẵn sàng theo mô hình Boot.

Ví dụ với Spring Boot:

```java
@Component
public class ReadinessMarker {
    private final CatalogService service;

    public ReadinessMarker(CatalogService service) {
        this.service = service;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        service.markReady();
    }
}
```

Cần import `org.springframework.boot.context.event.ApplicationReadyEvent` và `org.springframework.context.event.EventListener` khi dùng ví dụ trên. Đây là hook của **Spring Boot**, không có sẵn trong Spring Framework thuần nếu không dùng Boot.

Tuy nhiên, `ApplicationReadyEvent` chỉ chứng tỏ một mốc của tiến trình khởi động Boot. Nếu dịch vụ phụ thuộc một hệ thống ngoài hoặc có background warm-up chưa hoàn tất, chính ứng dụng vẫn phải quyết định khi nào thực sự READY. Không nên đánh dấu READY vô điều kiện nếu điều kiện nghiệp vụ chưa đạt.

Một mô hình tốt là:

```text
Context refresh hoàn tất
    -> một số infrastructure đã được tạo
    -> lifecycle start tiếp tục
    -> readiness được công bố từ trạng thái kiểm chứng
    -> JMX getter trả trạng thái hiện thời
```

Như vậy exporter có thể xuất MBean trước hoặc trong các mốc startup mà client vẫn nhìn thấy diễn tiến hợp lệ.

## 10. Dependency chain phức tạp và vòng phụ thuộc

Nếu một bean quản trị phụ thuộc service, service lại phụ thuộc exporter hoặc một bean mà exporter gián tiếp tạo ra, bạn có thể tạo vòng phụ thuộc:

```text
ManagementFacade
      -> BusinessService
             -> ManagementFacade
```

hoặc:

```text
Exporter -> ManagementFacade -> MonitoringInfrastructure -> Exporter
```

Constructor injection thường làm lỗi vòng phụ thuộc xuất hiện rõ trong quá trình tạo bean. Dùng setter injection hoặc lazy proxy có thể che việc tạo vòng trong một số trường hợp, nhưng không làm kiến trúc dễ hiểu hơn.

Để tránh:

1. Giữ `ManagementFacade` là lớp quan sát mỏng, phụ thuộc một chiều vào service hoặc state holder.
2. Không để business service cần exporter chỉ để hoạt động.
3. Tách `LifecycleState`/metrics holder khỏi UI quản trị nếu nhiều thành phần cần cùng thông tin.
4. Không gọi operation JMX trong constructor hoặc initialization của chính dependency mà operation đó cần.
5. Chỉ dùng `@Lazy` khi trì hoãn khởi tạo thực sự là một lựa chọn thiết kế, không phải cách giấu đồ thị phụ thuộc lỗi.

Sơ đồ ít rủi ro hơn:

```text
BusinessService ---> SharedOperationalState <--- ManagementFacade
                                               |
                                          exporter đăng ký
```

Nếu exporter khởi tạo một bean để lấy metadata, việc đó không nên kích hoạt một chuỗi side effect khiến service truy cập tài nguyên chưa được chuẩn bị.

## 11. Exporter và proxy: được xuất đối tượng nào?

Trong ứng dụng Spring, bean có thể được bọc bởi proxy, chẳng hạn khi dùng AOP, transaction hoặc scoped proxy. Khi `AnnotationMBeanExporter` làm việc với bean, cần phân biệt **bean definition**, object được tạo, proxy trả về từ container và interface/phương thức thực sự được export.

Các hiện tượng có thể xảy ra:

- Annotation đặt trên implementation nhưng metadata inspection đi qua proxy.
- Interface quản trị chỉ khai báo một số method, còn implementation có nhiều method khác.
- Bean được tạo lazy và chỉ được khởi tạo khi exporter hoặc thành phần khác yêu cầu.
- Một method quản trị gọi sang service có transactional proxy, nên kết quả phụ thuộc execution context.

Không nên giả định rằng annotation trên một class bất kỳ sẽ luôn được công bố đúng cách dưới mọi loại proxy. Khi gặp vấn đề, kiểm tra `MBeanInfo` của ObjectName đã đăng ký, kiểu bean thực tế và cơ chế exporter/assembler. Giải quyết theo cấu hình proxy và version Spring đang dùng thay vì tùy tiện đảo thứ tự tạo bean.

## 12. Đừng nhầm “đăng ký thành công” với “dependency healthy”

Giả sử `DatabaseClient` có constructor không kết nối ngay; kết nối thật chỉ được mở khi query đầu tiên. Spring đã tạo bean và exporter đã đăng ký monitor, nhưng database có thể đang down.

Ba biểu hiện:

| Điều quan sát | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|
| `ManagementFacade` có trong context | Bean đã được tạo hoặc có thể resolve tùy scope | Dependency ngoài đã khỏe |
| MBean đã xuất hiện trong JConsole | Registration đã thành công | Service đang READY |
| `getState() == READY` | Ứng dụng tự công bố READY | Tất cả chức năng đều thành công mãi mãi |

Một health/readiness attribute cần được cập nhật dựa trên tín hiệu có ý nghĩa, có thể gồm ping, warm-up completion, circuit breaker hoặc trạng thái subscription. Tránh để getter thực hiện health check nặng mỗi lần JConsole refresh; tốt hơn là cập nhật định kỳ hoặc dựa trên sự kiện, rồi getter trả trạng thái ngắn gọn.

## 13. Khi nào cần trì hoãn đăng ký MBean?

Không phải lúc nào cũng cần. Nhiều hệ thống cố ý cho MBean xuất hiện **sớm** để công cụ vận hành thấy trạng thái STARTING và lý do khởi động chậm. Việc ẩn MBean cho đến READY có thể làm mất khả năng quan sát đúng lúc hệ thống gặp lỗi startup.

Tuy nhiên, nếu MBean chỉ hợp lệ sau khi có một tài nguyên bắt buộc, có thể cần kiểm soát registration. Các lựa chọn:

- Thiết kế bean quản trị trả trạng thái `NOT_READY` trong thời gian đầu.
- Khởi tạo dependency bắt buộc đồng bộ trước exporter thông qua quan hệ bean thực sự, khi điều đó không làm block startup bất hợp lý.
- Đăng ký MBean chủ động khi đạt một mốc lifecycle cụ thể, thay vì auto-detection mặc định; cần quản lý unregister khi shutdown.
- Dùng cơ chế registration/exporter phù hợp với version Spring và ownership của MBeanServer.

Lựa chọn cuối cùng cần xem xét khả năng client kết nối sớm, xử lý lỗi registration, trùng ObjectName và quyền vận hành. Việc gỡ MBean trong shutdown cũng có thứ tự; callback quản trị có thể đang chạy lúc ứng dụng bắt đầu đóng, nên operation cần kiểm tra trạng thái và xử lý an toàn.

## 14. Ví dụ cấu hình AnnotationMBeanExporter

Cách đơn giản để bật annotation-based JMX export trong Spring Framework là dùng `@EnableMBeanExport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Spring tạo hạ tầng exporter phù hợp để phát hiện `@ManagedResource` cùng các annotation accessor/operation. Trong những cấu hình cần can thiệp sâu hơn, có thể khai báo `AnnotationMBeanExporter` trực tiếp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ManualJmxConfiguration {

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

**Chọn một cơ chế tạo exporter rõ ràng.** Tránh vừa `@EnableMBeanExport`, vừa khai báo nhiều exporter cùng đăng ký một tập ObjectName nếu không chủ đích thiết kế chính sách registration. Hai exporter có thể tranh cùng tên và gây `InstanceAlreadyExistsException` hoặc hành vi ghi đè theo policy không mong muốn.

Với Spring Boot, cấu hình auto-export có thể khác; cần xem `spring.jmx.enabled` và phiên bản Boot đang dùng. Các ví dụ trên nhắm vào Spring Framework cơ bản.

### 14.1. Cấu hình phụ thuộc theo tên BeanDefinition

Nếu thật sự cần thứ tự rõ ràng cho một bean exporter tự khai báo, có thể gắn dependency:

```java
@Bean
@DependsOn("managementPrerequisite")
public AnnotationMBeanExporter annotationMBeanExporter() {
    return new AnnotationMBeanExporter();
}
```

Ví dụ có tác dụng khi `managementPrerequisite` là bean được khởi tạo đồng bộ và có tên đúng. `@DependsOn` không chờ một công việc async do bean đó kích hoạt hoàn tất. Nếu prerequisite chưa thực sự sẵn sàng, vẫn cần một readiness state/condition riêng.

## 15. Quan sát thứ tự thực tế bằng log và JMX

Khi học lifecycle, đừng suy đoán chỉ từ tên class. Hãy đặt log tại những mốc cần thiết, ví dụ:

```java
@Component
public class StartupProbe {
    private static final Logger log =
        LoggerFactory.getLogger(StartupProbe.class);

    @PostConstruct
    void initialized() {
        log.info("StartupProbe: PostConstruct");
    }

    @EventListener(ContextRefreshedEvent.class)
    void contextRefreshed() {
        log.info("StartupProbe: ContextRefreshedEvent");
    }
}
```

Các import cần thiết với dự án Spring dùng SLF4J và Jakarta annotations:

```java
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
```

Trong `ManagementFacade`, thêm log ở constructor và callback khởi tạo (nếu cần); đồng thời có thể dùng `MBeanServer.queryNames(new ObjectName("demo.catalog:*"), null)` để xem các MBean đã đăng ký sau một mốc lifecycle. Chỉ thực hiện truy vấn này khi bạn đã có tham chiếu MBeanServer đúng; tránh tạo thêm exporter chỉ để log.

Quan sát theo chuỗi:

```text
CatalogService constructed
CatalogService initialized
ManagementFacade constructed
ManagementFacade initialized
MBean registered
Context refreshed
Application ready (nếu dùng Spring Boot)
```

Đây là **trật tự mong muốn minh họa**, không phải output cố định của mọi Spring application. Kết quả thực tế phụ thuộc cấu hình, auto-detection, lazy initialization, post-processors và các dependency khác. Cần ghi timestamp/trace từ chính ứng dụng đang chạy.

## 16. Lỗi thường gặp

### 16.1. MBean được đăng ký nhưng getter ném NullPointerException

Nguyên nhân thường là bean quản trị giữ một dependency được gán ngoài hợp đồng injection hoặc truy cập dữ liệu chỉ được khởi tạo sau đó. Dùng constructor injection cho dependency bắt buộc, biểu diễn trạng thái STARTING nếu dependency ngoài chưa sẵn sàng và tránh dereference trước khi READY.

### 16.2. Thêm @DependsOn nhưng vẫn gặp lỗi tài nguyên chưa sẵn sàng

Bean phụ thuộc được tạo trước nhưng công việc async của nó chưa hoàn thành. Cần sửa readiness contract hoặc chuyển sang init đồng bộ khi phù hợp, không tiếp tục thêm chuỗi `@DependsOn` dài chỉ để thử.

### 16.3. Bean circular dependency

Một monitor gọi service mà service lại gọi monitor/exporter ngay lúc constructor; Spring có thể báo lỗi vòng phụ thuộc. Tách state holder và tránh dependency ngược từ business service tới lớp JMX.

### 16.4. MBean không thấy trong JConsole

Kiểm tra exporter đã được cấu hình, bean có `@ManagedResource`, tên ObjectName hợp lệ, context đã refresh, không có duplicate registration và JConsole kết nối đúng JVM. Một bean có annotation nhưng không được exporter quét vẫn không xuất hiện.

### 16.5. MBean chỉ xuất hiện sau khi gọi bean lần đầu

Lazy initialization hoặc registration strategy có thể tạo thay đổi thời điểm xuất hiện. Kiểm tra chính sách lazy/proxy và exporter; đừng coi mọi singleton luôn được tạo ngay đầu quá trình refresh.

### 16.6. Exporter đăng ký trùng ObjectName

Hai exporter hoặc hai bean có cùng ObjectName có thể xung đột. Thiết kế naming strategy và ownership rõ ràng, chỉ bật một cấu hình auto-export cho cùng tập bean khi không có lý do khác.

### 16.7. Operation chạy khi service đang STOPPING

Client đã giữ kết nối và thao tác trong lúc shutdown. Operation phải từ chối hoặc xử lý an toàn theo trạng thái lifecycle, thay vì chỉ dựa vào việc MBean có còn trong registry ở thời điểm bắt đầu gọi.

## 17. Bài tập thực hành

**Bài 1 — Dependency injection và startup state.** Tạo `CatalogService` và `CatalogStatusMBean` bằng constructor injection. Cho service đi qua `NEW -> STARTING -> READY` bằng một worker nền. Mở JConsole, ghi nhận `State` qua các mốc. Giải thích tại sao MBean có thể đọc được trước khi READY.

**Bài 2 — So sánh đồng bộ và bất đồng bộ.** Tạo bean `Initializer` với `@PostConstruct`: lần đầu thực hiện công việc đồng bộ rồi trả về; lần thứ hai chỉ submit task lên executor. Gắn `@DependsOn("initializer")` cho một bean khác và quan sát thời điểm bean thứ hai được tạo. Giải thích giới hạn của `@DependsOn`.

**Bài 3 — SmartLifecycle phase.** Tạo hai `SmartLifecycle` bean `A` và `B` với phase lần lượt 0 và 100. In log `start()`, `stop()` và so sánh thứ tự. Giải thích vì sao phase không phải công cụ tổng quát để đặt thứ tự khởi tạo mọi bean.

**Bài 4 — MBean operation trong trạng thái lỗi.** Thêm `refreshCatalog()` vào monitor. Khi service ở `FAILED` hoặc `STOPPED`, từ chối operation bằng thông báo rõ ràng. So sánh hành vi giữa `getState()` và operation.

**Bài 5 — Gỡ vòng phụ thuộc.** Bắt đầu với graph `ManagementFacade -> BusinessService -> ManagementFacade`. Tái cấu trúc thành một `SharedOperationalState` được cả hai tham chiếu, rồi giải thích dependency graph mới.

**Bài 6 — Quan sát exporter.** Bật `@EnableMBeanExport`, tạo một bean có `@ManagedResource`, log các callback init và sự kiện context. Sau khi start, truy vấn `MBeanServer` để kiểm tra ObjectName. Thực hành này nhằm quan sát lifecycle, không được giả định kết quả trước khi chạy.

## 18. Câu hỏi tự kiểm tra

1. Việc Spring tạo xong một dependency có chắc rằng dịch vụ bên ngoài đã READY không?
2. Constructor injection và `@DependsOn` giải quyết loại thứ tự nào?
3. `@PostConstruct` hoàn tất có nghĩa một `CompletableFuture` được submit bên trong đã xong không?
4. `SmartLifecycle.getPhase()` ảnh hưởng đến những callback nào?
5. `ContextRefreshedEvent` thuộc Spring Framework hay Spring Boot?
6. `ApplicationReadyEvent` thuộc framework nào và có chứng minh mọi external dependency healthy không?
7. Tại sao một MBean trả `State=STARTING` có thể hữu ích hơn việc ẩn MBean cho tới READY?
8. Vì sao đăng ký nhiều `AnnotationMBeanExporter` cho cùng bean có thể gây lỗi?
9. Operation quản trị nên làm gì nếu service đang STOPPING?
10. Khi gặp lỗi thứ tự startup, những mốc log và metadata JMX nào giúp thu hẹp nguyên nhân?

## 19. Ghi nhớ

**Thứ tự khởi tạo và trạng thái sẵn sàng là hai hợp đồng khác nhau.** Spring dependency injection và `@DependsOn` điều phối thứ tự tạo bean; init callback hoàn tất theo lifecycle Spring; `SmartLifecycle` điều phối hoạt động start/stop; còn readiness của hệ thống bên ngoài cần được biểu diễn và kiểm chứng riêng.

`AnnotationMBeanExporter` công bố giao diện quản trị vào `MBeanServer`. MBean được đăng ký thành công chỉ chứng tỏ nó có thể được truy cập qua JMX; một getter và operation an toàn phải tự xử lý trường hợp service vẫn STARTING, FAILED hoặc STOPPING. Thiết kế dependency một chiều, dùng trạng thái lifecycle rõ ràng và kiểm tra kết quả runtime sẽ giúp JMX hoạt động đáng tin cậy khi ứng dụng Spring có nhiều bean phụ thuộc.
