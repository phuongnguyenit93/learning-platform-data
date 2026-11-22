# Refresh ApplicationContext và hoàn tất khởi tạo các thành phần cần thiết trong Spring Boot

**Phạm vi:** Spring Boot Application Runtime → Chuỗi khởi động. Bài viết giải thích cụ thể thời điểm `SpringApplication` refresh `ApplicationContext`, Spring xử lý bean definitions và tạo singleton, web runtime được khởi tạo như thế nào, các mốc sau refresh, cách đọc bằng chứng và xử lý lỗi startup. Các ví dụ chạy bằng **Java 17+**, **Spring Boot 3.3.x** và **Spring MVC**. Các mốc sự kiện, API và mặc định cần được đối chiếu với tài liệu phiên bản đang dùng nếu dự án chạy Spring Boot 4.x hoặc dòng khác.

## 1. Mục tiêu học tập và câu hỏi trọng tâm

Kết thúc bài, người học cần trả lời được:

1. `refresh()` là bước nào trong `SpringApplication.run()` và tại sao nó quan trọng?
2. Bean definition khác gì bean instance? Các `BeanFactoryPostProcessor` và `BeanPostProcessor` chạy ở giai đoạn nào?
3. Spring tạo bean, tiêm phụ thuộc, gọi `@PostConstruct`, `InitializingBean` và tạo proxy trước khi coi bean đã sẵn sàng như thế nào?
4. `finishBeanFactoryInitialization` và `finishRefresh` làm gì? Điều kiện nào khiến một bean chưa cần khởi tạo khi refresh kết thúc?
5. Vì sao `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationRunner` và `ApplicationReadyEvent` không đồng nghĩa?
6. Cách kiểm tra ứng dụng đã khởi tạo các thành phần thiết yếu và có thể phục vụ HTTP bằng log, sự kiện và response thực tế?
7. Khi refresh thất bại, phải đọc nguyên nhân từ đâu và điều gì **chưa** thể khẳng định về trạng thái ứng dụng?

**Ý chính:** `refresh()` biến một context đã chuẩn bị cấu hình thành một container hoạt động: hoàn thiện bean definitions, đăng ký cơ chế xử lý bean, tạo các singleton cần thiết, khởi động lifecycle infrastructure và công bố `ContextRefreshedEvent`. Sau đó Spring Boot vẫn còn các bước như phát `ApplicationStartedEvent`, chạy `ApplicationRunner`/`CommandLineRunner` và phát `ApplicationReadyEvent`. “Refresh xong” không phải “mọi thành phần có thể tồn tại đều đã được tạo”, cũng không tự chứng minh API nghiệp vụ trả dữ liệu đúng.

## 2. Refresh nằm ở đâu trong chuỗi khởi động?

Sơ đồ cho một lần chạy web app thành công:

~~~text
main(args)
  |
  v
SpringApplication.run(args)
  |
  +-- chuẩn bị Environment / cấu hình / profiles
  +-- chọn và tạo ConfigurableApplicationContext
  +-- áp dụng ApplicationContextInitializer
  +-- nạp cấu hình nguồn và đăng ký bean definitions ban đầu
  +-- ApplicationPreparedEvent (context chưa refresh)
  |
  +-- refreshContext(context)
  |      |
  |      +-- AbstractApplicationContext.refresh()
  |             +-- hoàn thiện các bean definitions
  |             +-- đăng ký BeanPostProcessor
  |             +-- chuẩn bị infrastructure của context
  |             +-- khởi tạo singleton không lazy
  |             +-- khởi động các lifecycle component liên quan
  |             +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent (refresh hoàn tất)
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  +-- readiness chuyển sang ACCEPTING_TRAFFIC (mặc định)
  |
  v
run() hoàn tất; app phục vụ request / xử lý công việc
~~~

Tên method và thứ tự nội bộ có thể khác một ít giữa các phiên bản, nhưng hợp đồng mức cao khá ổn định. Đối với Boot 3.3, `ApplicationStartedEvent` được phát sau khi context đã refresh và trước runner, còn `ApplicationReadyEvent` đến sau khi runner kết thúc. Một runner thất bại có thể khiến app **không bao giờ ready** dù context đã được refresh.

Nhiều ứng dụng servlet khởi tạo và bắt đầu web server nhúng trong tiến trình refresh. Vì vậy việc cổng HTTP có thể được mở ở một thời điểm trước event ready **không** cho phép giả định mọi tác vụ startup đã hoàn thành. Readiness được hiểu theo chính sách ứng dụng và nền tảng triển khai; kiểm tra status HTTP, dấu mốc ready và health/readiness khi cần.

## 3. Các giai đoạn cốt lõi trong AbstractApplicationContext.refresh()

`AbstractApplicationContext.refresh()` là thuật toán khuôn mẫu của Spring Framework. Bảng sau giúp liên hệ method với thành phần được hoàn thiện:

