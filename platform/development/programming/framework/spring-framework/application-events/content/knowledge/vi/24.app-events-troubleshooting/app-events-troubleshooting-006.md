# Event được phát trước khi listener đăng ký trong Spring Application Events

## 1. Tình huống: publisher đã chạy nhưng listener không thấy sự kiện

Một lỗi khó chẩn đoán trong hệ thống Spring là **producer đã gọi `ApplicationEventPublisher.publishEvent(...)`, nhưng listener mong đợi không nhận được event**. Đặc biệt khi event được phát trong giai đoạn khởi động hoặc trước lúc listener được đăng ký vào `ApplicationContext`, việc bổ sung `@EventListener` sau đó không tự làm event cũ xuất hiện trở lại.

Ví dụ một hệ thống vừa tạo bản ghi cấu hình lúc bootstrap:

~~~text
Thời điểm        Producer                          Listener
---------        -----------------------           -------------------------
t0               ApplicationContext đang refresh    chưa được đăng ký
t1               publish(ReferenceDataLoaded)      chưa có listener phù hợp
t2               ...                               @EventListener được đăng ký
t3               ứng dụng sẵn sàng                 đợi ReferenceDataLoaded
t4               không có event mới                 không làm gì
~~~

Hệ quả có thể là cache không được nạp, read model thiếu dữ liệu, tác vụ kích hoạt theo event không bao giờ chạy hoặc một component tưởng rằng hệ thống chưa hoàn tất khởi tạo.

**Điểm mấu chốt:** `ApplicationEventPublisher` là cơ chế phân phát sự kiện của Spring, **không phải event store hay message broker bền vững**. Một listener đăng ký muộn không mặc nhiên nhận lại những event đã được phân phát trước đó.

Tuy nhiên có một ngoại lệ cần nói chính xác: trong một phần giai đoạn `refresh()`, `AbstractApplicationContext` có cơ chế thu thập **early application events** và phát chúng khi multicaster/listener tương ứng đã sẵn sàng. Đây là **bộ đệm bootstrap giới hạn**, không phải cam kết phát lại cho mọi `@EventListener` bất kể thời điểm đăng ký. Bài học này phân biệt hai tình huống thay vì kết luận đơn giản rằng “event trong startup luôn mất”.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **publish đã xảy ra**, **listener đã đăng ký**, **listener được gọi** và **handler xử lý thành công**.
- Giải thích thứ tự khởi tạo `ApplicationContext`, `ApplicationListener`, `@EventListener` và `ContextRefreshedEvent`.
- Tái hiện trường hợp đăng ký listener **sau khi** event đã được phát mà **không có replay**.
- Nhận diện event quá sớm từ constructor, `@PostConstruct`, bước bootstrap hoặc các Spring Boot startup event.
- Chọn cách sửa phù hợp: đăng ký listener sớm, chuyển thời điểm publish, dùng runner/lifecycle hook hoặc dùng lưu trữ bền vững nếu bắt buộc giao đủ sự kiện.
- Viết integration test kiểm chứng đúng thứ tự, tránh nhầm với lỗi type/transaction/async.

## 2. Cơ chế publish/subscribe của Spring có lưu lịch sử không?

`ApplicationEventPublisher.publishEvent(Object)` chuyển một object event vào cơ chế event publishing. `ApplicationContext` sử dụng `ApplicationEventMulticaster` để gửi tới những `ApplicationListener` phù hợp **đã được đăng ký và còn tồn tại trong context nhận event**.

Với một event dạng POJO/record:

~~~java
public record CatalogLoaded(String catalogName) { }

// Khi có một Spring-managed publisher:
publisher.publishEvent(new CatalogLoaded("country-codes"));
~~~

Spring có thể bọc payload trong `PayloadApplicationEvent` để vận chuyển nội bộ. Một bean với method:

~~~java
@EventListener
public void onCatalogLoaded(CatalogLoaded event) {
    // Xử lý sự thật CatalogLoaded.
}
~~~

sẽ được gọi khi method này đã được framework chuyển thành listener, được đăng ký, và event đang được phân phát trong context tương ứng.

Những đoạn trên là **mã minh họa trong một ứng dụng có Spring bean**, không phải chương trình Java độc lập; phần 6 có dự án hoàn chỉnh.

### Bốn mốc không được đánh đồng

| Mốc | Sự thật có thể khẳng định | Điều chưa thể khẳng định |
| --- | --- | --- |
| Producer gọi `publishEvent(event)` | Code đã yêu cầu Spring công bố event | Listener mong đợi đã có mặt |
| Multicaster chọn listener | Listener đã được đăng ký, loại event/điều kiện phù hợp | Handler đã hoàn tất thành công |
| Listener bắt đầu xử lý | Code handler đã được gọi | Side effect đã commit hoặc external API thành công |
| Listener hoàn tất | Hàm listener trả về/worker đã xong theo contract | Event được lưu bền vững hay có replay sau crash |

Trong dispatch **đồng bộ mặc định**, `publishEvent` thường chờ listener thông thường xử lý xong; nhưng việc không có listener phù hợp vẫn có thể dẫn đến **không có thao tác nào**, và lời gọi publish vẫn trả về bình thường. Trong dispatch bất đồng bộ, publisher còn có thể trả về trước khi handler chạy.

Vì vậy **không có exception khi publish** không đồng nghĩa “event đã đến đúng listener”.

## 3. Đăng ký listener trong vòng đời ApplicationContext

Spring Framework có hai mô hình quen thuộc:

1. Một bean hiện thực `ApplicationListener<E>`, hoặc một listener được thêm trực tiếp qua `ConfigurableApplicationContext.addApplicationListener(...)`.
2. Một phương thức trên bean được chú thích `@EventListener`; Spring phát hiện phương thức này và tạo adapter listener tương ứng.

Hai mô hình có điểm đăng ký trong quá trình refresh khác nhau.

### 3.1. Các mốc khởi động đáng quan tâm

Sơ đồ khái quát của `AbstractApplicationContext.refresh()` trong Spring Framework 6.2:

~~~text
prepareRefresh()
    |
    +-- bắt đầu vùng thu thập earlyApplicationEvents
    |
