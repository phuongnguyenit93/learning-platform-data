# Chọn điểm mở rộng theo tài nguyên đang có ở từng giai đoạn

## 1. Vấn đề: một công việc đúng nhưng đặt sai thời điểm vẫn gây lỗi

Spring Boot có nhiều **điểm mở rộng (extension points)** để can thiệp vào quá trình khởi động: listener, bộ xử lý môi trường, bộ khởi tạo context, hook vòng đời bean, runner và sự kiện ứng dụng sẵn sàng. Chúng **không thể dùng thay thế cho nhau** vì mỗi điểm xuất hiện tại một giai đoạn khác nhau.

Giả sử ứng dụng cần thực hiện bốn việc:

- Thêm một giá trị cấu hình mặc định **trước khi Spring quyết định bean nào phải được tạo**.
- Bổ sung định nghĩa bean vào `ApplicationContext` **trước khi bean được khởi tạo**.
- Chuẩn bị dữ liệu nội bộ **sau khi một service đã được tiêm phụ thuộc**.
- Kiểm tra dữ liệu ban đầu bằng một service **sau khi context khởi động và trước khi ứng dụng được đánh dấu sẵn sàng**.

Nếu đặt cả bốn việc vào `ApplicationReadyEvent`, hai việc đầu sẽ quá muộn: Spring đã đọc các điều kiện cấu hình và tạo bean. Ngược lại, nếu cố lấy service từ `ApplicationStartingEvent`, context còn chưa tồn tại. Đây là lý do chọn hook theo **tài nguyên thực sự đang có** thay vì chỉ dựa trên tên của hook.

**Nguyên tắc cốt lõi:** trước hết xác định công việc cần `Environment`, metadata/định nghĩa bean, bean instance đã khởi tạo, hay một ứng dụng đã qua runner; sau đó chọn **giai đoạn sớm nhất đủ điều kiện** để thực hiện việc đó an toàn.

## 2. Bản đồ khởi động: tài nguyên xuất hiện dần

Trình tự khái quát của Spring Boot 3.3:

```text
SpringApplication.run(...)
        |
        v
ApplicationStartingEvent
  - Có SpringApplication và arguments
  - Chưa có Environment được chuẩn bị, chưa có ApplicationContext
        |
        v
Chuẩn bị và xử lý Environment
  - EnvironmentPostProcessor
  - ApplicationEnvironmentPreparedEvent
  - Có PropertySources; chưa có ApplicationContext
        |
        v
Tạo ApplicationContext + chạy ApplicationContextInitializer
  - Có Context và Environment
  - Chưa refresh; chưa thể dựa vào bean ứng dụng
        |
        v
ApplicationContextInitializedEvent
  - Initializers đã chạy
  - Chưa tải các bean definitions chính của ứng dụng
        |
        v
Tải cấu hình và bean definitions
        |
        v
ApplicationPreparedEvent
  - Definitions đã được tải
  - Context chưa refresh
        |
        v
refresh() và vòng đời bean
  - BeanDefinitionRegistryPostProcessor
  - BeanFactoryPostProcessor
  - BeanPostProcessor, @PostConstruct, khởi tạo singleton
  - Nếu có Web server: sự kiện khởi tạo Web server khi phù hợp
  - ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
  - Context đã refresh
  - Chưa chạy ApplicationRunner / CommandLineRunner
        |
        v
LivenessState.CORRECT
        |
        v
ApplicationRunner và CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
ReadinessState.ACCEPTING_TRAFFIC (quy trình mặc định)

Nếu khởi động thất bại: ApplicationFailedEvent
(context có thể vắng mặt hoặc chỉ được tạo một phần)
```

Sơ đồ cho thấy **thứ tự các mốc quan trọng**, không phải lời hứa rằng mọi bean và mọi tác vụ đều hoạt động theo một thứ tự nội bộ cố định. Các callback liên quan đến refresh có thể chạy nhiều lần trong những thiết kế nhiều context hoặc khi một context được refresh lại.

Có hai điều rất dễ bỏ sót:

1. **`ApplicationContextInitializedEvent` khác `ApplicationPreparedEvent`.** Ở mốc thứ nhất, initializers đã chạy nhưng các định nghĩa bean chính của ứng dụng chưa được tải. Ở mốc thứ hai, definitions đã được tải nhưng context chưa refresh.
2. **`ApplicationStartedEvent` khác `ApplicationReadyEvent`.** Sau Started vẫn còn các runner. Một runner chậm hoặc lỗi có thể kéo dài hoặc ngăn ứng dụng đạt mốc Ready.

## 3. Bảng chọn hook theo tài nguyên thực tế