| Giai đoạn | Việc chính | Bằng chứng hoặc lỗi tiêu biểu |
|---|---|---|
| `prepareRefresh()` | Đánh dấu context đang chuẩn bị, kiểm tra/khởi tạo property sources | Cấu hình nguồn thiếu, context không thể khởi động |
| `obtainFreshBeanFactory()` | Tạo/chuẩn bị BeanFactory của context, gắn kho định nghĩa bean | Vấn đề cấu hình bean definitions |
| `prepareBeanFactory(...)` | Cài đặc tính chuẩn như ClassLoader, các processor hạ tầng | Các interface `Aware` và infrastructure hoạt động |
| `postProcessBeanFactory(...)` | Hook cho context subclass tùy chỉnh BeanFactory | Điều chỉnh registry/factory ở lớp triển khai |
| `invokeBeanFactoryPostProcessors(...)` | Cho phép biến đổi, bổ sung bean definitions trước khi tạo singleton ứng dụng | Parsing `@Configuration`, `@Bean`, `@ComponentScan`, `@Import` |
| `registerBeanPostProcessors(...)` | Đăng ký processor xử lý các bean instance khi được tạo | `@PostConstruct`, autowiring, proxy/AOP có điều kiện |
| `initMessageSource()` | Chuẩn bị nguồn message/i18n | `MessageSource` hoạt động |
| `initApplicationEventMulticaster()` | Chuẩn bị cơ chế phân phối application events | Listener nhận event đúng ngữ cảnh |
| `onRefresh()` | Điểm mở rộng đặc biệt theo context subclass, ví dụ chuẩn bị web server | Server servlet/reactive được thiết lập tùy context |
| `registerListeners()` | Đăng ký các listener bean và xử lý early events | Các listener bắt đầu tham gia dispatch |
| `finishBeanFactoryInitialization(...)` | Hoàn tất BeanFactory và pre-instantiate các singleton không lazy còn lại | Constructor, injection, init callbacks; lỗi tạo bean |
| `finishRefresh()` | Kích hoạt lifecycle processor, phát `ContextRefreshedEvent` và hoàn thành refresh | Marker context-refreshed xuất hiện |

Đây là trình tự khái quát để học; thực tế Boot áp dụng nhiều processor tự động trước khi tạo các bean ứng dụng. Không nên kết luận mỗi tên method tương ứng chính xác với một dòng log riêng, hoặc mọi bean chỉ có thể được tạo ở `finishBeanFactoryInitialization`. Những bean phục vụ hạ tầng như processor có thể phải khởi tạo **sớm hơn** để xử lý bean còn lại.

### 3.1. Bean definition không phải bean instance

**Bean definition** là metadata để container biết có thể tạo một bean: lớp/factory method, scope, phụ thuộc, lazy flag, điều kiện cấu hình, init/destroy callback. Nó có thể tồn tại trong registry **trước khi** đối tượng Java được tạo.

Ví dụ:

~~~java
@Configuration
class AppConfig {
    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGateway();
    }
}
~~~

Sau khi Spring xử lý cấu hình, registry có thể chứa definition cho `paymentGateway`. Khi container khởi tạo nó, `PaymentGateway` mới trở thành một bean instance. Đối với singleton không lazy, điều này thường xảy ra trong refresh. Nếu bean là lazy/prototype/request-scoped, instance có thể chỉ xuất hiện khi có nhu cầu phù hợp.

`@SpringBootApplication` gom các ý nghĩa cấu hình, component scan và auto-configuration. Auto-configuration dựa trên điều kiện classpath, properties, bean hiện có và các điều kiện khác; không nên hiểu là framework tự khởi tạo mọi thứ có trong thư viện.

### 3.2. BeanFactoryPostProcessor và BeanPostProcessor

Phân biệt hai điểm mở rộng:

- `BeanFactoryPostProcessor` làm việc với metadata/`BeanFactory` **trước khi** các application singleton thông thường được khởi tạo. Nó thích hợp để tác động definitions, không nên gọi `getBean(...)` tràn lan rồi vô tình tạo bean quá sớm.
- `BeanPostProcessor` chạy quanh quá trình tạo từng bean instance. Nó có thể thay đổi cách khởi tạo, gọi callback hoặc bao bọc đối tượng trong proxy. AOP/transaction và nhiều cơ chế annotation phụ thuộc hạ tầng post-processing.
- `BeanDefinitionRegistryPostProcessor` có bước làm việc trực tiếp với registry definitions; Spring sử dụng các processor hạ tầng để phân tích cấu hình Java và mở rộng các definition cần thiết.

Nếu tự định nghĩa `@Bean` trả về `BeanFactoryPostProcessor` hoặc `BeanPostProcessor` trong một class `@Configuration`, nên cân nhắc factory method `static` và return type đủ cụ thể để processor được nhận diện sớm. Sai thời điểm sẽ tạo ra hiện tượng bean khởi tạo sớm và không nhận đầy đủ post-processing.

### 3.3. Chu trình tạo một singleton thông thường

Mô hình cho **một** bean mới được container tạo:

~~~text
đọc BeanDefinition
    |
    v
chọn constructor / factory method -> tạo instance
    |
    v
tiêm dependency / property, gọi các Aware callback thích hợp
    |
    v
BeanPostProcessor.beforeInitialization(...)
    +-- @PostConstruct (thông qua processor tương ứng)
    |
    v
InitializingBean.afterPropertiesSet(), custom init method
    |
    v
BeanPostProcessor.afterInitialization(...)
    +-- có thể trả về proxy
    |
    v
bean sẵn sàng để các consumer sử dụng
~~~

Thứ tự này là sơ đồ điển hình; việc resolve phụ thuộc có thể khiến bean khác được khởi tạo trước. Proxy, circular dependency, factory bean và phương thức cấu hình đặc biệt có thể làm chu trình quan sát phức tạp hơn. `@PostConstruct` chạy **sau khi dependency được inject**, nhưng **trước khi toàn bộ application startup hoàn tất**. Không nên khởi động các quy trình tải dữ liệu dài hoặc điều phối request từ bên trong callback đó.

### 3.4. Hoàn tất singleton và lifecycle infrastructure