obtainFreshBeanFactory()
prepareBeanFactory()
invokeBeanFactoryPostProcessors()
registerBeanPostProcessors()
initMessageSource()
initApplicationEventMulticaster()
onRefresh()
registerListeners()
    |
    +-- thêm ApplicationListener đã biết
    +-- phân phát các early events đã được thu thập trong vùng bootstrap
    |
finishBeanFactoryInitialization()
    |
    +-- khởi tạo các regular singleton cần thiết
    +-- EventListenerMethodProcessor.afterSingletonsInstantiated()
        đăng ký phương thức @EventListener
    |
finishRefresh()
    |
    +-- publish(ContextRefreshedEvent)
~~~

Sơ đồ lược bỏ nhiều chi tiết nội bộ và chỉ dùng để giải thích **thứ tự tương đối**. Nó không phải API để application code tự gọi từng bước.

Theo Spring 6.2, `EventListenerMethodProcessor` là một `SmartInitializingSingleton`: nó đăng ký các phương thức `@EventListener` tại cuối giai đoạn pre-instantiation của singleton. Do đó nếu một bean khác publish event **rất sớm trong lúc khởi tạo singleton** (ví dụ constructor hoặc `@PostConstruct`), listener phương thức mong đợi có thể **chưa được đăng ký**, dù object bean chứa method đó sau này vẫn tồn tại.

### 3.2. ApplicationListener và @EventListener không có cùng thời điểm

| Cơ chế | Điểm liên quan | Đặc điểm quan trọng |
| --- | --- | --- |
| `context.addApplicationListener(listener)` **trước** `refresh()` | Listener được biết trước khi context phát refresh event | Thích hợp khi cần listener sớm của context |
| Bean hiện thực `ApplicationListener<E>` | Được `registerListeners()` khám phá như listener bean | Có thể có mặt sớm hơn phương thức `@EventListener` được xử lý |
| Method `@EventListener` trên regular bean | Được `EventListenerMethodProcessor` phát hiện trong bootstrap singleton | Không nên giả định đăng ký trước mọi `@PostConstruct` của bean khác |
| `context.addApplicationListener(listener)` **sau** `refresh()` | Được thêm ngay vào multicaster của context đang hoạt động | Nhận event **sau khi đăng ký**, không mặc định nhận lại event cũ |
| `@EventListener` trên lazy bean | Phụ thuộc lifecycle bean và phát hiện method | Spring cảnh báo không định nghĩa listener bean kiểu này là lazy khi mong được đăng ký chuẩn |

Một listener lập trình được thêm trước `refresh` có thể nhận `ContextRefreshedEvent` được phát ở cuối refresh. Cùng listener đó nếu chỉ được thêm **sau khi refresh trả về** sẽ không nhận lại `ContextRefreshedEvent` vừa được phát, trừ khi một refresh/event tương ứng khác thực sự xảy ra.

### 3.3. Early events không phải một queue bền vững

`AbstractApplicationContext` có thể tạm lưu một số event trong `earlyApplicationEvents` khi nó đang ở phần đầu của `refresh()`, trước khi hoàn tất đăng ký những listener ban đầu. Sau bước `registerListeners()`, các event tạm lưu được phân phát.

Điều **không** được suy ra:

- Không có event log kéo dài đến khi một bean `@EventListener` được khởi tạo nhiều phút sau.
- Không có replay tự động cho listener được thêm sau `refresh()`.
- Không bảo đảm event phát từ bất kỳ constructor/`@PostConstruct` nào đều đến mọi method `@EventListener`, vì thời điểm xử lý annotation có thể muộn hơn thời điểm buffer đã được flush.
- Không có đảm bảo bền vững sau restart, crash hoặc kill container.
- Không thay thế transactional outbox, persistent job storage hoặc broker có retention.

Lưu ý thêm: gọi `publishEvent` trên một `ApplicationContext` vừa tạo **nhưng chưa refresh** không phải một mẫu bootstrap được khuyến nghị. Multicaster có thể chưa được khởi tạo; không dùng `publishEvent` trước `refresh` như một “queue trước khi start” do ứng dụng tự chế.

## 4. Năm nguyên nhân thường khiến event xuất hiện trước listener

### 4.1. Publish trong constructor hoặc @PostConstruct

~~~java
@Component
class DataLoader {
    private final ApplicationEventPublisher publisher;