| Bạn đã có gì ở giai đoạn này? | Hook gợi ý | Việc phù hợp | Không được giả định |
|---|---|---|---|
| Chỉ có đối tượng khởi động và đối số rất sớm | Listener `ApplicationStartingEvent` đăng ký từ trước | Ghi dấu mốc bắt đầu, quan sát quá trình bootstrap | `Environment` đã chuẩn bị hoặc có bean ứng dụng |
| `ConfigurableEnvironment`, `PropertySources` | `EnvironmentPostProcessor` | Thêm/chỉnh nguồn property, giá trị fallback trước khi tạo context | Có `ApplicationContext` hoặc service |
| `Environment` được chuẩn bị, context chưa có | Listener `ApplicationEnvironmentPreparedEvent` đăng ký sớm | Quan sát cấu hình, phối hợp logic trước khi tạo context | Có thể lấy bean bằng `getBean` |
| Context vừa tạo, đã có environment, chưa refresh | `ApplicationContextInitializer` | Cấu hình context, đăng ký thành phần định nghĩa phù hợp trước refresh | Các singleton ứng dụng đã khởi tạo |
| Đã chạy initializer, chưa tải definitions ứng dụng | Listener `ApplicationContextInitializedEvent` | Quan sát/truyền thông tin giai đoạn context ban đầu | Đã có bean definitions hoàn chỉnh |
| Definitions đã tải nhưng context chưa refresh | Listener `ApplicationPreparedEvent` | Chẩn đoán cấu hình trước refresh | Các bean đã sẵn sàng cho nghiệp vụ |
| Bean registry/factory có metadata trước tạo bean | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | Điều chỉnh hoặc bổ sung **bean definitions** | Có thể gọi tùy ý các bean nghiệp vụ mà không ảnh hưởng vòng đời |
| Một bean đã được tạo, dependency của chính bean đã được tiêm | `@PostConstruct` / `InitializingBean`, đôi khi `BeanPostProcessor` | Khởi tạo **trạng thái của bean đó**, xử lý quanh vòng đời từng bean | Toàn hệ thống đã ready hoặc mọi bean khác đã xong |
| Context đã refresh, runner chưa chạy | `ApplicationStartedEvent` | Quan sát trạng thái sau refresh, ghi số đo/telemetry phù hợp | Các startup runner đã hoàn tất |
| Các singleton bình thường và context đã khởi tạo để chạy tác vụ khởi động | `ApplicationRunner` / `CommandLineRunner` | Dùng service để kiểm tra dữ liệu, tải thông tin khởi tạo, chạy tác vụ phải xong trước ready | Chạy lâu là vô hại, hoặc Web server chắc chắn chưa nhận kết nối |
| Tất cả runner đã được gọi và hoàn tất thành công | `ApplicationReadyEvent` | Công bố/quan sát mốc ứng dụng đã hoàn thành chuỗi startup | Mọi dịch vụ bên ngoài chắc chắn khỏe mạnh mãi về sau |
| Khởi động gặp exception | `ApplicationFailedEvent` qua listener đăng ký sớm | Ghi/thu thập lỗi bootstrap, dọn tài nguyên độc lập | Context/bean nào đó luôn tồn tại |

Chọn theo **việc cần hoàn thành**: cần thay đổi quyết định tạo bean thì làm sớm; cần dùng service thì làm sau khi bean đã khởi tạo; cần đánh dấu sẵn sàng thì làm sau runner. Cùng một công việc có thể tách thành nhiều giai đoạn, mỗi giai đoạn nhận đúng đầu vào nó cần.

## 4. Điểm mở rộng trước khi có ApplicationContext

### 4.1. ApplicationStartingEvent: chưa có Environment chuẩn bị

`ApplicationStartingEvent` phát rất sớm, sau khi Spring Boot đăng ký các listeners/initializers và trước phần lớn công việc chuẩn bị. Đây là nơi thích hợp để **đánh dấu một giai đoạn khởi động** hoặc nối logic nền tảng rất sớm.

Ví dụ chỉ minh họa cách đăng ký:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event ->
        System.out.println("SpringApplication bắt đầu khởi động"));