`finishBeanFactoryInitialization(...)` yêu cầu container pre-instantiate các singleton không lazy còn lại. Các callback thuộc `SmartInitializingSingleton` được gọi sau khi quá trình pre-instantiation singleton thường hoàn thành. Chúng hữu ích khi cần một tác vụ kiểm tra phụ thuộc vào những singleton đã được khởi tạo, nhưng **không** có nghĩa mọi lazy bean hoặc bean thuộc scope khác cũng đã tồn tại.

`finishRefresh()` hoàn tất refresh, kích hoạt `LifecycleProcessor` và phát `ContextRefreshedEvent`. Các bean triển khai `SmartLifecycle` có thể tự khởi động theo phase, rất hữu ích cho worker, listener, scheduler hoặc connection manager được quản lý bởi container. Khi tự triển khai, phải thiết kế start/stop nhất quán và tránh chặn startup vô thời hạn.

## 4. Ví dụ đầy đủ: ứng dụng quan sát refresh theo các mốc

### 4.1. Tạo project Java 17

Tạo project Maven bằng Spring Initializr với:

- Group: `com.example`
- Artifact: `refresh-lab`
- Package: `com.example.refreshlab`
- Java: **17**
- Spring Boot: **3.3.x**
- Dependencies: **Spring Web** và **Spring Boot Actuator**.

Giữ phiên bản starter/plugin mà Initializr sinh ra. Mẫu sử dụng servlet web runtime mặc định của `spring-boot-starter-web`. Cấu trúc phần code cần tạo:

~~~text
refresh-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/refreshlab/
    RefreshLabApplication.java
    ProbeService.java
    DeferredProbe.java
    ProbeController.java
    FailingInitProbe.java
  src/main/resources/application.properties
~~~

Đây là **một ứng dụng Spring Boot đầy đủ theo package**, các class dưới đây ở những file riêng trùng với public class; không dùng `javac` độc lập vì chúng cần dependency từ Maven. Lệnh thực tế để biên dịch/chạy là Maven Wrapper (`./mvnw` hoặc `./mvnw.cmd`), sau đó `java -jar` khi đã package.

### 4.2. Main class và marker của các sự kiện

`src/main/java/com/example/refreshlab/RefreshLabApplication.java`:

~~~java
package com.example.refreshlab;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RefreshLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RefreshLabApplication.class);

        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("LAB_APPLICATION_FAILED"));

        app.run(args);
    }

    @Bean
    static BeanFactoryPostProcessor definitionProbe() {
        return factory -> System.out.println(
                "LAB_DEFINITIONS_COUNT="
                        + factory.getBeanDefinitionCount());
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("LAB_RUNNER_DONE");
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

**Giải thích:**

- `setApplicationStartup(new BufferingApplicationStartup(2048))` ghi lại startup steps của Spring Boot vào bộ đệm; sẽ dùng Actuator `/actuator/startup` để quan sát. Không dùng buffer không giới hạn và không phơi endpoint này ra Internet công khai.
- `definitionProbe()` là `static @Bean` trả `BeanFactoryPostProcessor`; marker `LAB_DEFINITIONS_COUNT` ghi số bean definitions đang biết **ở thời điểm callback**, không phải tổng số bean object đã tạo. Con số thay đổi theo dependency và cấu hình.
- `ApplicationRunner` chỉ chạy sau khi context đã refresh và Boot phát `ApplicationStartedEvent`. Ở đây runner không ép các bean lazy được tạo sớm.
- `ContextRefreshedEvent` thuộc Spring Framework, còn `ApplicationStartedEvent` và `ApplicationReadyEvent` thuộc Spring Boot; đây là những mốc khác nhau.
- Listener `ApplicationFailedEvent` được đăng ký sớm trực tiếp lên `SpringApplication` nên có thể quan sát startup failure khi bean listeners trong context chưa được tạo xong. Mã chỉ in marker; stack trace thực do Boot in ra mới giúp tìm nguyên nhân lỗi.

### 4.3. Bean có constructor, PostConstruct và SmartInitializingSingleton

`src/main/java/com/example/refreshlab/ProbeService.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class ProbeService implements SmartInitializingSingleton {
    private final String label;

    public ProbeService(@Value("${lab.label:ready}") String label) {
        this.label = label;
        System.out.println("LAB_PROBE_CONSTRUCTOR");
    }

    @PostConstruct
    public void init() {
        System.out.println("LAB_PROBE_POST_CONSTRUCT");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_SINGLETONS_INSTANTIATED");
    }

    public String label() {
        return label;
    }
}
~~~

Constructor chạy khi bean được tạo; `@PostConstruct` chạy khi dependency và property injection cần thiết đã được thực hiện; callback `SmartInitializingSingleton` xảy ra sau giai đoạn khởi tạo các singleton không lazy. Vì vậy thứ tự **trong phạm vi các marker của bài lab** là:

~~~text
LAB_PROBE_CONSTRUCTOR
LAB_PROBE_POST_CONSTRUCT
LAB_SINGLETONS_INSTANTIATED
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

Có nhiều log khác xen kẽ. `LAB_DEFINITIONS_COUNT=<số>` cũng xuất hiện trước khi các singleton ứng dụng thông thường được tạo, nhưng giá trị số không cố định. Với một context đơn như bài này, mốc refresh được nhận một lần; hierarchy nhiều context có thể dẫn tới nhiều event và không nên suy từ việc thấy marker lặp thành hai lần startup của JVM.

### 4.4. Một bean cố tình lazy để minh họa điều chưa được tạo

`src/main/java/com/example/refreshlab/DeferredProbe.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class DeferredProbe {

    @PostConstruct
    public void init() {
        System.out.println("LAB_DEFERRED_INIT");
    }

    public String value() {
        return "deferred";
    }
}
~~~

Bean này được định nghĩa trong context nhưng không cần khởi tạo ở refresh vì `@Lazy`; client phải yêu cầu nó thì instance mới được tạo. Ta dùng `ObjectProvider` để tránh injection ép khởi tạo trong constructor của controller.

### 4.5. Controller chứng minh runtime đã sẵn sàng phục vụ

`src/main/java/com/example/refreshlab/ProbeController.java`:

~~~java
package com.example.refreshlab;

import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    private final ProbeService service;
    private final ObjectProvider<DeferredProbe> deferred;

    public ProbeController(
            ProbeService service,
            ObjectProvider<DeferredProbe> deferred) {
        this.service = service;
        this.deferred = deferred;
    }

    @GetMapping("/probe")
    public Map<String, String> probe() {
        return Map.of("status", service.label());
    }

    @GetMapping("/lazy")
    public Map<String, String> lazy() {
        return Map.of("status", deferred.getObject().value());
    }
}
~~~

