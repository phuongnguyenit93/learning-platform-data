# Khởi tạo singleton không trì hoãn và hoàn tất refresh

## Mục tiêu

Bài học thuộc **Spring Boot Application Runtime → Context và refresh**, tập trung vào thời điểm Spring tạo các bean singleton, ý nghĩa của bước `finishBeanFactoryInitialization(...)`, lúc `refresh()` thực sự hoàn tất và các callback được gọi trước/sau những mốc đó.

Sau bài này, bạn có thể:

1. Phân biệt **singleton scope**, **eager initialization** (khởi tạo không trì hoãn) và **lazy initialization** (khởi tạo trì hoãn).
2. Giải thích tại sao Spring thường tạo các singleton **non-lazy** trong quá trình `ApplicationContext.refresh()`, trước khi ứng dụng được báo ready.
3. Phân biệt `@PostConstruct`, `InitializingBean`, `SmartInitializingSingleton`, `ContextRefreshedEvent`, `ApplicationStartedEvent` và `ApplicationReadyEvent`.
4. Chạy ví dụ Spring Boot quan sát thứ tự khởi tạo singleton, hoàn tất refresh, tạo bean lazy theo yêu cầu và dọn dẹp khi context đóng.
5. Chẩn đoán lỗi startup, dependency kéo bean lazy tạo sớm, độ trễ khởi động và hiểu giới hạn của việc gọi `refresh()` lần nữa.

## 1. Singleton là phạm vi quản lý bean, không phải bảo đảm tạo sớm

Trong Spring Framework, scope `singleton` mặc định có nghĩa là **một thể hiện bean được quản lý cho mỗi bean definition trong một Spring container**. Nếu hai chỗ khác nhau nhận cùng một bean singleton từ cùng context, chúng thường nhận cùng đối tượng. Điều này không đồng nghĩa với singleton toàn JVM hoặc một class chỉ được phép có đúng một object trong mọi context.

Định nghĩa bean:

~~~java
@Component
public class PriceService {
}
~~~

Ví dụ trên minh họa một singleton mặc định **khi component được scan**. Nếu tạo hai `ApplicationContext` khác nhau, mỗi context có thể tạo một singleton `PriceService` riêng. Mặt khác, mã Java vẫn có thể tự tạo object không do Spring quản lý; singleton scope không cấm điều đó.

**Eager và lazy là hai chiến lược về thời điểm khởi tạo**, không thay đổi số lượng singleton được giữ trong một context:

| Đặc điểm | Singleton mặc định, non-lazy | Singleton với `@Lazy` |
| --- | --- | --- |
| Scope | `singleton` | Vẫn là `singleton` |
| Thời điểm thường được tạo | Trong `refresh()`, ở giai đoạn khởi tạo singleton không trì hoãn | Lúc bean thực sự được yêu cầu; có ngoại lệ do dependency hoặc hạ tầng |
| Số instance Spring quản lý cho bean definition | Thông thường một trong mỗi context | Thông thường một trong mỗi context |
| Lỗi trong constructor | Thường xuất hiện ngay lúc startup | Có thể xuất hiện muộn, lúc bean được yêu cầu |
| Hệ quả hiệu năng | Startup có thể lâu hơn; phát hiện lỗi sớm | Có thể rút ngắn startup nhưng lần gọi đầu có thêm độ trễ |

Lưu ý rằng bean scope `prototype` có hợp đồng khác: Spring tạo instance mới theo mỗi lần yêu cầu phù hợp; nó **không** thuộc tập singleton thường được tạo sẵn. Không nên gộp mọi loại scope vào một quy tắc khởi tạo chung.

## 2. Bước pre-instantiate singleton nằm ở đâu trong refresh?

Khi `SpringApplication.run(...)` khởi động Spring Boot, framework tạo `ApplicationContext` phù hợp, sau đó yêu cầu context thực hiện `refresh()`. Trong `AbstractApplicationContext.refresh()` có những mốc chính sau (lược bỏ chi tiết nội bộ để làm rõ thứ tự):