app.run(args);
```

Đoạn trên cần các import Spring tương ứng và lớp `MyApplication` thật; nó **không phải tệp Java độc lập**. Lúc listener xử lý sự kiện này, đừng làm:

```java
// Cách nghĩ sai ở giai đoạn sớm:
myBusinessService.loadData();
```

Service ứng dụng chưa được Spring tạo. Đặt logic nghiệp vụ tại đây có thể dẫn đến lỗi null, lỗi phụ thuộc hoặc phải tự tạo service ngoài Spring, làm hỏng tính nhất quán của ứng dụng.

**Đăng ký đúng thời điểm:** listener cần được gắn qua `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)` hoặc đăng ký bootstrap thích hợp bằng `META-INF/spring.factories`. Một listener được định nghĩa bằng `@Bean` **không tồn tại đủ sớm** để nhận sự kiện trước khi context tạo bean.

### 4.2. EnvironmentPostProcessor: thay đổi property trước khi context được refresh

`EnvironmentPostProcessor` nhận `ConfigurableEnvironment` và `SpringApplication`. Đây là điểm mở rộng chuyên dụng khi cần **thêm hoặc điều chỉnh property source sớm**.

Ví dụ cung cấp giá trị fallback `demo.region=local` mà không ghi đè cấu hình do người vận hành đặt:

**`src/main/java/com/example/lifecycle/RegionDefaults.java`:**

```java
package com.example.lifecycle;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class RegionDefaults implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "demoRegionDefaults",
                        Map.of("demo.region", "local")));
    }
}
```

Đăng ký trong **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.lifecycle.RegionDefaults
```

Trong Spring Boot 3.3, `EnvironmentPostProcessor` được nạp theo khóa trên trong `spring.factories`. `addLast` đưa nguồn này về cuối danh sách property sources ở thời điểm thêm, nên các nguồn ưu tiên cao hơn (ví dụ cấu hình người dùng đã được nạp) có thể ghi đè giá trị fallback. Thứ tự tương đối với các bộ xử lý môi trường khác có thể kiểm soát bằng `Ordered`/`@Order`; cần kiểm tra điều này khi property phải tác động đến quyết định rất sớm của hệ thống.

Không nên dùng `@Service` và `@PostConstruct` để bổ sung property quan trọng cho việc chọn bean dựa trên `@ConditionalOnProperty`: đến lúc `@PostConstruct` chạy, quyết định đăng ký nhiều bean definitions đã được đưa ra.

### 4.3. ApplicationEnvironmentPreparedEvent: quan sát Environment nhưng chưa có bean

`ApplicationEnvironmentPreparedEvent` được phát khi Spring Boot đã có `Environment` dành cho context, **trước khi tạo context**. Listener đăng ký sớm có thể đọc giá trị property:

```java
app.addListeners(
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
        String runtimeVersion =
                event.getEnvironment().getProperty("java.version");
        System.out.println("Java runtime: " + runtimeVersion);
    });
```

Vì thứ tự giữa các listener và bộ xử lý môi trường có thể ảnh hưởng trạng thái `PropertySources` mà listener thấy, không nên giả định mọi nguồn cấu hình bổ sung đã được xử lý theo ý định ở bất kỳ listener nào. Với công việc **tạo property source có ảnh hưởng đến bootstrap**, `EnvironmentPostProcessor` và quản lý thứ tự thường diễn đạt mục đích rõ hơn.

Không có `ApplicationContext` ở thời điểm này; không gọi `getBean` hay sử dụng `@Autowired` trên một bean chưa tồn tại để thực hiện logic trong sự kiện sớm.

## 5. ApplicationContextInitializer: context có, bean chưa sẵn sàng

`ApplicationContextInitializer<ConfigurableApplicationContext>` được gọi **sau khi tạo context, trước khi refresh**. Có thể dùng nó để cấu hình context hoặc đăng ký bean definitions với API được context hỗ trợ.

Ví dụ một initializer chỉ quan sát context:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addInitializers(
    (ApplicationContextInitializer<ConfigurableApplicationContext>) context -> {
        System.out.println("Context type: "
                + context.getClass().getSimpleName());
        System.out.println("Profile đang hoạt động: "
                + String.join(",", context.getEnvironment().getActiveProfiles()));
    });