    DataLoader(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostConstruct
    void init() {
        publisher.publishEvent(new CatalogLoaded("country-codes"));
    }
}
~~~

Đây là mã **minh họa**, cần bean/type/import phù hợp. Nếu receiver sử dụng một method `@EventListener` khác, receiver đó có thể chưa được bộ xử lý annotation đăng ký tại thời điểm init. Code không nhất thiết ném lỗi; chỉ thấy thiếu phản ứng.

Cần đặc biệt tránh publish event quan trọng trong constructor: bean còn đang được xây dựng, các dependency/lifecycle khác có thể chưa hoàn tất, và event listener infrastructure chưa có trạng thái được kỳ vọng.

**Sửa theo contract:** chuyển công việc cần listener nhận sang sau khi bean infrastructure đã sẵn sàng, hoặc dùng phương thức trực tiếp khi thực sự cần bảo đảm một bước khởi tạo của chính use case.

### 4.2. Đăng ký listener muộn bằng code

~~~java
context.publishEvent(new CatalogLoaded("A"));
context.addApplicationListener(listener);
context.publishEvent(new CatalogLoaded("B"));
~~~

Nếu context đã hoạt động, listener mới được thêm **chỉ thấy event sau thời điểm đăng ký** theo cơ chế phân phát thông thường. Nó không tự nhìn thấy `CatalogLoaded("A")`. Đây là tình huống minh họa bằng demo có thể chạy ở phần 6.

### 4.3. Listener bean bị @Lazy hoặc chưa được đăng ký

Nếu bean chứa `@EventListener` không được framework phát hiện đúng vòng đời (ví dụ không thuộc context, định nghĩa lazy không phù hợp, sai component scan), method có thể không trở thành một listener đang hoạt động. Spring Framework Reference cảnh báo không khai báo listener bean với lazy initialization nếu muốn cơ chế đăng ký annotation-based diễn ra chuẩn.

Đây không phải lúc nào cũng là lỗi “event quá sớm”; đôi khi **listener chưa từng có mặt**. Khi chẩn đoán, phải kiểm tra **registration** trước khi trách producer.

### 4.4. Spring Boot phát event trước khi tạo context

Spring Boot có những startup event được `SpringApplication` phát **trước khi `ApplicationContext` tồn tại**. Ví dụ `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.

Một method `@EventListener` trên bean do context tạo **không thể** nghe các event đã xảy ra trước khi context/bean ấy được tạo. Tương tự, chỉ khai báo `@Bean ApplicationListener<ApplicationStartingEvent>` trong context là quá muộn để nhận event sớm đó.

Với Spring Boot, hãy đăng ký listener rất sớm bằng `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, hoặc cơ chế discovery qua `META-INF/spring.factories` theo phiên bản Boot đang dùng. Ví dụ ở mục 8 sẽ phân biệt với application event thông thường.

### 4.5. Tạo ApplicationContext con sau event của parent

Khi sử dụng hierarchy, sự kiện từ context con thường có thể được truyền lên context cha. Nhưng **context được tạo sau một event của context khác không tự nhận lịch sử event đó**. Đặt listener ở sai context cũng khiến producer và receiver không có đường truyền phù hợp.

Phân biệt:

- Event được phát trong context A nhưng listener ở context B **không nhận được do scope/hierarchy**.
- Listener nằm trong context A nhưng **được đăng ký sau event**.
- Listener ở parent có thể nhận event từ child theo cơ chế propagation, đôi khi dẫn đến **nhận nhiều lần** chứ không phải bỏ lỡ.

Không sửa mọi trường hợp bằng cách “đăng ký sớm hơn”; trước hết phải xác định **event được phát ở context nào**.

## 5. Dấu hiệu nhận biết “publish sớm” và cách loại trừ nguyên nhân khác

Một bảng chẩn đoán:

| Hiện tượng | Giả thuyết | Bằng chứng cần tìm |
| --- | --- | --- |
| Event phát trong `@PostConstruct`, handler không chạy | Listener method chưa được đăng ký | Log thời điểm init và sau refresh; thử publish lại sau refresh trong test |
| Publish sau refresh, thêm `ApplicationListener` muộn | Không replay event trước đăng ký | Test phát A trước add, phát B sau add |
| `@EventListener` bean không hề chạy | Bean không được scan/đăng ký hoặc lazy | Kiểm tra cấu hình tạo bean và framework event-method processing |
| `@TransactionalEventListener` không chạy | Không có transaction đang hoạt động, phase không khớp | Kiểm tra transaction boundary và `fallbackExecution` |
| Handler `@Async` không tạo side effect trước assert | Worker chưa hoàn tất | Chờ outcome bằng latch/future/await, không dựa vào sleep |
| Event là POJO nhưng listener nhận kiểu khác | Type/generic/condition mismatch | Kiểm tra runtime type và điều kiện `@EventListener(condition=...)` |
| Producer ở child, handler ở sibling | Context không có đường propagation phù hợp | Xác định context ID và parent chain |
| Event được phát nhưng consumer không nhận sau restart | Không có lịch sử bền vững | Kiểm tra outbox/broker/event store, không kỳ vọng ApplicationEventPublisher replay |
| Listener có log “START” nhưng không có “DONE” | Handler chạy rồi lỗi, không phải mất event | Kiểm tra exception/log/metrics và retry policy |

**Điều quan trọng:** “không nhìn thấy hiệu ứng của listener” không đồng nghĩa “listener chưa đăng ký”. Có thể handler được gọi rồi bị lỗi, điều kiện listener false, đang chờ async hoặc transaction-bound callback bị bỏ qua do không có transaction.

### 5.1. Một quy trình điều tra từ ngoài vào trong

1. **Ghi mốc publish:** event class, eventId, correlationId, timestamp, context ID, thread.
2. **Xác minh publisher:** lời gọi thực sự xảy ra, không bị guard `if`, exception hoặc nhánh code chặn.
3. **Xác minh context:** producer đang publish vào context nào; listener thuộc cùng context hay ancestor phù hợp?
4. **Xác minh listener được đăng ký:** bean tồn tại, không lazy ngoài ý định, processor đã hoàn tất, method đúng annotation/type.
5. **So sánh thời gian:** event đã được phân phát trước registration hay chưa? Đang trong giai đoạn refresh nào?
6. **Kiểm tra dispatch/transaction:** `@Async`, `@TransactionalEventListener`, condition, lỗi handler, `ErrorHandler`.
7. **Thử một event mới sau khi listener chắc chắn hoạt động:** nếu event mới nhận, khả năng lớn đây là vấn đề thời điểm.
8. **Kết luận nguyên nhân và sửa contract:** chọn đăng ký sớm, dời publication, state reconciliation hoặc durable delivery.

Không cần đọc toàn bộ codebase nếu có log đầy đủ các mốc và một test nhỏ tái hiện.

## 6. Ví dụ Java 17+ chạy được: event trước đăng ký bị bỏ lỡ

Ví dụ độc lập dùng Spring Framework 6.2.8, Java 17+ và Maven, không dùng Spring Boot hoặc database.

Nó chứng minh **ba hiện tượng**:

1. Context đã `refresh()` xong nhưng **chưa có listener** cho `DiagnosticSignal`. Publish event `"before"` không có người nhận.
2. Dùng `context.addApplicationListener(...)` đăng ký một listener **sau** lần publish đó. Publish `"after"` được nhận, nhưng event cũ không được replay.
3. Một bean có `@EventListener` được khai báo ngay từ đầu trong `Config` nhận `ReadySignal` phát **sau refresh**, xác nhận cơ chế annotation-based hoạt động khi đăng ký đúng vòng đời.

Đây là test có chủ đích để cô lập **registration timing**; không thử publish vào một context chưa refresh.

### 6.1. Cấu trúc dự án

~~~text
late-event-listener-demo/
├── pom.xml
└── src/main/java/LateListenerDemo.java
~~~

### 6.2. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>late-event-listener-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>LateListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. Tệp src/main/java/LateListenerDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class LateListenerDemo {

    public record DiagnosticSignal(String label) { }
    public record ReadySignal(String label) { }