~~~text
SpringApplication.run(...)
  |
  +-- Chuẩn bị Environment, tạo ApplicationContext
  |
  +-- ApplicationContext.refresh()
       |
       +-- prepareRefresh()
       +-- obtainFreshBeanFactory()
       +-- prepareBeanFactory(...)
       +-- postProcessBeanFactory(...)
       +-- invokeBeanFactoryPostProcessors(...)
       +-- registerBeanPostProcessors(...)
       +-- initMessageSource()
       +-- initApplicationEventMulticaster()
       +-- onRefresh()                 (hạ tầng context cụ thể)
       +-- registerListeners()
       |
       +-- finishBeanFactoryInitialization(beanFactory)
       |    |
       |    +-- preInstantiateSingletons()
       |         +-- Tạo singleton đủ điều kiện, chưa tồn tại
       |         +-- Resolve dependency / injection
       |         +-- Chạy bean lifecycle khi khởi tạo
       |         +-- Gọi SmartInitializingSingleton callbacks
       |
       +-- finishRefresh()
            +-- Hoàn tất tác vụ refresh của context
            +-- Khởi động lifecycle processor/SmartLifecycle
            +-- Publish ContextRefreshedEvent
  |
  +-- Spring Boot: ApplicationStartedEvent
  +-- Spring Boot: ApplicationRunner / CommandLineRunner
  +-- Spring Boot: ApplicationReadyEvent
  |
  +-- run(...) trả về ConfigurableApplicationContext
~~~

Sơ đồ này phản ánh các **mốc chính của Spring Framework 6.1 và Spring Boot 3.3**, không phải một bản sao tất cả câu lệnh nguồn. Những context hoặc phần mở rộng cụ thể có thể thêm công việc riêng, và có thể có bean được tạo sớm hơn do hạ tầng hay quá trình xử lý bean definition.

Hai ý cần phân biệt:

- **`finishBeanFactoryInitialization(...)`**: Điểm Spring chuẩn bị xong phần khởi tạo các singleton không trì hoãn đủ điều kiện của BeanFactory, trong đó bước quan trọng là `preInstantiateSingletons()`. Tên phương thức **không** có nghĩa toàn bộ vòng đời refresh và Spring Boot startup đã xong.
- **`finishRefresh()`**: Mốc kết thúc phần refresh của `ApplicationContext`. Tại đây lifecycle processor được gọi và `ContextRefreshedEvent` được phát. Spring Boot còn tiếp tục xử lý các bước riêng (started event, runners, ready event) sau khi refresh hoàn tất.

Ở ứng dụng web, quá trình chuẩn bị embedded server có thể diễn ra khi refresh. **Server có thể lắng nghe trước `ApplicationReadyEvent`**; vì vậy một cổng HTTP mở không phải bằng chứng rằng tất cả startup runners đã xong hoặc instance đã ready nhận traffic theo chính sách vận hành.

## 3. Spring làm gì trong preInstantiateSingletons()?

Khi dùng `DefaultListableBeanFactory`, bước `preInstantiateSingletons()` làm việc với các bean definition đã đăng ký. Theo hợp đồng thông thường:

1. Xem các bean definition phù hợp, ưu tiên những bean **singleton và không lazy** chưa được tạo.
2. Yêu cầu tạo chúng thông qua cơ chế container. Việc này có thể kéo theo việc tạo bean dependency **trước** bean đang cần.
3. Bean trải qua constructor/factory method, dependency injection, callbacks Aware và BeanPostProcessor, lifecycle initialization.
4. Sau giai đoạn chuẩn bị singleton thông thường, gọi callback `afterSingletonsInstantiated()` của những bean quản lý có triển khai `SmartInitializingSingleton`.

Không nên hiểu `preInstantiateSingletons()` là vòng lặp tạo đối tượng bằng `new` theo đúng thứ tự source code. Container còn xử lý bean definitions, phụ thuộc, post-processor, factory method, scope và proxy. Một số bean hạ tầng được tạo sớm hơn để phục vụ chính quá trình bootstrap.

### Quy tắc cần nhớ

- Singleton **non-lazy** có thể được tạo trong lúc refresh ngay cả khi chưa có HTTP request và chưa có class nào gọi service đó từ logic nghiệp vụ.
- Một bean **lazy** vẫn có thể được tạo trong refresh khi một singleton non-lazy yêu cầu trực tiếp nó qua constructor hoặc factory method. `@Lazy` **không** bảo đảm bean chắc chắn vắng mặt ở cuối startup.
- Một số trường hợp `FactoryBean` có quy tắc riêng; factory và object mà factory tạo ra không phải lúc nào cũng có cùng thời điểm khởi tạo. Không suy diễn tất cả bean từ ví dụ giản lược.
- `preInstantiateSingletons()` không khởi tạo trước **mọi** prototype hoặc mọi singleton lazy chưa được yêu cầu.
- Khi còn một bean non-lazy có constructor lỗi hoặc dependency không thỏa mãn, startup thường thất bại ngay tại refresh. Đây là một lợi ích của kiểm tra sớm, bên cạnh chi phí startup.