`GET /probe` dùng singleton `ProbeService` đã khởi tạo; `GET /lazy` buộc `ObjectProvider` lấy instance `DeferredProbe`. Khi gọi `/lazy` lần đầu, console mới có `LAB_DEFERRED_INIT`. Những request tiếp theo sử dụng cùng singleton lazy đã được tạo, nên không có thêm marker init nếu app chỉ có một context.

### 4.6. Bean gây lỗi có điều kiện để thử refresh thất bại

`src/main/java/com/example/refreshlab/FailingInitProbe.java`:

~~~java
package com.example.refreshlab;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "lab.fail-on-init", havingValue = "true")
public class FailingInitProbe {

    @PostConstruct
    public void fail() {
        throw new IllegalStateException(
                "LAB_INTENTIONAL_STARTUP_FAILURE");
    }
}
~~~

Khi không truyền property `lab.fail-on-init=true`, bean này **không được đăng ký theo điều kiện tương ứng**. Khi bật cờ, singleton bean được tạo và callback ném exception có chủ đích; ứng dụng không thể hoàn tất refresh. Thí nghiệm sẽ giúp phân biệt startup failure với lỗi tại một HTTP request.

### 4.7. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=refresh-lab
server.port=8080
lab.label=ready
management.endpoints.web.exposure.include=health,startup
management.endpoint.health.show-details=never
~~~

Chỉ bật `startup` endpoint cho **lab nội bộ/local**. Actuator không tự mở mọi endpoint qua HTTP. Trong môi trường thật, đừng expose các endpoint vận hành chứa dữ liệu nhạy cảm khi chưa có kiểm soát truy cập và giới hạn mạng.

## 5. Chạy, đọc log và xác nhận chuỗi khởi tạo

### 5.1. Startup bằng Maven Wrapper

Trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Nếu chưa có quyền thực thi `mvnw` trên Unix, cấp quyền cho file wrapper trong project trước khi chạy, hoặc dùng `mvn spring-boot:run` khi Maven đã cài. Java và Maven phải dùng phiên bản JDK hỗ trợ project.

Trong console ứng dụng, chỉ lọc các dòng chứa `LAB_`. Không yêu cầu mọi log của Tomcat hoặc Spring xuất hiện theo một chuỗi hoàn toàn cố định. Một trích đoạn marker thành công là:

~~~text
LAB_DEFINITIONS_COUNT=<so_dinh_nghia>
LAB_PROBE_CONSTRUCTOR
LAB_PROBE_POST_CONSTRUCT
LAB_SINGLETONS_INSTANTIATED
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

`<so_dinh_nghia>` là **giá trị minh họa dạng mô tả**, không phải stdout nguyên văn; khi chạy thật nó được thay bằng một số nguyên. Các marker còn lại là chuỗi do mã Java in ra và thứ tự tương đối như trên là điều cần quan sát. `LAB_DEFERRED_INIT` chưa xuất hiện nếu chưa ai yêu cầu lazy bean.

**Cách đọc:** `ContextRefreshedEvent` chứng minh framework đã đi hết pha refresh; `ApplicationStartedEvent` chứng minh Boot đã nhận lại control sau refresh; runner hoàn thành trước ready event. Nếu chỉ thấy `LAB_CONTEXT_REFRESHED` mà chưa có `LAB_APPLICATION_READY`, đừng ghi nhận startup toàn bộ là thành công.

### 5.2. HTTP request thực tế

Mở terminal thứ hai:

~~~bash
curl -i "http://localhost:8080/probe"
curl -i "http://localhost:8080/actuator/health"
~~~

Với ứng dụng lab đang hoạt động bình thường, `GET /probe` có HTTP 200, body JSON tương đương:

~~~json
{"status":"ready"}
~~~

`GET /actuator/health` thông thường trả status `UP` trong môi trường lab không có dependency lỗi:

~~~json
{"status":"UP"}
~~~

Header, Content-Length, PID, port hiển thị trong log và duration phụ thuộc hệ thống; không dùng chúng làm kết quả cố định. `UP` chỉ là kết quả các health indicator đã đăng ký, không chứng minh mọi API trả dữ liệu nghiệp vụ hợp lệ.

Giờ gọi:

~~~bash
curl -i "http://localhost:8080/lazy"
curl -i "http://localhost:8080/lazy"
~~~

Cả hai lần thường trả:

~~~json
{"status":"deferred"}
~~~

Console xuất hiện `LAB_DEFERRED_INIT` **một lần**, ở thời điểm bean được yêu cầu lần đầu. Đây là bằng chứng trực tiếp chống lại suy luận “context refresh xong thì mọi bean đã được khởi tạo”. Nếu chạy cùng app với chế độ global lazy khác mặc định, một số mốc tạo bean có thể bị lùi đến request; hãy ghi lại option đang dùng khi so sánh.

### 5.3. Bằng chứng chi tiết từ startup endpoint

Vì main đã cấu hình `BufferingApplicationStartup` và Actuator exposure, gọi:

~~~bash
curl -i "http://localhost:8080/actuator/startup"
~~~

Phản hồi thành công thường chứa `timeline.events`, với các trường như `startupStep.name`, `startupStep.id`, `startTime`, `endTime`, `duration`, `tags`. Có thể gặp các bước liên quan `spring.context.refresh`, `spring.beans.instantiate`, xử lý bean post-processors hoặc công việc Boot khởi tạo. **Không hardcode** số lượng event, ID, duration hay thứ tự mọi event vì chúng biến đổi theo dependency và phiên bản.

Trong Boot 3.3, endpoint startup hỗ trợ GET lấy snapshot và POST tiêu thụ/drain dữ liệu trong buffer. Cho bài thực hành ưu tiên GET để quan sát mà không chủ động drain. Dữ liệu từ startup endpoint hữu ích để tìm bước chậm, nhưng không tự thay thế profiling, log lỗi hay thí nghiệm HTTP.

### 5.4. Chạy bằng file JAR

Dừng phiên Maven rồi chạy:

~~~bash
./mvnw clean package
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar
~~~

Với Windows sử dụng `./mvnw.cmd clean package`. Tên file JAR đúng khi artifact là `refresh-lab` và version mặc định `0.0.1-SNAPSHOT`; nếu version do Initializr hoặc dự án thay đổi, lấy tên thực tế trong `target/`. Nếu đổi code hoặc resources sau khi đóng gói, cần build lại JAR để chứa bản mới.

## 6. Hoàn tất khởi tạo không đồng nghĩa mọi bean đều tồn tại

Vào cuối refresh, container đã đáp ứng hợp đồng cho những singleton **không lazy** cần pre-instantiate và các thành phần hạ tầng thiết yếu, trong phạm vi các điều kiện cấu hình đang có hiệu lực. Song có các ngoại lệ quan trọng:

| Trường hợp | Có tạo instance ngay lúc refresh không? | Ý nghĩa khi kiểm tra |
|---|---|---|
| Singleton mặc định, không lazy | Thường có, trừ các cơ chế đặc biệt | Constructor/init failure thường khiến startup thất bại |
| Singleton `@Lazy` | Thường được trì hoãn cho tới lần sử dụng đầu | Lỗi init có thể xuất hiện lúc request |
| `@Scope("prototype")` | Khi có yêu cầu tạo đối tượng | Mỗi lần yêu cầu có thể tạo instance mới |
| `@RequestScope` | Theo từng HTTP request | Không thể kỳ vọng sẵn instance ở thời điểm ready |
| Bean theo `@ConditionalOnProperty` không khớp | Definition có thể bị loại bởi điều kiện | Không có instance là hành vi đúng của điều kiện |
| Bean bị ép eager bởi bean phụ thuộc | Có thể tạo sớm dù bản thân được đánh dấu lazy | Xem đồ thị dependency trước khi kết luận lazy không hoạt động |

`spring.main.lazy-initialization=true` có thể giảm thời gian startup bằng cách trì hoãn nhiều bean đến khi cần, nhưng có thể làm lỗi cấu hình xuất hiện muộn và khiến request đầu tiên chậm. Dự án production nên cân nhắc cùng readiness, cảnh báo lỗi sớm và warmup thay vì chỉ nhìn thời gian khởi động thấp hơn.

Nếu một bean lazy đóng vai trò **thật sự thiết yếu trước khi nhận traffic**, hãy quyết định rõ cơ chế chủ động khởi tạo/kiểm tra nó ở giai đoạn phù hợp (ví dụ runner có timeout hoặc health/readiness check phản ánh dependency), thay vì mặc định hy vọng nó đã được tạo.

## 7. Event khởi động, runner và readiness: các dấu mốc khác nhau

| Mốc | Thời điểm | Có thể kết luận | Chưa thể kết luận |
|---|---|---|---|
| `ApplicationPreparedEvent` | Context đã chuẩn bị trước refresh | Bean definitions nguồn đã được nạp để chuẩn bị refresh | Bean singleton đã init đầy đủ |
| `ContextRefreshedEvent` | Spring Framework hoàn thành refresh của một context | Context đã refresh và lifecycle hạ tầng kích hoạt | Các Boot runner đã xong |
| `ApplicationStartedEvent` | Boot sau refresh, trước runners | `SpringApplication` đã vượt qua refresh | App đã ready |
| `ApplicationRunner` / `CommandLineRunner` | Sau `ApplicationStartedEvent` | Logic hậu refresh đang thực thi | Mọi runner đã xong nếu chưa trả về |
| `ApplicationReadyEvent` | Sau các runner hoàn tất | Boot đi đến mốc ready của ứng dụng | Mọi request tương lai đúng |
| `AvailabilityChangeEvent` về `ReadinessState.ACCEPTING_TRAFFIC` | Sau ready event trong luồng mặc định | Trạng thái readiness được Boot công bố | Hệ thống ngoài đã cấp route và dependency nghiệp vụ luôn đúng |