    public static class ReadyListener {
        @EventListener
        public void onReady(ReadySignal event) {
            System.out.println(
                "ANNOTATED_RECEIVED=" + event.label()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ReadyListener readyListener() {
            return new ReadyListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.register(Config.class);
            context.refresh();

            // Chỉ có ReadyListener (nghe ReadySignal) được đăng ký.
            List<String> seenByLateListener = new ArrayList<>();
            System.out.println("CONTEXT_READY");

            // Không có ai nhận DiagnosticSignal lúc này.
            context.publishEvent(new DiagnosticSignal("before"));
            System.out.println(
                "BEFORE_COUNT=" + seenByLateListener.size()
            );

            // Đăng ký sau refresh: nhận event MỚI,
            // không tự phát lại event đã được publish.
            ApplicationListener<ApplicationEvent> lateListener =
                new ApplicationListener<ApplicationEvent>() {
                    @Override
                    public void onApplicationEvent(
                            ApplicationEvent event) {
                        if (event instanceof PayloadApplicationEvent<?> wrapped
                                && wrapped.getPayload()
                                   instanceof DiagnosticSignal signal) {
                            seenByLateListener.add(signal.label());
                            System.out.println(
                                "LATE_RECEIVED=" + signal.label()
                            );
                        }
                    }
                };

            context.addApplicationListener(lateListener);

            context.publishEvent(new DiagnosticSignal("after"));
            System.out.println(
                "AFTER_COUNT=" + seenByLateListener.size()
            );

            // @EventListener đã được đăng ký ở lúc context.refresh().
            context.publishEvent(new ReadySignal("after-refresh"));
            System.out.println("DONE");
        }
    }
}
~~~

Tại thư mục `late-event-listener-demo`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng **do chương trình tự in** theo thứ tự (không kể thông báo phụ của Maven):

~~~text
CONTEXT_READY
BEFORE_COUNT=0
LATE_RECEIVED=after
AFTER_COUNT=1
ANNOTATED_RECEIVED=after-refresh
DONE
~~~

### 6.4. Giải thích kết quả

**Trước khi thêm listener:** `context.refresh()` đã kết thúc, nhưng trong cấu hình chỉ có `ReadyListener` nhận `ReadySignal`; không có listener cho `DiagnosticSignal`. Gọi `context.publishEvent(new DiagnosticSignal("before"))` không làm list `seenByLateListener` tăng; in `BEFORE_COUNT=0`.

**Đăng ký listener muộn:** `context.addApplicationListener(lateListener)` đăng ký trực tiếp listener ở context đang hoạt động. Vì method event listener nhận `ApplicationEvent`, nó có thể quan sát các event framework; code chỉ xử lý những `PayloadApplicationEvent<?>` có payload là `DiagnosticSignal`. Sau khi phát `"after"`, listener in `LATE_RECEIVED=after`, list tăng thành một và `AFTER_COUNT=1`. Không có dòng `LATE_RECEIVED=before`, chứng minh **không có replay**.

**Phương thức @EventListener:** `ReadyListener` là bean non-lazy do `Config` định nghĩa từ đầu. Spring đăng ký method `onReady` trong refresh. Khi publish `ReadySignal("after-refresh")`, log `ANNOTATED_RECEIVED=after-refresh` xuất hiện.

**Vì sao không dùng @Async?** Để phân biệt lỗi đăng ký với lỗi chờ worker, ví dụ cố ý dùng dispatch đồng bộ mặc định. Chương trình không có thread race hay sleep, nên output dễ đối chiếu.

**Giới hạn minh họa:** ví dụ không nói rằng mọi event publish trong mọi phase `refresh` sẽ bị bỏ lỡ. Nó chứng minh trường hợp **một event đã được phân phát sau refresh nhưng trước khi listener mới được đăng ký**. Đây là tình huống đơn giản và nhất quán nhất để hiểu cơ chế.

### 6.5. Đổi thứ tự để sửa

Nếu ứng dụng có quyền đăng ký listener từ đầu, sửa theo thứ tự:

~~~java
// Với context phù hợp:
context.addApplicationListener(lateListener);
context.refresh();
context.publishEvent(new DiagnosticSignal("after-registration"));
~~~

Đây là **đoạn minh họa**, không copy nguyên xi vào chương trình trên mà không di chuyển lời khai báo `lateListener` và thiết lập context. Trong production, cấu hình đăng ký listener ở bootstrap thường tốt hơn việc cài đặt một listener động khi ứng dụng đã hoạt động.

Ngoài ra, thay một listener động bằng Spring bean `@EventListener` non-lazy được khai báo trong cấu hình ban đầu là lựa chọn phù hợp cho event **được phát sau refresh**.

## 7. @PostConstruct có phải nơi tốt để publish event bắt buộc không?

Thường **không**, nếu receiver dựa vào phương thức `@EventListener` chỉ được đăng ký sau khi các regular singleton đã được tạo. `@PostConstruct` chạy trong vòng đời tạo bean; ứng dụng không nên giả định rằng mọi event method khác đã đăng ký ở thời điểm đó.

Ví dụ có nguy cơ:

~~~java
@Component
public class BootstrapPublisher {

    private final ApplicationEventPublisher publisher;