## 4. Thứ tự lifecycle ở cấp một bean

Xét bean singleton thông thường có dependency hợp lệ và được tạo dưới sự quản lý của container:

~~~text
Tạo instance (constructor hoặc @Bean factory method)
  |
  +-- Dependency injection / Aware callbacks
  +-- BeanPostProcessor trước initialization
  |    +-- @PostConstruct thường được xử lý trong giai đoạn này
  |
  +-- InitializingBean.afterPropertiesSet() (nếu có)
  +-- custom init method (nếu khai báo)
  +-- BeanPostProcessor sau initialization
  |
  +-- Bean sẵn sàng được lấy từ context
~~~

Nếu bean triển khai `SmartInitializingSingleton`, `afterSingletonsInstantiated()` được gọi ở mốc riêng **sau** bước pre-instantiate các singleton thông thường, chứ không phải cùng lúc constructor của chính bean đó hoàn tất.

| Hook | Thời điểm, phạm vi | Dùng cho |
| --- | --- | --- |
| Constructor / factory method | Khi tạo **một bean** | Thiết lập state hợp lệ, kiểm tra đối số cơ bản |
| `@PostConstruct` | Trong initialization của **bean đó** | Kiểm tra/lắp ráp tài nguyên cục bộ đã được inject |
| `InitializingBean.afterPropertiesSet()` | Sau khi thuộc tính được thiết lập cho **bean đó** | Xác thực/hoàn tất initialization có phụ thuộc Spring API |
| Custom `initMethod` | Giai đoạn initialization của **bean đó** | Logic init không buộc lớp triển khai Spring interface |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau pre-instantiate các singleton không trì hoãn | Logic cần chờ pha khởi tạo singleton thông thường hoàn tất |
| `ContextRefreshedEvent` | Khi **ApplicationContext** hoàn tất refresh | Quan sát một lần refresh hoàn thành |
| `ApplicationStartedEvent` | Spring Boot: sau refresh, trước runners | Quan sát trạng thái đã startup theo mốc Boot |
| `ApplicationRunner`, `CommandLineRunner` | Sau `ApplicationStartedEvent`, trước ready | Thực hiện tác vụ khởi động của ứng dụng |
| `ApplicationReadyEvent` | Sau runners, khi Boot đã tiến tới trạng thái ready | Quan sát mốc ứng dụng sẵn sàng |

**Lưu ý:** `@PostConstruct` của bean A **không bảo đảm** tất cả bean B, C, D trong context đã tạo xong. Nếu A cần B, injection làm B được giải quyết theo quy tắc dependency; còn các singleton không liên quan có thể chưa được khởi tạo. Dùng `SmartInitializingSingleton` hoặc sự kiện đúng mốc khi yêu cầu là chờ một giai đoạn tổng thể.

`SmartInitializingSingleton` là callback của *những bean được tạo trong giai đoạn pre-instantiate*; nó không có nghĩa tất cả singleton lazy đều được tạo rồi. Một `SmartInitializingSingleton` bản thân bị lazy và chưa bao giờ được tạo trước refresh sẽ không tự động nhận callback cho lần tạo muộn như một cách “chạy lại toàn bộ pre-instantiate”.

## 5. Ví dụ hoàn chỉnh: quan sát eager, refresh và lazy

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13** và Gradle. Chỉ sử dụng `spring-boot-starter` nên là ứng dụng **non-web**; nó không mở cổng HTTP và tự đóng context sau phần thí nghiệm.

### 5.1. Cấu trúc

~~~text
singleton-refresh-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/refresh/RefreshLifecycleApplication.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'singleton-refresh-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.refresh.RefreshLifecycleApplication'
}
~~~

Tệp `src/main/java/com/example/refresh/RefreshLifecycleApplication.java`:

~~~java
package com.example.refresh;