app.run(args);
```

Ở đây **context đã có**, nhưng **chưa refresh**, vì vậy không thể dùng việc `getBean(MyService.class)` như một phép thử đáng tin về một service đã khởi tạo.

Nếu thực sự cần đăng ký bean programmatically trước refresh và loại context là `GenericApplicationContext`, có thể dùng API đăng ký của nó:

```java
if (context instanceof GenericApplicationContext generic) {
    generic.registerBean(
            "clock",
            java.time.Clock.class,
            java.time.Clock::systemUTC);
}
```

Đây là đoạn **chèn vào callback initializer**, cần import `org.springframework.context.support.GenericApplicationContext` hoặc viết tên đầy đủ. Nó đăng ký **định nghĩa** bean; không có nghĩa `Clock` đã được Spring lấy ra và tất cả singleton đã khởi tạo tại chính callback.

Nếu chỉ muốn thêm một cấu hình Java cố định, `@Import` hoặc một `@Configuration` phù hợp có thể đơn giản và dễ bảo trì hơn. Initializer có giá trị khi muốn can thiệp từ điểm khởi động/khung dùng chung, trước vòng đời bean.

### Các sự kiện tiếp theo vẫn còn sớm

- `ApplicationContextInitializedEvent`: initializers đã chạy, các định nghĩa bean ứng dụng **chưa** được tải.
- `ApplicationPreparedEvent`: bean definitions **đã** được tải, context vẫn **chưa refresh**.

Sự khác nhau giữa hai mốc này quan trọng nếu bạn định quan sát hoặc kiểm tra danh sách **bean definitions**, nhưng chưa đủ để tự tin gọi một service nghiệp vụ. Nếu cần **chỉnh** definitions, dùng đúng cơ chế hậu xử lý BeanFactory/Registry thường thích hợp hơn tự thao tác vào listener.

## 6. BeanDefinitionRegistryPostProcessor và BeanFactoryPostProcessor: làm việc với định nghĩa bean

Sau khi đã có bean factory và quá trình cấu hình, Spring xử lý các định nghĩa bean trước khi tạo các bean thông thường.

- `BeanDefinitionRegistryPostProcessor` có thể bổ sung hoặc thay đổi bean definitions thông qua registry, thích hợp cho một số cơ chế sinh định nghĩa bean.
- `BeanFactoryPostProcessor` có thể sửa metadata/cấu hình các bean definitions hiện có trước khi bean thông thường được khởi tạo.

**Đầu vào chính lúc này là bean definition metadata**, chẳng hạn tên bean, class, scope, property values hoặc thông tin đăng ký. Không nên gọi một service nghiệp vụ chỉ vì bean factory đã tồn tại.

Một ví dụ tự chứa về **BeanFactoryPostProcessor** (đặt thành lớp bên trong project Spring Boot):

```java
package com.example.lifecycle;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.stereotype.Component;

@Component
public class BeanCountPostProcessor implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        int definitions = beanFactory.getBeanDefinitionCount();
        System.out.println("Số bean definitions hiện có: " + definitions);
    }
}
```

Số lượng phụ thuộc project, dependency và auto-configuration; **không có kết quả số cố định**. Phép đo này đếm definitions tại thời điểm callback, không phải “toàn bộ bean đang chạy”. Cố gọi `getBean` để thực thi logic nghiệp vụ trong post-processor có thể khiến bean khởi tạo quá sớm, bỏ qua một phần các post-processor khác.

Các bộ hậu xử lý kiểu này là **hạ tầng Spring**, cần dùng có mục đích rõ ràng. Khi nhu cầu chỉ là tạo service hay cấu hình thông thường, `@Component`, `@Bean`, `@Import` và constructor injection thường phù hợp hơn.

## 7. BeanPostProcessor, @PostConstruct và InitializingBean: có một bean, chưa có toàn hệ thống

Khi Spring bắt đầu tạo một bean, nó xác định và tiêm phụ thuộc, gọi các callback khởi tạo và các `BeanPostProcessor` thích hợp. Đây là giai đoạn thích hợp để **chuẩn bị trạng thái riêng** của bean.

Ví dụ:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private String state = "new";

    @PostConstruct
    public void prepare() {
        state = "initialized";
        System.out.println("3. WorkerService @PostConstruct: " + state);
    }

    public String currentState() {
        return state;
    }
}
```

Đối với `WorkerService`, khi `@PostConstruct` chạy, việc tiêm phụ thuộc của chính bean này đã diễn ra theo cơ chế Spring. Nó phù hợp để kiểm tra dữ liệu nội bộ hoặc chuẩn bị cấu trúc nội bộ không cần toàn hệ thống.

**Không nên** coi `@PostConstruct` là mốc “Spring Boot ready”. Các bean khác có thể chưa được khởi tạo, Web server có thể chưa hoàn thành mọi giai đoạn, và runner chưa chạy. Nếu một bean cần giao tiếp với tài nguyên ngoài nặng (database, HTTP service), hãy cân nhắc việc thực hiện ở hook có khả năng báo lỗi, giới hạn thời gian và hành vi startup rõ ràng.

`BeanPostProcessor` chuyên xử lý từng bean **trước/sau khởi tạo**, thường dùng cho AOP, proxy hoặc hạ tầng tương tự. Không nên dùng nó như sự kiện “ứng dụng đã khởi động”; callback có thể được gọi nhiều lần cho các bean khác nhau, và việc làm nặng ở đây làm chậm/ảnh hưởng nhiều bean.

Có thể dùng `InitializingBean.afterPropertiesSet()` thay cho `@PostConstruct` trong trường hợp cần một hook khởi tạo rõ ràng theo interface Spring; cả hai vẫn thuộc **vòng đời bean**, không thay được `ApplicationReadyEvent`.

## 8. Context đã refresh: Started, Runner và Ready