    public BootstrapPublisher(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostConstruct
    public void init() {
        publisher.publishEvent(new CacheWarmupRequested("products"));
    }
}
~~~

Đây là snippet cần import `PostConstruct`, `Component`, `ApplicationEventPublisher` và định nghĩa `CacheWarmupRequested`. Nó **không bảo đảm** bean nhận `@EventListener(CacheWarmupRequested.class)` được đăng ký kịp.

**Hướng thay thế tùy mục tiêu:**

- Nếu bước khởi tạo là **bắt buộc và thuộc cùng use case**, gọi trực tiếp service chuẩn bị dữ liệu thay vì phụ thuộc một event listener chưa biết đã đăng ký.
- Nếu muốn một bước bắt đầu **khi context đã refresh xong**, dùng `@EventListener(ContextRefreshedEvent.class)` ở một bean đã khai báo đúng trong context; khi có context cha–con, lọc context nguồn.
- Nếu là ứng dụng **Spring Boot** và cần làm việc ở giai đoạn cuối startup, cân nhắc `ApplicationRunner`/`CommandLineRunner` hoặc `ApplicationReadyEvent` tùy hợp đồng readiness và thứ tự.
- Nếu chỉ cần chờ **toàn bộ singleton cơ bản được tạo**, `SmartInitializingSingleton` là một lifecycle callback có thể hữu ích, nhưng **không nên tự suy luận rằng mọi `@EventListener` khác đã được đăng ký trước một callback `SmartInitializingSingleton` của bạn**; `EventListenerMethodProcessor` cũng sử dụng callback loại này.
- Nếu sự kiện là **thông tin bắt buộc không được mất**, chuyển sang outbox/job store bền vững, không dựa vào dời annotation đơn thuần.

## 8. Spring Boot startup events: trước và sau ApplicationContext

Spring Boot bổ sung các sự kiện vòng đời của `SpringApplication`. Một số được phát **trước khi ApplicationContext tồn tại**, nên đăng ký listener thông qua bean annotation là quá muộn.

Sơ đồ mốc phổ biến trong Spring Boot:

~~~text
SpringApplication.run()
    |
    +-- ApplicationStartingEvent               [context chưa tạo]
    |
    +-- ApplicationEnvironmentPreparedEvent    [context chưa tạo]
    |
    +-- ApplicationContextInitializedEvent
    |
    +-- ApplicationPreparedEvent               [trước refresh]
    |
    +-- context.refresh()
    |     +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent                [sau refresh]
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent                  [sau runners]
~~~

Các sự kiện liveness/readiness và web server có thêm các mốc tương ứng; sơ đồ chỉ tập trung vào tình huống **listener được đăng ký quá muộn**.

### 8.1. Cách nghe event Boot sớm

Với `ApplicationStartingEvent`, đăng ký listener **trước khi gọi `run`**:

~~~java
// Minh họa ở lớp main của một Spring Boot application.
SpringApplication app = new SpringApplication(MyBootApp.class);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        System.out.println("Boot startup is beginning");
    }
);

app.run(args);
~~~

Đây là snippet của ứng dụng Spring Boot có dependency/import tương ứng; **không thuộc** dự án Spring Framework thuần ở phần 6. Listener kiểu này được biết bởi `SpringApplication` từ trước startup event nên có cơ hội nhận sự kiện sớm.

Một lựa chọn khác được Spring Boot ghi nhận là `SpringApplicationBuilder.listeners(...)` hoặc registration qua `META-INF/spring.factories` với khóa:

~~~properties
org.springframework.context.ApplicationListener=com.example.EarlyStartupListener
~~~

Listener sớm **không nên giả định đã có bean injection hay ApplicationContext đầy đủ**, vì mục tiêu của nó là chạy trong giai đoạn trước context.

### 8.2. Những event phát sau refresh

`ApplicationStartedEvent` thuộc Spring Boot xảy ra **sau refresh nhưng trước runners**; `ApplicationReadyEvent` xảy ra **sau runners**, gần mốc ứng dụng được xem là sẵn sàng theo quy trình Boot. Một bean `@EventListener` được Spring đăng ký bình thường có thể nghe những event phát sau refresh.

Tuy nhiên, không nên dùng `ApplicationReadyEvent` cho một công việc bắt buộc phải **kết thúc trước khi ứng dụng sẵn sàng** mà không thiết kế rõ chính sách blocking/readiness; listener kéo dài/async có thể thay đổi hành vi startup. Với công việc cần hoàn tất trước readiness, một `ApplicationRunner` đồng bộ có thể diễn đạt ý định rõ hơn.

**Không nhầm tên:** Spring Framework `ContextStartedEvent` chỉ được phát khi gọi `ApplicationContext.start()` theo cơ chế lifecycle, **không** có nghĩa tương đương Spring Boot `ApplicationStartedEvent`.

## 9. Nhiều nguyên nhân khác trông giống event bị bỏ lỡ

### 9.1. @TransactionalEventListener không có transaction

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderPlaced(OrderPlaced event) {
    // ...
}
~~~

`@TransactionalEventListener` mặc định chỉ chạy khi event được publish gắn với transaction tương ứng. Nếu gọi publisher **ngoài transaction**, listener có thể không thực thi (mặc định `fallbackExecution=false`), dù nó **đã được đăng ký từ trước**.

Muốn xử lý khi không có transaction, có thể chọn `fallbackExecution=true` khi thực sự phù hợp. Nhưng điều này thay đổi **hợp đồng nghiệp vụ**; không bật chỉ để “làm test xanh”. Với dữ liệu quan trọng cần commit, cần transaction thật hoặc outbox.

### 9.2. Event type hoặc generic không phù hợp

Một event dạng record:

~~~java
public record OrderPlaced(long orderId) { }
~~~

không phải subclass của một custom `ApplicationEvent` khác. Nếu listener khai báo kiểu không khớp, multicaster có thể lọc nó. Với `PayloadApplicationEvent<T>`, cần chú ý generic và cách Spring wrap payload; đơn giản nhất thường là method `@EventListener` nhận thẳng payload class `OrderPlaced`.

### 9.3. Condition false

~~~java
@EventListener(condition = "#event.urgent")
public void onAlert(AlertEvent event) {
    // ...
}
~~~

Đây là snippet minh họa; việc truy cập SpEL/property cụ thể còn phụ thuộc vào event và tên tham số. Nếu condition false hoặc biểu thức không phù hợp, method không chạy hoặc có lỗi biểu thức; đó không phải bằng chứng event đến trước registration. Khi cần, tạm bỏ condition trong một integration test tối giản để cô lập lỗi.

### 9.4. Async chưa hoàn tất

Với `@Async @EventListener`, handler có thể đã được schedule nhưng chưa chạy xong. Một assert ngay sau `publishEvent(...)` có thể thấy biến/list rỗng, rồi kết luận nhầm là event đã mất. Dùng `CountDownLatch`, future, một trạng thái kết quả hoặc công cụ await có timeout để kiểm tra outcome.

### 9.5. Listener thuộc context khác

Producer ở context child không tự broadcast tới sibling context. Spring có cơ chế đẩy một số event từ child lên parent, nhưng không đưa event từ parent xuống child theo cách đối xứng. Kiểm tra event source/context, parent chain và xem listener thực sự được đăng ký ở đâu.

### 9.6. Listener bị lỗi nhưng không có log quan sát

Một exception trong listener đồng bộ có thể propagate; nếu có `ErrorHandler` hoặc exception bị bắt/nuốt, publisher vẫn có thể trả về. Lỗi async thường đi qua cơ chế exception của worker. Trong cả hai trường hợp, việc không thấy side effect **không đủ** để kết luận event đến trước registration.

## 10. Bảng chọn giải pháp theo thời điểm và yêu cầu

| Tình huống | Giải pháp thường phù hợp | Vì sao |
| --- | --- | --- |
| Listener cần nhận `ContextRefreshedEvent` của lần refresh đầu | Đăng ký `ApplicationListener` trước `refresh`, hoặc bean `@EventListener` non-lazy được chuẩn bị đúng | Có mặt trước thời điểm context phát refresh |
| Event custom bị publish trong `@PostConstruct` | Dời publish sang sau refresh hoặc gọi service trực tiếp | Tránh phụ thuộc registration đang trong bootstrap |
| Phải nghe `ApplicationStartingEvent` của Boot | `SpringApplication.addListeners(...)` hoặc listener discovery sớm | Context bean chưa tồn tại |
| Component được thêm động vào context đang chạy | Chấp nhận chỉ nhận event tương lai; nếu cần lịch sử phải có storage | Event bus không replay quá khứ |
| Khởi tạo reference data bắt buộc | Runner đồng bộ, lifecycle hook phù hợp hoặc migration | Có hợp đồng hoàn tất/failed rõ hơn |
| Trạng thái hiện tại cần đồng bộ cho late subscriber | Gửi snapshot/state reconciliation khi đăng ký, sau đó nhận các change events | Không phụ thuộc sự kiện quá khứ |
| Event đã commit phải được giao đủ cho consumer | Transactional outbox + retry/idempotency | Bền vững qua crash và registration gap |
| Listener `AFTER_COMMIT` bỏ qua event | Kiểm tra transaction phase và fallback policy | Không phải mọi lần bỏ qua đều do đăng ký muộn |
| Listener async chưa cập nhật projection | Đợi outcome/monitor worker; kiểm tra executor | Có thể chưa chạy, không phải mất event |
| Multiple ApplicationContext | Chọn context đúng, kiểm tra hierarchy và filter source | Tránh vừa mất vừa nhận trùng |

### 10.1. Ưu tiên đồng bộ trạng thái hiện tại thay vì “phát lại tất cả”

Nếu listener mới chỉ cần **biết trạng thái hiện tại** (ví dụ cache danh mục tại lúc module được bật), một luồng **snapshot + change events** thường phù hợp hơn replay event history:

~~~text
Listener đăng ký
       |
       +--> tải snapshot dữ liệu hiện tại
       |
       +--> nhận change events tiếp theo
       |
       +--> reconcile với version/checkpoint
~~~

Tuy nhiên, nếu snapshot và listener registration diễn ra không nguyên tử, có thể có **race** giữa lúc đọc snapshot và bắt đầu nghe. Giải pháp production cần version/checkpoint, đăng ký trước rồi reconcile, hoặc transaction/snapshot mechanism phù hợp. Đừng thay lỗi “bỏ lỡ event trước registration” bằng một race khác lúc tải snapshot.

### 10.2. Khi thực sự cần mọi event: durable outbox

Giả sử `OrderPlaced` là fact quan trọng cho billing:

~~~text
T1 BEGIN
  save order
  insert outbox(eventId, aggregateId, type, payload)
T1 COMMIT
              |
              v
Outbox dispatcher / broker
              |
              v
Consumer đăng ký hoặc khởi động muộn
              |
              v
đọc từ offset/checkpoint + xử lý idempotent
~~~

Khi publisher commit, event outbox đã được lưu trong cùng transaction. Consumer có thể xử lý sau khi được khởi động lại, nếu log/queue còn giữ thông điệp theo retention/ack đúng. Cần dedup/idempotency vì delivery thường là at-least-once.

**Không nên chỉ tự gọi lại `publisher.publishEvent(...)` với event cũ** mà không biết trạng thái consumer, vì listener mới và listener cũ có thể cùng phản ứng, tạo side effect trùng như gửi email, charge payment hoặc giữ hàng.

## 11. Testing: kiểm tra timing thay vì dùng Thread.sleep

Một integration test tốt cần chứng minh **thời điểm đã có listener** so với **thời điểm publish**.

### 11.1. Ma trận trường hợp

| Test | Kỳ vọng |
| --- | --- |
| Publish khi context đã refresh nhưng chưa thêm listener động | Không có handler invocation cho event cũ |
| Add listener rồi publish event mới cùng type | Event mới được nhận đúng một lần |
| Đăng ký listener trước refresh | Listener có mặt khi `ContextRefreshedEvent` được phát |
| Bean `@EventListener` non-lazy trong config ban đầu | Nhận custom event publish sau refresh |
| Publish trong init callback trước khi method registration hoàn tất | Test phát hiện không được dựa vào delivery; chuyển mốc khi cần |
| Spring Boot listener sớm đăng ký trước `run` | Nhận Boot startup event trước context |
| Listener chỉ đăng ký như bean thường của Boot cho event sớm | Không mong nhận event đã xảy ra trước context |
| `@TransactionalEventListener` publish ngoài transaction | Mặc định không xử lý; phân biệt với registration gap |
| `@Async` xử lý chậm | Test chờ kết quả có timeout thay vì assert ngay |
| Event type khác với handler signature | Listener bị lọc, không coi là mất do timing |
| Context parent/child/sibling | Kiểm tra đường propagation và nguồn context |
| Retry/replay từ outbox sau consumer restart | Event ID nhất quán và idempotency hoạt động |

### 11.2. Test bằng counter/latch

Với listener đồng bộ, số invocation/counter có thể kiểm tra ngay sau `publishEvent`. Demo mục 6 dùng một `List<String>` và output xác định, không cần sleep.

Với listener async, sử dụng latch hoặc await utility có timeout; **không** viết:

~~~java
publisher.publishEvent(new CatalogLoaded("A"));
Thread.sleep(100);
assertEquals(1, handledCount.get());
~~~

Đây là **phản ví dụ**: scheduler, CI load và executor queue có thể khiến 100 ms không đủ, dẫn đến test flaky. Cách đúng là chờ một tín hiệu do handler phát ra rồi assert trạng thái.

### 11.3. Chú ý @RecordApplicationEvents

Spring TestContext hỗ trợ `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận event được publish **trong phạm vi test**. Nó hữu ích khi muốn chứng minh code đã publish event và lọc theo type. Tuy vậy:

- Event đã phát **trước lúc test bắt đầu ghi nhận** sẽ không tự xuất hiện trong danh sách test.
- Có event trong recorder **không đồng nghĩa** listener cụ thể đã xử lý thành công.
- Test recorder không phải event store của production.
- Nếu muốn kiểm tra listener, hãy đo kết quả thực của listener hoặc dùng một capturing listener.

Khi test lỗi thời điểm, đo **cả** publication lẫn consumption; chỉ assert số event recorder có thể bỏ qua nguyên nhân registration.

### 11.4. Không phụ thuộc thứ tự tạo bean ngẫu nhiên

Một test cố tình phát event trong constructor hoặc `@PostConstruct` có thể pass/fail khác nhau nếu bean creation order hoặc phụ thuộc thay đổi. Với tài liệu kiểm chứng “late listener không replay”, demo mục 6 cố tình **kiểm soát thứ tự**: refresh xong → publish A → đăng ký listener → publish B. Đây là mốc xác định và có thể lặp lại.

Nếu test thực tế cần bảo đảm bước bootstrap, hãy thay đổi kiến trúc để tạo một **hợp đồng mốc lifecycle rõ ràng**, không chỉ viết test cố định một thứ tự khởi tạo may rủi.

## 12. Logging và metrics để tìm event bị bỏ lỡ

Một chiến lược quan sát nên ghi lại các điểm:

~~~text
phase=publish    event=CatalogLoaded eventId=e1 context=app-1
phase=register   listener=CatalogListener  context=app-1
phase=handle     event=CatalogLoaded eventId=e2 listener=CatalogListener
phase=complete   event=CatalogLoaded eventId=e2 status=success
~~~

Ở log trên, `e1` xuất hiện **trước** dòng register và không có dòng handle; `e2` xuất hiện sau register và được xử lý. Đó là dấu vết phù hợp với giả thuyết timing. Nhưng cần xác nhận log ở cùng clock/context; distributed logs có thể bị lệch thứ tự timestamp.

Các trường log hữu ích:

- `eventId`, `eventType`, `aggregateId`, `correlationId`.
- `contextId`, `listenerName`, `listenerBeanName`.
- `startupPhase` hoặc mốc `refreshStarted/refreshCompleted`.
- `threadName`, `transactionPhase`, `isAsync`.
- `publishedAt`, `registeredAt`, `handledAt`.
- `success/failure/skipped` và error code.

Metric tự định nghĩa có thể gồm:

~~~text
app_event_published_total{eventType="CatalogLoaded"}
app_event_handled_total{listener="CatalogListener"}
app_listener_registered_total{type="CatalogLoaded"}
app_event_processing_errors_total{listener="CatalogListener"}
app_event_backlog{consumer="billing"}
~~~

Các tên trên là **gợi ý**, không phải metric có sẵn mặc định của Spring. Không dùng `eventId`/`orderId` làm label Prometheus vì tạo cardinality quá cao; để ID trong logs và traces.

### Bật log framework có kiểm soát

Trong môi trường chẩn đoán có thể tăng log cho `org.springframework.context.event` hoặc lifecycle của context, nhưng **không kỳ vọng framework tự log toàn bộ publisher/consumer của mọi custom event ở mức cấu hình đó**. Ở ứng dụng production nên bổ sung instrumentation ở điểm publish và handler, giới hạn payload, không log token/PII.

## 13. Lỗi phổ biến khi khắc phục

1. **Chỉ thêm @EventListener rồi mong nhận event cũ:** registration không làm lịch sử được replay.
2. **Chuyển listener thành @Lazy với hy vọng khởi tạo khi có event:** Spring cảnh báo lazy listener bean có thể không được đăng ký method.
3. **Gọi publishEvent trong constructor:** container và các bean khác chưa bảo đảm sẵn sàng.
4. **Publish trong @PostConstruct và tin mọi @EventListener đã có mặt:** phụ thuộc mốc đăng ký của `EventListenerMethodProcessor`.
5. **Dùng @DependsOn như một hệ thống replay:** phụ thuộc bean creation không phát lại event đã qua.
6. **Cho rằng earlyApplicationEvents là queue bền vững:** chỉ là bộ đệm bootstrap giới hạn.
7. **Bắt Spring Boot ApplicationStartingEvent bằng @Bean listener trong context:** context chưa tồn tại tại thời điểm event.
8. **Gọi publishEvent trước refresh trên context mới tạo như cách “xếp hàng”:** multicaster có thể chưa sẵn sàng.
9. **Nhầm @TransactionalEventListener không có transaction với registration gap:** listener có thể đã đăng ký nhưng không hợp phase.
10. **Nhầm @Async chưa hoàn tất với event bị mất:** cần chờ outcome.
11. **Không kiểm tra event type/generic/condition:** listener có mặt nhưng không match.
12. **Không kiểm tra parent-child context:** publish không tự truyền tới mọi context trong JVM.
13. **Kết luận publish thành công chỉ vì không exception:** không xác nhận có listener xử lý.
14. **Gọi lại event cũ tùy tiện:** có thể gây side effect trùng ở các listener đã nhận từ trước.
15. **Dùng in-memory queue làm bảo đảm delivery qua restart:** mất khi crash/process kill.
16. **Không có idempotency khi bật replay:** listener có thể thực thi cùng side effect nhiều lần.
17. **Dựa vào thứ tự bean creation ngẫu nhiên:** refactor/thêm dependency làm lỗi trở lại.
18. **Chỉ xem log publisher, không instrument handler/registration:** thiếu dữ liệu để xác định nguyên nhân.
19. **Test chỉ assert @RecordApplicationEvents có event:** chưa chứng minh handler chạy.
20. **Không định nghĩa event là fact hay command:** lỗi timing có thể che một workflow cần orchestration hoặc call trực tiếp.

## 14. Quy trình sửa lỗi theo mức độ tin cậy

### Cấp 1: đăng ký đúng và phát vào lúc hợp lý

Dùng khi event chỉ là thông báo nội bộ không bắt buộc lưu lịch sử:

1. Đưa listener vào context từ đầu; dùng `@EventListener` trên bean non-lazy hoặc `ApplicationListener` đăng ký trước refresh khi cần sớm.
2. Phát event khi context đã có listener; với bootstrap, chọn mốc sau refresh hoặc runner phù hợp.
3. Thêm integration test cho listener và publisher thật.
4. Ghi log publish/handle rõ ràng để kiểm tra các bản build sau.

### Cấp 2: state reconciliation cho subscriber vào muộn

Dùng khi listener mới cần **trạng thái hiện tại**, không cần từng fact lịch sử:

1. Subscriber đăng ký hoặc kích hoạt.
2. Đọc snapshot/state hiện tại với version phù hợp.
3. Áp dụng các change events theo checkpoint hoặc cơ chế chống race.
4. Dùng idempotency để không áp dụng trùng state transition.

Ví dụ: cache cấu hình theo tenant có thể tải snapshot từ DB trước khi phục vụ, rồi nhận event thay đổi; việc bỏ lỡ một `ConfigInitialized` cũ không còn làm cache thiếu vĩnh viễn.

### Cấp 3: bền vững hóa event nghiệp vụ

Dùng khi mỗi event có nghĩa vụ giao đến consumer, kể cả consumer chưa online:

1. Lưu state nghiệp vụ và outbox cùng transaction.
2. Dispatcher gửi event từ outbox/log theo chính sách retry và retention.
3. Consumer nhận event với event ID ổn định, checkpoint và idempotency.
4. Có dead-letter/quarantine, alert và khả năng replay chọn lọc.
5. Kiểm thử crash/restart, duplicate delivery và consumer đi vào muộn.

Khi đã ở cấp 3, **Spring ApplicationEventPublisher có thể vẫn dùng cho event nội bộ**, nhưng không phải thành phần duy nhất chịu trách nhiệm delivery.

## 15. Bài tập tự kiểm tra

1. Một listener được đăng ký sau `context.publishEvent(new CatalogLoaded("A"))`. Có tự nhận lại `A` không? Vì sao?
2. Vì sao việc gọi `@EventListener` trong bean không bảo đảm method sẵn sàng ngay lúc một bean khác chạy `@PostConstruct`?
3. `earlyApplicationEvents` trong `AbstractApplicationContext` có chức năng gì và giới hạn quan trọng nhất là gì?
4. Vì sao `ContextRefreshedEvent` là mốc phù hợp hơn constructor để phát một event cần listener theo cấu hình ban đầu?
5. Khi cần nghe `ApplicationStartingEvent` của Boot, nên dùng `@Bean ApplicationListener` trong context hay `SpringApplication.addListeners(...)`?
6. Trong demo, tại sao có `LATE_RECEIVED=after` nhưng không có `LATE_RECEIVED=before`?
7. Nếu bean `@EventListener` là lazy và không được đăng ký theo vòng đời kỳ vọng, có thể sửa bằng cách nào?
8. Nếu `@TransactionalEventListener(AFTER_COMMIT)` không chạy khi publish ngoài transaction, có phải do listener đăng ký muộn?
9. Tại sao một handler `@Async` có thể chưa có kết quả ngay sau `publishEvent` dù đã nhận event?
10. Khi listener mới chỉ cần cấu hình hiện tại, snapshot + version có lợi gì so với replay toàn bộ event cũ?
11. Nếu một domain event là nghĩa vụ nghiệp vụ không được mất, cần cơ chế gì ngoài event bus nội bộ?
12. Trong context hierarchy, event từ parent có mặc nhiên đi xuống mọi child không?
13. Khi test timing, vì sao thứ tự **refresh → publish A → register → publish B** đáng tin hơn phụ thuộc vào bean creation order?
14. Vì sao phát lại thủ công event cũ có thể tạo duplicate email hoặc thanh toán?
15. Sự khác biệt giữa “event được publish”, “listener chạy” và “side effect hoàn tất” là gì?

**Định hướng đáp án:** (1) không, event bus không tự replay lịch sử; (2) xử lý annotation diễn ra ở cuối giai đoạn singleton; (3) đệm một số early events trong refresh, không phải queue bền vững cho late subscriber; (4) đăng ký listener cơ bản đã hoàn tất trước mốc này; (5) `addListeners`; (6) listener chỉ được thêm sau event đầu; (7) dùng bean được phát hiện/khởi tạo đúng, không lazy ngoài ý định; (8) không, là điều kiện transaction phase; (9) worker chạy bất đồng bộ; (10) đồng bộ state hiện tại và chống race qua version; (11) transactional outbox/log + retry/idempotency; (12) không; (13) kiểm soát rõ các mốc; (14) một số consumer đã xử lý rồi; (15) ba tầng bảo đảm khác nhau.

## 16. Tổng kết

**“Event được phát trước khi listener đăng ký”** là lỗi về **thời điểm, phạm vi và hợp đồng delivery**, không chỉ là một thiếu sót annotation.

- Listener thêm sau khi event đã được phân phát **không tự nhận lại event cũ**.
- Trong `refresh()`, Spring có **early event buffering giới hạn** cho giai đoạn bootstrap, nhưng `@EventListener` method có thể được đăng ký ở một mốc muộn hơn.
- Event Boot phát trước khi context tồn tại cần listener đăng ký qua `SpringApplication` sớm, không dựa vào bean tạo sau đó.
- Muốn công việc chạy đúng một mốc startup, chọn lifecycle hook hoặc runner đúng ý định; đừng phụ thuộc `@PostConstruct` publish ngẫu nhiên.
- Muốn late subscriber biết state hiện tại, dùng snapshot/reconciliation có chống race.
- Muốn mọi event được giao dù crash, dùng storage/outbox và consumer idempotent; Spring event bus không cung cấp durable replay.
- Chẩn đoán phải phân biệt registration gap với `@TransactionalEventListener` phase, `@Async` delay, type mismatch, condition false hoặc context hierarchy.

## Tài liệu tham khảo

- Spring Framework 6.2 — *Application Events and Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2.8 Javadoc — *EventListenerMethodProcessor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot Reference — *Application Events and Listeners*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Source — *AbstractApplicationContext, earlyApplicationEvents/registerListeners*: https://github.com/spring-projects/spring-framework/blob/v6.2.8/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java