import java.util.Locale;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RefreshLifecycleApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(RefreshLifecycleApplication.class, args)) {

            System.out.println("MAIN: run returned");

            // Đến đây refresh và các Boot startup callbacks đã xong.
            // Yêu cầu bean lazy lần đầu mới kích hoạt khởi tạo nó.
            LazyParser parser = context.getBean(LazyParser.class);
            System.out.println("MAIN: parsed=" + parser.parse("ab"));
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    EagerCatalog eagerCatalog() {
        return new EagerCatalog();
    }

    @Bean
    @Lazy
    LazyParser lazyParser() {
        return new LazyParser();
    }

    @Bean
    SmartInitializingSingleton allNonLazySingletonsReady(EagerCatalog catalog) {
        // Phụ thuộc EagerCatalog bảo đảm bean đó đã tồn tại.
        return () -> System.out.println(
                "CALLBACK: afterSingletonsInstantiated");
    }

    @EventListener(ContextRefreshedEvent.class)
    void afterContextRefresh() {
        System.out.println("EVENT: ContextRefreshedEvent");
    }

    @EventListener(ApplicationStartedEvent.class)
    void afterBootStarted() {
        System.out.println("EVENT: ApplicationStartedEvent");
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterBootReady() {
        System.out.println("EVENT: ApplicationReadyEvent");
    }

    static final class EagerCatalog {
        EagerCatalog() {
            System.out.println("BEAN: EagerCatalog created");
        }

        @PreDestroy
        public void destroy() {
            System.out.println("BEAN: EagerCatalog destroyed");
        }
    }

    static final class LazyParser {
        LazyParser() {
            System.out.println("BEAN: LazyParser created");
        }

        String parse(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

**Vì sao là chương trình đầy đủ?** Nó có lớp `@SpringBootApplication`, một `main`, Gradle dependencies, bean eager, bean lazy, callback lifecycle, class phụ trợ và lời gọi `getBean` thật. Trong cùng package nguồn, không cần thêm file Java hay server web.

### 5.2. Chạy

Từ thư mục `singleton-refresh-demo`:

~~~bash
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. Bản Gradle sử dụng phải tương thích với Spring Boot 3.3 và Java được cài đặt.

Bỏ qua log của Spring Boot, **các dòng do chương trình tự in** có thứ tự kỳ vọng:

~~~text
BEAN: EagerCatalog created
CALLBACK: afterSingletonsInstantiated
EVENT: ContextRefreshedEvent
EVENT: ApplicationStartedEvent
EVENT: ApplicationReadyEvent
MAIN: run returned
BEAN: LazyParser created
MAIN: parsed=AB
BEAN: EagerCatalog destroyed
MAIN: context closed
~~~

Thứ tự các dòng phía trên thể hiện hợp đồng lifecycle cho cấu hình demo; các log và dòng output khác của build/runtime có thể xen giữa. Thứ tự khởi tạo các bean **không liên quan** trong một dự án lớn không nhất thiết có thứ tự cố định giống một danh sách khai báo.

### 5.3. Phân tích từng mốc

**Mốc 1 — `EagerCatalog` được tạo trước khi `run` trả về**

Không có HTTP request và `main` cũng chưa gọi `getBean(EagerCatalog.class)`. Singleton này vẫn được tạo vì mặc định là non-lazy; hơn nữa callback `allNonLazySingletonsReady` nhận nó làm dependency, nên container phải giải quyết nó trước.

**Mốc 2 — `SmartInitializingSingleton` được gọi sau giai đoạn khởi tạo singleton**

Dòng `CALLBACK: afterSingletonsInstantiated` phát ra từ lambda bean triển khai `SmartInitializingSingleton`. Nó chạy sau pha pre-instantiate các singleton không lazy, nhưng **không** bắt `LazyParser` phải tạo. Điều này là căn cứ để lựa chọn callback khi cần thao tác phụ thuộc việc các singleton bình thường đã khởi tạo xong.

**Mốc 3 — Context refreshed trước các mốc Boot started/ready**

`ContextRefreshedEvent` được phát trong `finishRefresh()`. Sau khi `refresh` trở về thành công, Spring Boot phát `ApplicationStartedEvent`, thực hiện các startup runners (nếu có), rồi phát `ApplicationReadyEvent`. Demo không có runner; sự khác nhau giữa hai sự kiện vẫn quan trọng khi thêm runner về sau.

**Mốc 4 — `SpringApplication.run` trả về và bean lazy vẫn chưa có**

`MAIN: run returned` xuất hiện sau các mốc above. Khi `context.getBean(LazyParser.class)` được gọi, Spring mới phải khởi tạo singleton lazy đang chưa có; constructor in `BEAN: LazyParser created`, và phương thức `parse("ab")` trả `AB`.

**Mốc 5 — Đóng context không giống kết thúc một request**

`try-with-resources` gọi `context.close()` sau các thao tác chính. Bean `EagerCatalog` có `@PreDestroy` nên được dọn dẹp; sau đó chương trình in `MAIN: context closed`. Đây là ví dụ CLI chủ động đóng context; trong một ứng dụng web chạy dài hạn, không đóng context ngay khi startup xong.

### 5.4. Thử nghiệm thay đổi

Không sửa ví dụ chính cùng lúc theo nhiều hướng; thử từng biến thể riêng và chạy lại ứng dụng:

1. **Bỏ `@Lazy` ở phương thức `lazyParser`.** Kỳ vọng `LazyParser` được tạo trong refresh, trước dòng `MAIN: run returned`.
2. **Giữ `@Lazy` nhưng gọi `context.getBean(LazyParser.class)` hai lần.** Hai lần lấy trong cùng context cho cùng bean definition vẫn trả về cùng một singleton; constructor không chạy hai lần.
3. **Thêm bean singleton non-lazy có constructor injection của `LazyParser`.** Lúc này dependency có thể khiến `LazyParser` được tạo ngay trong refresh, dù nó mang annotation `@Lazy`.
4. **Cho constructor của `EagerCatalog` ném exception.** Startup bị hủy trước khi ready; xem log về bean creation failure. Đừng giữ lỗi này trong bản demo hoạt động bình thường.
5. **Thêm `ApplicationRunner` có log.** Xác nhận runner chạy **sau** `ApplicationStartedEvent` và **trước** `ApplicationReadyEvent`.
6. **Bật global lazy initialization rồi chạy lại.** Quan sát những bean nào bị hoãn và những thành phần hạ tầng nào vẫn được tạo sớm. Không dự đoán toàn bộ callback vẫn diễn ra giống y hệt khi thay cấu hình global.

## 6. @Lazy: những tình huống dễ hiểu sai

### @Lazy ở bean definition

~~~java
@Bean
@Lazy
ReportEngine reportEngine() {
    return new ReportEngine();
}
~~~

Đoạn trên là **minh họa**, giả định có lớp `ReportEngine` và import `@Bean`/`@Lazy`. Spring chưa cần xây dựng `ReportEngine` cho pha non-lazy pre-instantiation nếu không ai yêu cầu nó sớm.

### Dependency non-lazy làm bean lazy được tạo sớm

~~~java
@Component
final class StartupService {

    private final ReportEngine reportEngine;

    StartupService(ReportEngine reportEngine) {
        this.reportEngine = reportEngine;
    }
}
~~~

Nếu `StartupService` là singleton non-lazy và Spring phải inject trực tiếp `ReportEngine` khi tạo nó, bean `ReportEngine` sẽ được giải quyết, kể cả khi bean definition của nó được đánh dấu lazy. Vì vậy **chỉ dán `@Lazy` lên bean không bảo đảm nó được hoãn**.

Đây là đoạn minh họa có các import/type tương ứng trong một dự án đầy đủ; **không** thêm `StartupService` vào chương trình mục 5 khi muốn giữ `LazyParser` chưa tạo trước `getBean`.

### Sử dụng ObjectProvider khi thực sự muốn lấy bean theo nhu cầu

~~~java
@Component
final class ReportControllerSupport {

    private final ObjectProvider<ReportEngine> engine;

    ReportControllerSupport(ObjectProvider<ReportEngine> engine) {
        this.engine = engine;
    }

    String generateReport() {
        return engine.getObject().render();
    }
}
~~~

Đoạn trên **minh họa một phần**, cần lớp `ReportEngine` có `render()`, các import và project tương ứng. `ObjectProvider` cho phép trì hoãn *việc lấy instance* đến `getObject()`; một bean khác vẫn có thể yêu cầu `ReportEngine` sớm, nên kết quả không phải cam kết tuyệt đối rằng bean chưa bao giờ được tạo trước đó.

Có thể sử dụng `@Lazy` tại injection point để nhận proxy trì hoãn việc giải quyết dependency trong những trường hợp phù hợp. Cần hiểu hiệu ứng của proxy và phương thức thực sự kích hoạt target, thay vì dùng nó để che lỗi circular dependency.

### Global lazy initialization

Spring Boot hỗ trợ:

~~~properties
spring.main.lazy-initialization=true
~~~

Hoặc cấu hình sớm trong code `SpringApplication` tương ứng. Global lazy có thể giúp startup nhanh hơn, nhưng làm một số lỗi cấu hình hoặc kết nối chỉ xuất hiện ở request/tác vụ đầu tiên. Các bean infrastructure, listener hoặc dependency được yêu cầu trong quá trình khởi động vẫn có thể khởi tạo sớm. **Không suy luận rằng tất cả bean đều chắc chắn lazy**, cũng không nên bật chỉ để che lỗi startup.

## 7. Vì sao @PostConstruct không thay thế SmartInitializingSingleton?

Giả sử một bean `CatalogIndex` có `@PostConstruct` và muốn tìm tất cả bean `ProductHandler`.

Trong `@PostConstruct`, **chính `CatalogIndex`** đang hoàn tất initialization, nhưng những singleton **không có quan hệ dependency** có thể chưa được Spring tạo. Nếu tác vụ cần chạy sau giai đoạn toàn bộ singleton non-lazy được pre-instantiate, `SmartInitializingSingleton` là hook sát nghĩa hơn:

~~~java
@Component
final class CatalogIndex implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Hợp lý cho bước kiểm tra/tổng hợp sau pha pre-instantiate.
        // Không suy ra các singleton lazy đều đã được tạo.
    }
}
~~~

Đây là một **đoạn minh họa**, không phải class dùng trực tiếp cùng ví dụ ở mục 5; cần các import `Component` và `SmartInitializingSingleton`.

Cần nhớ ba lớp mốc:

- **Bean ready:** Các bước initialization của một bean hoàn tất.
- **Non-lazy singleton pre-instantiation complete:** Spring đã xử lý pha singleton thường trong `finishBeanFactoryInitialization` và gọi callbacks `SmartInitializingSingleton`.
- **Context refreshed / Boot ready:** Context đã hoàn tất `refresh`; Spring Boot còn có started, runner và ready sau đó.

Nếu muốn thực hiện công việc cần **cả ứng dụng** đã khởi động xong và sau runners, `ApplicationReadyEvent` là mốc gần nghĩa hơn. Nếu cần cung cấp hook khởi động/stop cho thành phần runtime, tìm hiểu `SmartLifecycle` và `LifecycleProcessor`: chúng liên quan đến bắt đầu/dừng các bean có lifecycle, không đồng nghĩa callback initialization một lần của singleton.

## 8. Refresh thành công, failure và rollback

### Khi một singleton non-lazy lỗi

Ví dụ:

~~~java
@Bean
InventoryClient inventoryClient() {
    throw new IllegalStateException(
            "Missing external inventory configuration");
}
~~~

Đây là ví dụ **cố ý gây lỗi**, không thêm vào project đang chạy. Trong quá trình refresh, nếu Spring phải tạo `inventoryClient` và factory method ném exception, `BeanCreationException` hoặc exception startup có thể được báo ra ngoài. Context không thể coi là đã refresh thành công; các callback cuối như `ContextRefreshedEvent` và `ApplicationReadyEvent` thường không đạt được ở lần startup thất bại này.

Spring thực hiện cleanup khi refresh không hoàn tất theo khả năng framework, bao gồm hủy những singleton đã quản lý phù hợp. Tuy nhiên không nên diễn giải cleanup đó thành bảo đảm mọi tài nguyên ngoại vi đã mở thủ công đều luôn đóng đúng trong mọi trường hợp. Constructor hoặc init method mở file/socket/connection rồi lỗi giữa chừng cần có cơ chế xử lý/dọn dẹp của chính code đó.

### Một request lỗi không tự thực hiện refresh lại

Trong ứng dụng web đã chạy, một controller có thể ném exception trong một request. Điều đó thường chỉ được xử lý trong phạm vi HTTP request. Không gọi lại `SpringApplication.run(...)` để “sửa” một request hỏng; làm vậy có thể tạo một context mới, nhân đôi bean và tranh chấp port.

### Có nên gọi context.refresh() thêm lần nữa?

**Không coi `refresh()` là nút hot reload chung cho ứng dụng Spring Boot.** Không phải mọi triển khai `ApplicationContext` đều hỗ trợ nhiều lần refresh; các context dựa trên `GenericApplicationContext` thông thường không cho refresh lại lần thứ hai. Ngay cả với những context hỗ trợ, thay đổi bean definition/config và quản lý toàn bộ resource đang chạy đòi hỏi thiết kế rõ ràng.

Để đổi cấu hình startup/bean trong ứng dụng thực tế, ưu tiên triển khai phiên bản mới, restart có kiểm soát hoặc cơ chế refresh có contract riêng (nếu hệ thống đã cung cấp). Việc sửa `application.yml` trên đĩa không tự làm một singleton đã tạo được “khởi tạo lại”.

## 9. Quan hệ với startup time, readiness và vận hành

### Eager initialization có lợi gì?

- Giúp phát hiện sớm dependency bị thiếu, cấu hình bean sai, lỗi constructor/initialization của các bean non-lazy.
- Những singleton cần thiết thường đã được tạo trước khi đạt mốc context refreshed, giảm việc khởi tạo ngoài dự kiến ở request đầu tiên.
- Phù hợp cho các thành phần phải sẵn sàng phục vụ ngay khi ứng dụng được điều phối traffic.

### Eager initialization có giá phải trả gì?

- Nhiều bean được tạo sớm làm tăng thời gian startup và đôi khi dùng tài nguyên cho chức năng chưa cần ngay.
- Constructor/`@PostConstruct` chứa network I/O dài hoặc thao tác blocking có thể trì hoãn refresh và readiness.
- Startup timeout ở container orchestration có thể kích hoạt restart lặp lại nếu công việc startup quá nặng.

### Lazy initialization có lợi gì và giới hạn nào?

- Hoãn khởi tạo một phần bean tới lần sử dụng đầu; có thể giảm chi phí startup ban đầu.
- Lần sử dụng đầu có thể chậm hơn và lỗi của bean bị trì hoãn phát hiện.
- Khó dự đoán thời điểm tạo nếu nhiều bean có dependency phức tạp; đo lường bằng log/metrics thực tế thay vì giả định.

**Readiness ≠ finishRefresh.** `ContextRefreshedEvent` đánh dấu context refresh xong, còn Spring Boot có thể chạy `ApplicationRunner`/`CommandLineRunner` trước `ApplicationReadyEvent`. Ứng dụng có thể đã mở cổng HTTP trước khi thực sự ready. Hệ thống triển khai nên dùng readiness probe đúng nghĩa để quyết định traffic; không chỉ kiểm tra port đã nghe.

Để phân tích startup, có thể dùng `ApplicationStartup`/`BufferingApplicationStartup`, Java Flight Recorder hoặc Micrometer Observation phù hợp với phiên bản và cấu hình hệ thống. Đừng lấy thời gian của riêng constructor một bean làm toàn bộ thời gian refresh.

## 10. Các lỗi tư duy thường gặp

**1. “Singleton luôn được tạo đúng lúc startup.”** Sai. Singleton có thể là lazy; bean được tạo theo yêu cầu sau khi startup hoặc sớm vì dependency. Singleton mô tả scope, không nhất thiết mô tả thời điểm.

**2. “@Lazy đảm bảo đến request đầu tiên mới tạo bean.”** Sai. Một bean eager có dependency trực tiếp vào bean lazy có thể kéo nó tạo trong refresh. Trong ứng dụng CLI, bean lazy có thể được lấy qua `getBean` dù không có request nào.

**3. “@PostConstruct nghĩa là tất cả singleton khác đã sẵn sàng.”** Sai. Nó chỉ là giai đoạn initialization của bean hiện tại. Nếu cần mốc rộng hơn, dùng `SmartInitializingSingleton` hoặc event theo nhu cầu.

**4. “finishBeanFactoryInitialization và finishRefresh là cùng một thứ.”** Sai. Giai đoạn hoàn tất BeanFactory initialization diễn ra **trước** `finishRefresh`; Spring Boot còn tiếp tục các mốc startup sau context refresh.

**5. “ContextRefreshedEvent = ApplicationReadyEvent.”** Sai. `ContextRefreshedEvent` thuộc Spring context; `ApplicationReadyEvent` thuộc Spring Boot và đến sau startup runners khi startup thành công.

**6. “Gọi preInstantiateSingletons là tạo mọi bean của JVM.”** Sai. Nó chạy trong phạm vi BeanFactory tương ứng, tập trung vào singleton non-lazy đủ điều kiện; các scope và context khác có hợp đồng riêng.

**7. “Khởi tạo bean theo thứ tự tên file hoặc thứ tự @Bean được viết.”** Không nên dựa vào đó. Dependency graph, post-processor và bean infrastructure quyết định nhiều ràng buộc. Chỉ thể hiện thứ tự phụ thuộc khi thật sự cần, tránh viết logic nghiệp vụ dựa trên thứ tự đăng ký ngẫu nhiên.

**8. “Khi startup thất bại, mọi thứ bên ngoài đều đã được rollback.”** Sai. Cleanup container có giới hạn; những tác vụ có side effect ngoài hệ thống (ghi DB, gọi API, gửi message) cần tính idempotency và phục hồi riêng.

**9. “Khởi tạo lazy chắc chắn nhanh hơn trong mọi tình huống.”** Không có bảo đảm như vậy. Nó chuyển chi phí startup sang thời điểm sử dụng và có thể tăng độ trễ request đầu hoặc phát hiện lỗi muộn.

**10. “Chỉ cần gọi refresh() lại để chạy @PostConstruct một lần nữa.”** Không phù hợp với cơ chế chung của Spring Boot. Hãy xác định vòng đời và loại context thực tế; nếu cần tái tạo bean/config, thiết kế giải pháp được hỗ trợ.

## 11. Bài thực hành và câu hỏi tự kiểm tra

1. Trong demo, ghi lại thứ tự `EagerCatalog created`, `afterSingletonsInstantiated`, `ContextRefreshedEvent` và `ApplicationReadyEvent`. Vì sao chúng không phải cùng một mốc?
2. Xóa `@Lazy` ở `lazyParser`. Dòng tạo `LazyParser` di chuyển đến đâu? Sự thay đổi có làm singleton trở thành prototype không?
3. Giữ `@Lazy`, gọi `context.getBean(LazyParser.class)` hai lần và so sánh bằng toán tử `==`. Bạn dự đoán kết quả nào?
4. Tạo một singleton non-lazy cần `LazyParser` trong constructor. Quan sát việc `LazyParser` có còn được trì hoãn đến sau `run` không. Giải thích nguyên nhân.
5. Bổ sung `ApplicationRunner` có log vào ví dụ. Sự kiện Boot nào nằm trước runner và sự kiện nào nằm sau?
6. Cố ý ném exception trong `EagerCatalog` constructor. Những dòng log mốc sau refresh có xuất hiện không? Vì sao ứng dụng không đạt ready?
7. Bật `spring.main.lazy-initialization=true`. Xem các log tạo bean và kiểm tra tính đúng đắn của giả định “tất cả bean bị hoãn”.
8. Một service cần chạy logic sau khi toàn bộ singleton non-lazy được khởi tạo; nên chọn `@PostConstruct` hay `SmartInitializingSingleton`? Một job khởi động cần hoàn tất trước khi hệ thống được báo ready nên cân nhắc runner hay event nào?
9. Nếu singleton tạo connection pool trong initialization, làm sao đảm bảo dọn dẹp khi startup lỗi hoặc context đóng? Tại sao không nên thực hiện network I/O thiếu timeout trong constructor?
10. Nếu ứng dụng web đã refresh xong nhưng một startup runner chưa hoàn tất, có nên kết luận instance đã ready nhận traffic chỉ vì kiểm tra TCP port thành công không?

## Ghi nhớ

- **Singleton scope** là quy tắc tồn tại của bean trong container; **eager/lazy** quyết định thời điểm khởi tạo.
- Trong một lần `ApplicationContext.refresh()` thành công, Spring thường **pre-instantiate các singleton non-lazy** tại `finishBeanFactoryInitialization(...)` và gọi các `SmartInitializingSingleton` phù hợp.
- `finishRefresh()` diễn ra sau đó và phát `ContextRefreshedEvent`; Spring Boot còn có `ApplicationStartedEvent`, runners và `ApplicationReadyEvent`.
- `@PostConstruct` chỉ xác nhận giai đoạn initialization của **một bean**; nó không chứng minh tất cả singleton khác hay cả ứng dụng đã ready.
- `@Lazy` không bảo đảm hoãn bean nếu có dependency cần nó từ sớm. Khởi tạo trễ có thể chuyển chi phí và lỗi sang lần dùng đầu.
- Không dùng `refresh()` như cách reload toàn bộ ứng dụng một cách tùy tiện, và không lấy “port đã mở” làm bằng chứng readiness.

### Tài liệu tham khảo

- Spring Framework 6.1 — `AbstractApplicationContext.refresh()`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.1 — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework 6.1 — `SmartInitializingSingleton`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Bean Initialization and Destruction: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — SpringApplication and Application Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