Trong ứng dụng đơn giản, các event có thể cách nhau rất ít thời gian. Trong ứng dụng thật, runner thực hiện import metadata, kết nối, warmup hoặc kiểm tra tài nguyên có thể mất đáng kể. Đặt logic phù hợp đúng chặng giúp đánh giá readiness chính xác.

Spring Boot có thể công bố `LivenessState.CORRECT` sau `ApplicationStartedEvent` và `ReadinessState.ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent` trong luồng bình thường. Nếu tích hợp Kubernetes, việc probe nhận được trạng thái còn phụ thuộc endpoint probe, cổng, cấu hình và thời điểm kubelet gọi; chỉ log ready không thay thế test toàn đường đi.

**Lưu ý về listener:** event phát trước khi tạo context như `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` không thể được lắng nghe bằng một `@Bean` thông thường vì bean chưa tồn tại. Hãy đăng ký listener sớm qua `SpringApplication.addListeners(...)` khi cần. Các callback event theo mặc định thường chạy đồng bộ; không nên để logic quá dài chặn startup trong một listener.

## 8. Thí nghiệm chủ đích: refresh thất bại ở PostConstruct

Tắt instance đang phục vụ 8080. Sau khi build JAR, khởi động:

~~~bash
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar --lab.fail-on-init=true
~~~

Điều kiện của `FailingInitProbe` được thỏa, bean xuất hiện và `@PostConstruct` ném `IllegalStateException("LAB_INTENTIONAL_STARTUP_FAILURE")`. Kỳ vọng quan sát:

- Stack trace chứa chuỗi `LAB_INTENTIONAL_STARTUP_FAILURE`; lớp exception bao ngoài có thể là `BeanCreationException` do Spring đang tạo bean.
- Console có thể đã in `LAB_DEFINITIONS_COUNT` và một số marker bean khởi tạo trước khi lỗi xảy ra.
- Không đạt `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_DONE` hoặc `LAB_APPLICATION_READY` của lần chạy thất bại này.
- Listener sớm in `LAB_APPLICATION_FAILED` khi Boot phát failure event; boot process trả về exit status thất bại.
- Nếu servlet server đã được chuẩn bị một phần, Spring vẫn thực hiện rollback/cleanup theo cơ chế lỗi khởi tạo. Không kết luận server đang phục vụ chỉ từ vài dòng log tạo Tomcat.

**Cách chẩn đoán:** bắt đầu từ exception cuối, lần theo các phần `Caused by` để xác định bean, method khởi tạo và thông báo gốc. Thông báo chủ ý trong ví dụ là chứng cứ nguyên nhân. Khôi phục bằng cách chạy lại JAR **không truyền cờ** hoặc truyền `--lab.fail-on-init=false`. Không xóa hàng loạt bean hoặc vô hiệu hóa post-processing chỉ để ẩn stack trace.

**Đối chứng:** sau khi bỏ cờ lỗi, cùng artifact có thể đi hết các marker và trả 200 cho `/probe`. Sự khác biệt nằm ở một property điều khiển điều kiện bean, chứng minh fail trong refresh có thể phụ thuộc environment.

## 9. Thí nghiệm lazy initialization toàn ứng dụng

Tắt app cũ rồi chạy:

~~~bash
java -jar target/refresh-lab-0.0.1-SNAPSHOT.jar --spring.main.lazy-initialization=true
~~~

Chụp lại các marker xuất hiện trước request, sau `GET /probe` và sau `GET /lazy`. Không giữ kỳ vọng rằng mọi marker bean vẫn xuất hiện lúc startup như chế độ eager. Với global lazy, các bean không bị đòi hỏi bởi hạ tầng khởi động có thể chuyển việc init sang lần đầu truy cập. Sau đó so lại thời gian request đầu tiên, dấu mốc ready và những exception có thể bị hoãn.

**Kết luận đúng:** giảm khối lượng khởi tạo trong refresh không đồng nghĩa bỏ hoàn toàn việc khởi tạo; công việc chỉ chuyển thời điểm. Phải xem bean dependency và nhu cầu trước ready để quyết định có phù hợp với SLO khởi động và phản hồi đầu tiên hay không.

## 10. Quan sát các bean cần thiết và tránh khởi tạo bằng cách sai

Có ba câu hỏi nghiệp vụ phải trả lời trước khi chọn điểm khởi tạo:

1. Thành phần **cần để khởi động hệ thống** hay chỉ cần khi một tính năng được gọi? Nếu thiếu nó khiến ứng dụng vô dụng, hãy xác thực sớm trong startup hoặc readiness.
2. Công việc khởi tạo có phụ thuộc các bean khác đã sẵn sàng không? Constructor và `@PostConstruct` chỉ thích hợp để khởi tạo trạng thái nội bộ gọn; với thao tác liên bean sau khi toàn bộ singleton thông thường sẵn sàng, cân nhắc `SmartInitializingSingleton` hoặc `ContextRefreshedEvent`.
3. Công việc có thể chậm, có I/O hay thất bại tạm thời không? Cần timeout, retry hợp lý, telemetry và chính sách readiness. Không chôn một vòng lặp vô hạn trong `@PostConstruct` khiến startup không tiến lên.

**Những điểm móc phù hợp:**