### ApplicationStartedEvent: chưa chạy runner

`ApplicationStartedEvent` phát sau khi `ApplicationContext` được refresh và trước khi gọi `ApplicationRunner` / `CommandLineRunner`. Đây là điểm có thể quan sát các bean đã khởi tạo trong context, nhưng **các bước trong runner vẫn chưa hoàn tất**.

Sau `ApplicationStartedEvent`, Spring Boot còn phát thay đổi trạng thái liveness sang `LivenessState.CORRECT` theo quy trình mặc định. “Sống” (liveness) **không tương đương** “sẵn sàng nhận tải” (readiness).

### ApplicationRunner và CommandLineRunner: có bean để làm việc trước Ready

`ApplicationRunner` nhận `ApplicationArguments`; `CommandLineRunner` nhận `String... args`. Cả hai được gọi sau mốc Started và trước Ready. Có thể dùng chúng để:

- Xác thực dữ liệu, hoàn thành công việc khởi tạo bắt buộc trước khi công bố readiness.
- Tải cache hoặc chuẩn bị thông tin ứng dụng cần dùng ngay sau startup, nếu việc này được thiết kế đồng bộ.
- Kiểm tra sự tồn tại của cấu hình bắt buộc và để lỗi startup nổi lên nếu kiểm tra thất bại.

Ví dụ đặt trong một lớp `@Configuration`:

```java
@Bean
ApplicationRunner verifyAtStartup(WorkerService workerService) {
    return args -> {
        System.out.println("4. Runner thấy state: "
                + workerService.currentState());
    };
}
```

Đây là đoạn phương thức bean minh họa; cần import `org.springframework.context.annotation.Bean` và `org.springframework.boot.ApplicationRunner` khi đưa vào lớp. Nó sử dụng **bean đã được Spring tạo và tiêm vào phương thức `@Bean`**.

**Cẩn trọng với việc chặn lâu:** runner đồng bộ có thể làm chậm mốc Ready. Nếu Web server đã mở socket trước runner, một số yêu cầu vẫn có thể tới trước khi hệ thống đánh dấu ready; đừng dựa vào giả định “chưa Ready = chưa thể có request”. Khi triển khai, cấu hình readiness probe và kiểm soát routing đúng.

### ApplicationReadyEvent: runner đã xong

`ApplicationReadyEvent` phát sau khi các runner chạy thành công, báo ứng dụng gần như đã hoàn thành chuỗi bootstrap. Theo trình tự mặc định, `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` được phát **ngay sau đó**. Listener `ApplicationReadyEvent` chạy **trước** thông báo readiness này.

Một bean có thể dùng:

```java
@EventListener(ApplicationReadyEvent.class)
public void whenReady() {
    System.out.println("5. ApplicationReadyEvent");
}
```

Phương thức này phải thuộc một bean đã được tạo (ví dụ lớp `@Component` hoặc `@Configuration`) và import `org.springframework.context.event.EventListener` cùng `ApplicationReadyEvent`. Dùng nó cho quan sát/trình tự nhẹ liên quan tới mốc ready; listener chạy đồng bộ theo mặc định, nên công việc nặng cũng có thể làm chậm việc đánh dấu sẵn sàng. Nếu nhiệm vụ **bắt buộc hoàn tất trước Ready**, runner thường biểu đạt điều kiện đó rõ ràng hơn.

## 9. Ví dụ hoàn chỉnh: cùng một lần chạy, quan sát năm giai đoạn

Dự án Spring Boot 3.3.x, Java 17+ sau đây không cần Web server, giúp nhìn rõ thứ tự các callback. Nó **không** cố gọi service trước khi bean được tạo.

Cấu trúc:

```text
extension-phase-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lifecycle/
    ├── ExtensionLifecycleApplication.java
    └── WorkerService.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'extension-phase-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

**`src/main/java/com/example/lifecycle/ExtensionLifecycleApplication.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ExtensionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExtensionLifecycleApplication.class);

        // Không cần HTTP server trong bài thực hành.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Listener đăng ký trước run, vì lúc này chưa có bean.
        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event ->
                        System.out.println("0. ApplicationStartingEvent"));

        application.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
                    boolean hasJavaVersion =
                            event.getEnvironment().containsProperty("java.version");
                    System.out.println(
                            "1. Environment co java.version: " + hasJavaVersion);
                });

        application.addInitializers(
                (ApplicationContextInitializer<ConfigurableApplicationContext>) context ->
                        System.out.println(
                                "2. Context da ton tai: "
                                + context.getClass().getSimpleName()));

        application.run(args);
    }

    @Bean
    ApplicationRunner printAfterContext(WorkerService workerService) {
        return args -> System.out.println(
                "4. Runner thay WorkerService: "
                + workerService.currentState());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("5. ApplicationReadyEvent");
    }
}
```

**`src/main/java/com/example/lifecycle/WorkerService.java`:**

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private String state = "new";

    @PostConstruct
    public void prepare() {
        state = "initialized";
        System.out.println("3. WorkerService @PostConstruct: " + state);
    }

    public String currentState() {
        return state;
    }
}
```