- **Constructor / dependency injection:** thiết lập invariant đơn giản và tiếp nhận các dependency đã được container giải quyết.
- **`@PostConstruct`:** kiểm tra cấu hình nội bộ, chuẩn bị cấu trúc dữ liệu vừa phải. Nó chạy trong quá trình init bean; tránh truy cập ngược bean chưa ổn định hoặc thực hiện I/O dài.
- **`SmartInitializingSingleton.afterSingletonsInstantiated()`:** cần xử lý sau khi singleton không lazy đã được pre-instantiate; không mặc định áp dụng cho lazy/request/prototype.
- **`ContextRefreshedEvent`:** cần phản ứng khi một context refresh xong. Kiểm tra context đích trong hệ thống có parent/child context vì event có thể lan đến parent.
- **`ApplicationRunner` / `CommandLineRunner`:** công việc cấp ứng dụng sau refresh nhưng trước ready; failure ở đây có thể chặn mốc ready, dù refresh thành công.
- **`ApplicationReadyEvent`:** thông báo giai đoạn rất cuối của startup, phù hợp ghi nhận/audit nhẹ. Những công việc bắt buộc trước khi nhận traffic nên được đặt vào runner/readiness policy phù hợp thay vì hy vọng listener ready chạy xong trước khi có request.

Không cần tự gọi `context.refresh()` trong `@PostConstruct`, controller, hoặc runner của ứng dụng Boot. `SpringApplication` đã điều phối refresh đúng một lần trong startup tiêu chuẩn; gọi lại trên context không hỗ trợ nhiều lần có thể gây lỗi hoặc làm mất tính nhất quán.

## 11. Khi refresh lỗi: trách nhiệm phục hồi của container

Khi `refresh()` ném exception, Spring Framework cố gắng dừng các lifecycle component đã chạy, hủy các singleton đã tạo, hủy trạng thái refresh và truyền lỗi lên cho `SpringApplication`. Boot có thể phát `ApplicationFailedEvent` và kết thúc startup không thành công. Đây là **cleanup theo best effort**, không đồng nghĩa mọi kết nối/transaction ngoài hệ thống đã được phục hồi hoàn hảo.

Phân biệt các lớp nguyên nhân thường gặp:

| Tín hiệu | Pha nghi ngờ | Kiểm tra đầu tiên |
|---|---|---|
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | Resolve dependency khi tạo bean | Component scan, package, `@Bean`, `@Conditional...`, profile, kiểu bean |
| `BeanCreationException` + exception từ init | Constructor, inject, `@PostConstruct`, init-method | Dòng `Caused by` gốc, cấu hình và I/O ở callback |
| `BeanCurrentlyInCreationException` | Dependency cycle, thường giữa constructor dependencies | Sơ đồ phụ thuộc, tách trách nhiệm, bỏ vòng |
| `BindException` từ Spring Boot configuration binding | Bind `@ConfigurationProperties` | Tên property, kiểu dữ liệu, validation, nguồn config |
| Port already in use | Web server startup | `server.port` hiệu lực và listener trên cổng |
| `ApplicationStartedEvent` có, `ApplicationReadyEvent` không có | Sau refresh, runner hoặc bước hậu refresh lỗi | Exceptions trong runners, tác vụ hậu refresh |
| HTTP 404 sau ready | Routing/URL | `@RequestMapping`, context path, URL, method |
| HTTP 500 sau ready | Xử lý request | Stack trace controller/service tại request |
| `/actuator/health` trả `UP` nhưng API sai | Hành vi nghiệp vụ không được health indicator kiểm tra | Test response/body và dependency nghiệp vụ |

Không bật `spring.main.allow-circular-references=true` như phản xạ mặc định mỗi khi dependency cycle; sửa đồ thị bean mới giải quyết đúng nguyên nhân. Tương tự, đổi port có thể giải quyết xung đột port nhưng không giải quyết bean init failure; phải đối chiếu stack trace và mốc có/không có.

Nếu dùng `--debug` trong một lần chạy để xem condition evaluation report, lưu báo cáo cần thiết rồi tắt ở môi trường thông thường. Báo cáo điều kiện chỉ giải thích vì sao auto-configuration match/no-match, không phải bằng chứng tất cả bean instance đã hoạt động.

## 12. Những lỗi hiểu sai thường gặp

**Nhầm 1: “Đã có BeanDefinition nghĩa là bean đã sẵn sàng.”** Sai. Registry có metadata trước khi instance được tạo; lazy, request scope và conditional config thay đổi thời điểm hoặc điều kiện tạo object.

**Nhầm 2: “BeanFactoryPostProcessor và BeanPostProcessor làm cùng việc.”** Sai. Một loại can thiệp BeanFactory/definitions, loại kia can thiệp quá trình tạo bean instances. Cả hai có vị trí khác nhau trong refresh.

**Nhầm 3: “Mọi bean sinh ra đúng ở finishBeanFactoryInitialization.”** Sai. Một số processor và infrastructure bean phải xuất hiện trước; non-lazy application singleton còn lại mới được pre-instantiate ở giai đoạn này.

**Nhầm 4: “@PostConstruct chạy sau ApplicationReadyEvent.”** Sai cho singleton eager thông thường. Nó chạy trong quá trình bean được init, vốn thường diễn ra khi refresh, trước ready. Riêng lazy bean có thể init muộn, kể cả sau ready.

**Nhầm 5: “ContextRefreshedEvent chứng minh mọi runner chạy xong.”** Sai. Boot phát `ApplicationStartedEvent` sau refresh, rồi mới gọi runners, cuối cùng mới phát `ApplicationReadyEvent`.

**Nhầm 6: “Có HTTP listener là đã readiness.”** Không chắc. Embedded server có thể bắt đầu lắng nghe trước khi các hậu startup tasks hoàn thành; cần quyết định readiness theo hợp đồng hệ thống và xác nhận request thực tế.