Nếu project đã có Gradle Wrapper, chạy ở thư mục `extension-phase-demo`:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có Wrapper, tạo project qua Spring Initializr hoặc dùng Gradle phù hợp để sinh các tệp Wrapper. Bản ví dụ không giả định các tệp Wrapper tự xuất hiện chỉ vì bạn viết `build.gradle`.

Các dòng **do chương trình tự in** sẽ xuất hiện theo thứ tự ý nghĩa sau; Spring Boot/Gradle còn có log khác xen giữa:

```text
0. ApplicationStartingEvent
1. Environment co java.version: true
2. Context da ton tai: AnnotationConfigApplicationContext
3. WorkerService @PostConstruct: initialized
4. Runner thay WorkerService: initialized
5. ApplicationReadyEvent
```

Giá trị `true` phản ánh thuộc tính hệ thống Java thông thường; tên lớp context phản ánh context **mặc định khi dùng `WebApplicationType.NONE`**. Nếu bạn tùy chỉnh `ApplicationContextFactory` hoặc hệ thống chạy khác đáng kể, tên context có thể khác. Điều chắc chắn cần kiểm chứng là **thứ tự pha**: môi trường có trước context, bean khởi tạo trước runner và ready sau runner.

### Vì sao ví dụ không lấy WorkerService trong listener đầu tiên?

`ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` đến khi Spring chưa tạo bean ứng dụng. Dù ta có thể **tự** tạo `new WorkerService()`, đối tượng đó sẽ nằm ngoài quản lý của Spring và không phải bean đã được tiêm phụ thuộc theo vòng đời bình thường. Cách thử nghiệm đúng là đọc property tại pha sớm, rồi chỉ đọc service tại runner/bean callback.

### Vì sao @EventListener nhận được Ready nhưng không nhận Starting?

`@EventListener` được phát hiện khi Spring tạo và xử lý các bean trong context. Vì vậy phương thức `onReady` trong `@SpringBootApplication` hoạt động tại pha muộn. Đổi thành `@EventListener(ApplicationStartingEvent.class)` trên một bean **không** làm nó hiện diện sớm hơn; sự kiện Starting đã xảy ra trước khi bean được tạo.

## 10. Đăng ký hook đúng cách: không chỉ chọn đúng giai đoạn