**Nhầm 7: “Global lazy luôn là cách tối ưu startup an toàn.”** Nó chuyển chi phí sang first use, có thể đẩy exception sang request đầu và khiến latency tăng. Đo cả startup, first request, readiness và lỗi thực tế.

**Nhầm 8: “@PostConstruct nên kết nối mọi hệ thống ngoài và loop đến khi thành công.”** Callback dài/bị treo chặn init; ưu tiên timeout, chính sách retry có giới hạn và lifecycle thích hợp.

**Nhầm 9: “Nhìn thấy dòng Started Application có nghĩa request chắc chắn thành công.”** Dòng đó là dấu mốc framework, không thay thế kiểm thử route, auth, response body và các phụ thuộc.

**Nhầm 10: “Startup failure luôn có ApplicationFailedEvent listener đặt trong @Bean.”** Listener bean có thể chưa tồn tại nếu context chưa refresh; cần đăng ký sớm bằng `SpringApplication.addListeners(...)` khi muốn quan sát lỗi trước khi container sẵn sàng.

## 13. Kịch bản thực hành có tiêu chí nghiệm thu

Thực hành lần lượt và lưu một bảng bằng chứng như dưới đây:

| Thí nghiệm | Lệnh/trigger | Marker hoặc kết quả cần đối chiếu | Kết luận |
|---|---|---|---|
| Boot bình thường | `./mvnw spring-boot:run` | `LAB_CONTEXT_REFRESHED` trước `LAB_APPLICATION_STARTED`, runner trước ready | Phân biệt refresh và hậu refresh |
| Bean eager | Khởi chạy mặc định | Constructor → PostConstruct → SmartInitializingSingleton | Vòng đời bean singleton không lazy |
| HTTP hoạt động | `GET /probe` | 200 và `{"status":"ready"}` | Mapping và service hoạt động thực tế |
| Lazy bean | `GET /lazy` lần đầu | `LAB_DEFERRED_INIT` xuất hiện lần đầu ở request | Ready không đồng nghĩa mọi bean được tạo |
| Startup timeline | `GET /actuator/startup` | JSON timeline có các startup steps | Quan sát cost/giai đoạn bằng công cụ |
| Refresh thất bại | `--lab.fail-on-init=true` | Exception gốc; failure marker, không có ready | Init error chặn hoàn thành startup |
| Global lazy | `--spring.main.lazy-initialization=true` | Một số init marker dời sang lúc dùng | Tối ưu startup có trade-off |
| Hậu refresh lỗi | Cho runner ném lỗi trong một nhánh thử có kiểm soát | Refresh/started có thể có, ready không có | Runner error khác refresh error |

Chặng cuối là **bài mở rộng tự làm**: trong bản copy của lab, sửa `startupRunner()` thành:

~~~java
@Bean
ApplicationRunner startupRunner() {
    return args -> {
        System.out.println("LAB_RUNNER_BEGIN");
        throw new IllegalStateException("LAB_RUNNER_FAILURE");
    };
}
~~~

Snippet này **thay phương thức `startupRunner()` trong `RefreshLabApplication`**, không phải file Java hoàn chỉnh độc lập. Build và chạy lại trong một terminal thử nghiệm riêng. Kỳ vọng `LAB_CONTEXT_REFRESHED` và `LAB_APPLICATION_STARTED` có thể đã có; `LAB_APPLICATION_READY` không có vì runner thất bại. Phân biệt stack trace từ runner với lỗi `FailingInitProbe` nằm trong refresh. Sau thí nghiệm, khôi phục phương thức runner ban đầu trước khi làm các bài khác.

### Checklist nghiệm thu

- [ ] Dựng được project Java 17 / Spring Boot 3.3.x và chạy với Maven Wrapper.
- [ ] Mô tả đúng thứ tự các bước cốt lõi của `AbstractApplicationContext.refresh()` và vai trò BeanFactory.
- [ ] Phân biệt `BeanFactoryPostProcessor` với `BeanPostProcessor` và vòng đời `@PostConstruct`.
- [ ] Quan sát constructor, init callback, SmartInitializingSingleton và ContextRefreshedEvent trong log.
- [ ] Xác nhận `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` theo marker.
- [ ] Gọi `GET /probe` và `GET /lazy` để chứng minh endpoint và lazy initialization.
- [ ] Đọc `/actuator/startup` để tìm một startup step và giải thích timestamp/duration trong thực tế.
- [ ] Chủ động tạo một bean init failure và xác định nguyên nhân qua `Caused by`.
- [ ] Phân biệt refresh failure với runner failure sau refresh.
- [ ] Giải thích được giới hạn của kết luận “startup complete” khi có bean lazy hoặc dependency bên ngoài.

## 14. Tài liệu tra cứu

- Spring Framework 6.2, `AbstractApplicationContext` Javadoc (vòng đời `refresh()`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework, Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework, Container extension points: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework, Bean scopes: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html
- Spring Boot 3.3, SpringApplication và application events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3, Actuator endpoints và availability: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html

Với mọi tình huống thực tế, hãy viết **giả thuyết → vị trí trong chuỗi startup → lệnh kiểm tra → marker/stack trace/HTTP quan sát được → kết luận theo đúng phạm vi chứng cứ**. Đó là cách chứng minh context đã hoàn tất khởi tạo những thành phần cần thiết, đồng thời nhận diện những thành phần còn chờ được sử dụng hoặc được triển khai ở pha sau.