**Listener đăng ký sớm** có thể được thêm trực tiếp:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyEarlyListener());
app.run(args);
```

Hoặc cấu hình `META-INF/spring.factories` theo cơ chế Boot hỗ trợ, ví dụ:

```properties
org.springframework.context.ApplicationListener=com.example.lifecycle.MyEarlyListener
```

Ở trường hợp này, `MyEarlyListener` phải là một lớp có thể được tạo và triển khai listener hợp lệ, phụ thuộc được sẵn có ở pha bootstrap. Đây là **khung đăng ký**, cần lớp thật; không phải mã đầy đủ để chạy riêng.

**Initializer** có thể đăng ký qua `SpringApplication.addInitializers(...)` trước `run`. **EnvironmentPostProcessor** dùng khóa riêng `org.springframework.boot.env.EnvironmentPostProcessor` trong `spring.factories` như phần 4.

**Listener muộn** thường khai báo bằng bean `@EventListener` hoặc `ApplicationListener<T>` thuộc context. **Runner** là một bean `ApplicationRunner` hoặc `CommandLineRunner`; **bean hook** nằm ở lớp được Spring quản lý.

Nếu mục đích là chọn sớm **có hay không tạo bean**, hãy nhớ thời gian đăng ký còn quan trọng ngang thời gian callback: gắn listener sớm bằng một bean được tạo muộn sẽ bỏ lỡ sự kiện.

## 11. Các tình huống chọn điểm mở rộng

### Tình huống A — đặt fallback property cho nhiều module

**Đầu vào cần:** `ConfigurableEnvironment`, `PropertySources`.  
**Nên dùng:** `EnvironmentPostProcessor`, có `Ordered` khi cần.  
**Không nên dùng:** `@PostConstruct` của một service để quyết định property cho `@ConditionalOnProperty` từ trước.

Lý do: nếu conditional configuration đã được phân tích, chỉnh property muộn không đảm bảo Spring quay lại đăng ký bean bị bỏ qua.

### Tình huống B — thêm định nghĩa bean rất sớm, trước refresh

**Đầu vào cần:** `ConfigurableApplicationContext` / `BeanDefinitionRegistry`.  
**Nên dùng:** `ApplicationContextInitializer` (khi API của context phù hợp), `BeanDefinitionRegistryPostProcessor`, hoặc cơ chế cấu hình chuẩn.  
**Không nên dùng:** `ApplicationReadyEvent` để yêu cầu Spring tự đọc lại toàn bộ cấu hình đã hoàn tất.

### Tình huống C — chuẩn bị bộ nhớ đệm nội bộ cho riêng một bean

**Đầu vào cần:** dependencies đã tiêm của chính bean.  
**Nên dùng:** `@PostConstruct` hoặc `InitializingBean` nếu thao tác gọn, không gây phụ thuộc vòng đời khó kiểm soát.  
**Khi cần phối hợp nhiều service hoặc kết quả làm điều kiện Ready:** chuyển logic phù hợp sang runner.

### Tình huống D — kiểm tra dữ liệu khởi tạo bằng service

**Đầu vào cần:** service đã được tạo và tiêm phụ thuộc.  
**Nên dùng:** `ApplicationRunner` hoặc `CommandLineRunner` khi phải xong trước Ready.  
**Cần lưu ý:** lỗi runner có thể làm khởi động thất bại; tác vụ quá lâu làm chậm readiness. Cần timeout, xử lý thất bại và thiết kế triển khai phù hợp.

### Tình huống E — ghi nhận ứng dụng hoàn tất startup

**Đầu vào cần:** context đã refresh và các runner đã xong.  
**Nên dùng:** `ApplicationReadyEvent` cho thông báo nhẹ, số đo hoàn tất startup hoặc hành động theo mốc Ready.  
**Cần lưu ý:** readiness trong nền tảng triển khai có thể chịu thêm probe và kiểm tra độc lập; `ApplicationReadyEvent` không có nghĩa mọi hệ thống bên ngoài sẽ luôn hoạt động.

### Tình huống F — ghi nguyên nhân khởi động thất bại

**Đầu vào cần:** exception và thông tin bootstrap còn có thể truy cập.  
**Nên dùng:** listener `ApplicationFailedEvent` đã đăng ký đủ sớm.  
**Không nên giả định:** `ApplicationContext`, service logging cấu hình bằng bean hoặc database đã sẵn có; lỗi có thể xảy ra trước khi chúng được tạo.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Gắn `@EventListener(ApplicationStartingEvent.class)` vào bean | Listener không tồn tại lúc sự kiện sớm được phát | Đăng ký qua `SpringApplication.addListeners` hoặc `spring.factories`. |
| Dùng `@Autowired` service trong callback môi trường sớm | Chưa có context/bean để tiêm | Tách xử lý property ở pha sớm và nghiệp vụ ở pha bean/runner. |
| Gọi `getBean` trong `ApplicationContextInitializer` | Context chưa refresh, bean chưa sẵn sàng | Chỉ cấu hình context/definitions; để Spring tạo bean theo lifecycle. |
| Chỉnh `spring.main.*` sau khi context đã tạo | Một số quyết định bootstrap đã được chốt | Thiết lập từ config/Environment trước khi những quyết định đó xảy ra. |
| Dùng `BeanFactoryPostProcessor` để truy xuất hàng loạt bean nghiệp vụ | Khởi tạo bean quá sớm, có thể bỏ qua xử lý khác | Tập trung vào bean definitions; xử lý nghiệp vụ trong runner/service. |
| Coi `@PostConstruct` là mốc toàn ứng dụng Ready | Bean khác, runner hoặc Web readiness còn chưa hoàn tất | Dùng runner hoặc sự kiện Ready cho công việc đúng giai đoạn. |
| Cho runner thực hiện gọi mạng không timeout | Có thể giữ ứng dụng trong trạng thái startup kéo dài | Thiết lập timeout, lỗi rõ ràng và kiểm soát điều kiện readiness. |
| Làm việc nặng trong listener `ApplicationReadyEvent` | Có thể làm chậm thông báo readiness và luồng sự kiện | Dùng runner cho bước phải hoàn thành trước Ready, hoặc cơ chế xử lý sau startup có kiểm soát. |
| Cho rằng HTTP chưa nhận request trước `ApplicationReadyEvent` | Server có thể mở socket trước Ready | Cấu hình readiness probe và giới hạn điều hướng traffic. |
| Dùng một hook ở mọi nơi vì thấy nó “chạy được” | Tạo phụ thuộc ngầm vào thứ tự khởi tạo | Chọn hook từ tài nguyên đầu vào và mốc cần hoàn thành. |

## 13. Cách ra quyết định khi viết tính năng mới

Hãy trả lời tuần tự bốn câu hỏi:

1. **Công việc thật sự cần dữ liệu gì?** Chỉ `args`, `Environment`, bean metadata, một bean đã tiêm phụ thuộc hay toàn bộ dịch vụ đã khởi động?
2. **Khi nào những dữ liệu đó chắc chắn tồn tại?** Đối chiếu bảng pha, đừng thử gọi API ở pha quá sớm rồi dựa vào may rủi.
3. **Kết quả phải có hiệu lực trước mốc nào?** Trước khi Spring phân tích cấu hình, trước khi bean tạo, trước Ready hay chỉ sau Ready?
4. **Công việc có thể thất bại hoặc chạy lâu không?** Quyết định nơi báo lỗi, timeout và ảnh hưởng đến startup/readiness; không đẩy tác vụ nặng vào một callback bất kỳ.

Có thể dùng quy tắc ngắn gọn:

```text
Cần sửa cấu hình đầu vào?       -> EnvironmentPostProcessor
Cần chỉnh context trước refresh? -> ApplicationContextInitializer
Cần sửa bean definition?        -> Registry/BeanFactoryPostProcessor
Cần chuẩn bị đúng một bean?     -> @PostConstruct / InitializingBean
Cần thực hiện việc dùng service
trước khi Ready?                -> ApplicationRunner / CommandLineRunner
Cần quan sát hệ thống đã qua
runner?                         -> ApplicationReadyEvent
Cần bắt lỗi bootstrap?          -> ApplicationFailedEvent (listener sớm)
```

Đây là gợi ý chọn **điểm mở rộng phù hợp**, không phải quy định rằng mỗi nhiệm vụ chỉ có một API khả thi. Với ứng dụng đơn giản, sử dụng `@Configuration`/`@Bean` và constructor injection theo quy tắc Spring thường tốt hơn thêm các hook bootstrap không cần thiết.

## 14. Bài thực hành

Dùng project phần 9, thay đổi mỗi lần một yếu tố:

1. Chạy ứng dụng và quan sát thứ tự `0 -> 1 -> 2 -> 3 -> 4 -> 5`, đồng thời xác định thời điểm xuất hiện dòng `Started ...` giữa việc khởi tạo bean và runner.
2. Thử thêm `@EventListener(ApplicationStartingEvent.class)` vào `WorkerService`, rồi quan sát rằng callback mới trong bean không nhận sự kiện quá sớm. Giữ listener `addListeners` ở `main` để thấy nó vẫn nhận.
3. Đặt `System.out.println(workerService.currentState())` ở `ApplicationRunner` và xác nhận trả về `initialized`, sau đó giải thích vì sao không nên làm cùng việc trong `ApplicationContextInitializer`.
4. Thêm một `Thread.sleep(1000)` có xử lý `InterruptedException` phù hợp trong runner: mốc Ready bị trễ, còn listener môi trường và initializer vẫn chạy trước runner.
5. Thêm `RegionDefaults` và tệp `spring.factories` từ phần 4 vào đúng package project, rồi đọc `demo.region` từ `Environment` trong runner. Thêm giá trị khác từ `application.properties` để kiểm tra fallback và độ ưu tiên của property source.
6. Chọn tình huống ứng dụng cần tạo một bean theo cấu hình lúc startup. Giải thích vì sao sửa property đó tại `ApplicationReadyEvent` không thể tự yêu cầu Spring đánh giá lại toàn bộ `@ConditionalOnProperty`.

**Câu hỏi tự kiểm tra:** Tại sao một listener `@Bean` không thấy `ApplicationEnvironmentPreparedEvent`? Tại sao `@PostConstruct` được phép dùng phụ thuộc của bean nhưng chưa đảm bảo mọi startup runner đã chạy? Vì sao cập nhật `Environment` phải xảy ra sớm khi property quyết định việc có tạo bean hay không? Trả lời được các câu hỏi này nghĩa là bạn đã biết chọn điểm mở rộng theo **tài nguyên và mốc vòng đời**, thay vì chọn bằng cách thử ngẫu nhiên.

## Tài liệu chính thức

- Spring Boot 3.3, SpringApplication lifecycle và thứ tự các Application Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `EnvironmentPostProcessor` Java API và cách đăng ký: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3, `ApplicationStartedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3, `ApplicationReadyEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Framework, `ApplicationContextInitializer`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html

Khi chọn một điểm mở rộng, hãy xét **tài nguyên đã xuất hiện**, **thời điểm logic cần có hiệu lực** và **hành vi khi thất bại**. Một callback chạy được không đủ để chứng minh nó đúng thời điểm; callback đúng là callback nhận đủ dữ liệu, còn sớm đủ để tác động tới quyết định mong muốn, và không tạo phụ thuộc vòng đời khó kiểm soát.