# Phân biệt bean hoàn tất khởi tạo với ứng dụng Spring Boot hoàn tất khởi động

## 1. Hai mốc khác nhau trong cùng một quá trình startup

Một ứng dụng Spring Boot thường gồm hàng chục đến hàng nghìn bean. Mỗi bean có **vòng đời khởi tạo riêng**, trong khi toàn bộ ứng dụng có **vòng đời khởi động chung**. Vì vậy, thấy một bean đã chạy constructor hay **@PostConstruct** không có nghĩa toàn bộ ứng dụng đã sẵn sàng xử lý công việc.

Phân biệt hai khái niệm:

- **Bean hoàn tất khởi tạo (bean initialized):** Spring đã tạo và cấu hình **một bean cụ thể**, giải quyết các dependency cần thiết và thực hiện các bước initialization của bean đó theo contract của container. Sau khi hoàn tất các BeanPostProcessor thích hợp, bean có thể được sử dụng theo phạm vi của nó.
- **Ứng dụng hoàn tất khởi động (application ready):** Spring Boot đã hoàn tất quá trình khởi động ApplicationContext, chạy các **ApplicationRunner** và **CommandLineRunner** được đăng ký, rồi phát **ApplicationReadyEvent**. Boot tiếp tục công bố trạng thái **ReadinessState.ACCEPTING_TRAFFIC** ngay sau event này theo lifecycle mặc định.

Một bean hoàn tất khởi tạo là **mốc cục bộ**; ApplicationReadyEvent là **mốc toàn ứng dụng**. Hai mốc có thể cách nhau bởi nhiều bước: khởi tạo các bean khác, refresh context, phát startup events và chạy các runner.

**Không đồng nhất @PostConstruct, ContextRefreshedEvent, ApplicationStartedEvent và ApplicationReadyEvent.** Chúng thuộc các lớp trách nhiệm và thời điểm khác nhau.

## 2. Sơ đồ thời gian từ bean đến ứng dụng ready

~~~text
SpringApplication.run(args)
         |
         v
Chuẩn bị Environment, cấu hình, tạo ApplicationContext
         |
         v
Nạp BeanDefinition và refresh ApplicationContext
         |
         +--> Tạo bean A
         |       Constructor + dependency injection
         |       @PostConstruct / InitializingBean / init method
         |       BeanPostProcessor sau khởi tạo
         |       => Bean A đã khởi tạo
         |
         +--> Tạo bean B, C và các singleton non-lazy khác
         |
         +--> SmartInitializingSingleton callbacks
         |       (sau khi pre-instantiate các singleton thường)
         |
         +--> Hoàn tất context refresh
         |       ContextRefreshedEvent
         |
         v
ApplicationStartedEvent
         |
         +--> AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent
         |
         +--> AvailabilityChangeEvent(
         |        ReadinessState.ACCEPTING_TRAFFIC)
         |
         v
SpringApplication.run(args) trả về main
         |
         v
Ứng dụng tiếp tục hoạt động theo mô hình của nó
~~~

Sơ đồ mô tả luồng **startup thành công mặc định** của Spring Boot 3.5. Một số bean hạ tầng và BeanPostProcessor phải được tạo sớm để phục vụ việc khởi tạo các bean khác. Bean lazy/prototype có thể được tạo **sau thời điểm ready**. Các listener chạy bất đồng bộ nếu ứng dụng cấu hình riêng có thể làm việc quan sát thứ tự phức tạp hơn.

Trình tự chính thức được Spring Boot quy định:

1. **ApplicationStartingEvent**, **ApplicationEnvironmentPreparedEvent**, **ApplicationContextInitializedEvent** và **ApplicationPreparedEvent** xảy ra trước hoặc quanh quá trình tạo/chuẩn bị context.
2. **ContextRefreshedEvent** phát sau khi context được refresh; với web context, **WebServerInitializedEvent** cũng có thể được phát trong quá trình startup.
3. **ApplicationStartedEvent** phát **sau refresh**, **trước runners**.
4. **AvailabilityChangeEvent** với **LivenessState.CORRECT** được phát ngay sau started event.
5. Boot thực thi các bean **ApplicationRunner** và **CommandLineRunner**.
6. **ApplicationReadyEvent** phát **sau khi runners được gọi hoàn tất**.
7. **AvailabilityChangeEvent** với **ReadinessState.ACCEPTING_TRAFFIC** được phát ngay sau ready event.

Do đó application ready không đơn thuần là “tất cả constructor chạy xong”, cũng không chỉ là “HTTP server đã bind port”.

## 3. Khi nào một bean được coi là khởi tạo xong?

Spring quản lý bean theo **BeanDefinition**, scope, dependency và các cơ chế mở rộng của container. Với một **singleton non-lazy** thông thường, các bước tiêu biểu là:

1. **Tạo instance:** gọi constructor hoặc factory method / phương thức **@Bean**.
2. **Điền dependency và properties:** giải quyết các giá trị/bean mà đối tượng cần, thực hiện các cơ chế injection tương ứng.
3. **Aware callbacks:** một số interface như **BeanNameAware**, **BeanFactoryAware** hoặc **ApplicationContextAware** có thể được gọi theo contract.
4. **BeanPostProcessor trước initialization:** các processor có cơ hội xử lý instance trước các init callbacks.
5. **Initialization callbacks:** có thể gồm **@PostConstruct**, **InitializingBean.afterPropertiesSet()** và một **custom init-method** nếu được khai báo.
6. **BeanPostProcessor sau initialization:** các processor có thể tiếp tục xử lý, kể cả trả về wrapper/proxy trong những cơ chế như AOP.
7. Bean được container cung cấp theo **scope** của nó, với lifecycle initialization đã hoàn tất.

Một số bước có thể được thực hiện bởi chính post-processor, và thứ tự chi tiết tùy loại bean/cơ chế được cấu hình. Không nên coi constructor hoặc **@PostConstruct** là luôn là callback cuối cùng trước khi instance sẵn sàng.

Khi kết hợp ba cơ chế init callback bằng các method khác nhau, thứ tự phổ biến do Spring Framework quy định là:

~~~text
@PostConstruct
    -> InitializingBean.afterPropertiesSet()
    -> custom init-method
~~~

Nhưng các **BeanPostProcessor** có thể chạy trước/sau những callback này. Một bean bị proxy có thể khiến đối tượng được trả về cho client khác với object gốc ở mức reference, dù vẫn tuân thủ contract của Spring.

### @PostConstruct có ý nghĩa chính xác gì?

**@PostConstruct** chạy sau khi bean được tạo và các dependency cần thiết được inject, trong quá trình initialization của **bean đó**. Thích hợp cho:

- Kiểm tra tính hợp lệ của cấu hình cục bộ của bean.
- Chuẩn bị cấu trúc dữ liệu nội bộ đơn giản.
- Thiết lập những bất biến cần trước khi sử dụng bean.

**@PostConstruct không có nghĩa:**

- Mọi bean trong context đều đã khởi tạo.
- Mọi data source, message consumer hay cache ngoài hệ thống đều sẵn sàng.
- Các runner của Spring Boot đã hoàn thành.
- Ứng dụng đã phát **ApplicationReadyEvent**.
- Load balancer hoặc Kubernetes đã đánh dấu pod sẵn sàng nhận traffic.

Spring Framework khuyến cáo không đặt công việc tốn nhiều thời gian, truy cập tùy tiện sang bean khác hoặc làm việc có khả năng deadlock trong init callback: initialization diễn ra dưới sự quản lý của container và có thể nằm trong vùng khóa tạo singleton.

## 4. Phân biệt các mốc bằng bảng

| Mốc / callback | Phạm vi | Thời điểm | Điều nó chứng minh | Điều nó chưa chứng minh |
| --- | --- | --- | --- | --- |
| **Constructor** | Một object | Khi Spring tạo instance | Object đang được xây dựng | Dependency injection/khởi tạo bean đã xong |
| **@PostConstruct** | Một bean | Trong initialization của bean | Bean đã nhận dependency phù hợp để chạy callback | Context đã refresh hoặc ứng dụng ready |
| **InitializingBean.afterPropertiesSet()** | Một bean | Trong initialization | Một init callback của bean đã chạy | Các bean khác đã sẵn sàng |
| **SmartInitializingSingleton.afterSingletonsInstantiated()** | Giai đoạn singleton của BeanFactory | Sau pre-instantiation của các singleton không lazy | Đã đến mốc kết thúc bước tạo singleton thông thường | Mọi lazy/prototype bean đã tồn tại hoặc Boot ready |
| **ContextRefreshedEvent** | ApplicationContext | Sau refresh của context | Context đã hoàn tất refresh | Runners đã hoàn thành |
| **ApplicationStartedEvent** | SpringApplication | Sau refresh, trước runners | Boot đã đạt mốc started | Ứng dụng đã ready |
| **ApplicationRunner / CommandLineRunner** | Công việc startup | Sau ApplicationStartedEvent, trước ready | Đang hoàn thành phần chuẩn bị sau refresh | Các runner khác đã xong nếu method hiện tại chưa trả về |
| **ApplicationReadyEvent** | SpringApplication | Sau khi runners hoàn tất | Boot báo hoàn tất startup ở cấp ứng dụng | Mọi phụ thuộc ngoài luôn khỏe về sau |
| **ReadinessState.ACCEPTING_TRAFFIC** | ApplicationAvailability | Ngay sau ready event trong startup mặc định | Boot báo có thể nhận traffic | Orchestrator chắc chắn đã chuyển traffic vào instance |
| **@PreDestroy** | Một bean | Khi bean được hủy/đóng bình thường | Đã đến bước cleanup của bean | Ứng dụng từng hoàn tất startup hoặc mọi cleanup chắc chắn thành công |

Hai lưu ý quan trọng:

- Với các **lazy** hoặc **prototype** bean, initialization có thể xảy ra **sau ApplicationReadyEvent** khi bean lần đầu được yêu cầu. Vì vậy không phát biểu “ready nghĩa là tất cả bean trong hệ thống đã được tạo”.
- Với một context hierarchy, event của context con có thể truyền lên parent. Listener của parent có thể nhận nhiều **ContextRefreshedEvent**; cần phân biệt context phát sự kiện thay vì chỉ đếm số lần callback chạy.

## 5. Ví dụ Java 17+ chạy được: quan sát từng bước

Ví dụ này dùng **Spring Boot 3.5.x** và Java 17+ trong một ứng dụng **non-web**. Mục tiêu là thấy bằng mắt thứ tự:

- Constructor của bean.
- **@PostConstruct**.
- **SmartInitializingSingleton.afterSingletonsInstantiated()**.
- **ContextRefreshedEvent**.
- **ApplicationStartedEvent**.
- **ApplicationRunner**.
- **ApplicationReadyEvent**.
- **SpringApplication.run** trả về main.
- **@PreDestroy** khi đóng context bình thường.

### 5.1. Tạo dự án

Dùng Spring Initializr, chọn **Maven**, **Java 17 trở lên**, **Spring Boot 3.5.x**, group **com.example**, artifact **startup-stages**, package **com.example.demo**, và dependency **Spring Boot Starter**. Không cần starter-web vì ứng dụng cố ý chọn **WebApplicationType.NONE**.

Tạo file **src/main/java/com/example/demo/StartupStagesApplication.java** như sau:

~~~java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupStagesApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupStagesApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("08 | run returned; active="
                    + context.isActive());
        }
    }

    @Bean
    StageProbe stageProbe() {
        return new StageProbe();
    }

    @Bean
    ApplicationRunner runAfterStarted(Environment environment) {
        return args -> {
            System.out.println("06 | ApplicationRunner");

            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "Simulated startup runner failure");
            }
        };
    }

    public static final class StageProbe
            implements SmartInitializingSingleton {

        public StageProbe() {
            System.out.println("01 | constructor");
        }

        @PostConstruct
        public void initialized() {
            System.out.println("02 | @PostConstruct");
        }

        @Override
        public void afterSingletonsInstantiated() {
            System.out.println("03 | SmartInitializingSingleton");
        }

        @EventListener(ContextRefreshedEvent.class)
        public void contextRefreshed() {
            System.out.println("04 | ContextRefreshedEvent");
        }

        @EventListener(ApplicationStartedEvent.class)
        public void applicationStarted() {
            System.out.println("05 | ApplicationStartedEvent");
        }

        @EventListener(ApplicationReadyEvent.class)
        public void applicationReady() {
            System.out.println("07 | ApplicationReadyEvent");
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("09 | @PreDestroy");
        }
    }
}
~~~

**Mã trên là một chương trình Java đầy đủ** khi được đặt trong project Spring Boot có đúng dependencies. Không thể biên dịch bằng riêng lệnh **javac StartupStagesApplication.java** mà không có Spring Boot/Spring Framework trên classpath. Maven Wrapper của dự án giải quyết dependencies và chọn main class tương ứng.

### 5.2. Chạy chương trình

Từ thư mục gốc dự án:

~~~bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt:
# .\mvnw.cmd spring-boot:run
~~~

Kết quả **các dòng do chính chương trình in ra**, theo thứ tự trong kịch bản startup thành công mặc định:

~~~text
01 | constructor
02 | @PostConstruct
03 | SmartInitializingSingleton
04 | ContextRefreshedEvent
05 | ApplicationStartedEvent
06 | ApplicationRunner
07 | ApplicationReadyEvent
08 | run returned; active=true
09 | @PreDestroy
~~~

Maven/Spring Boot có thể in thêm log xen giữa; khối trên chỉ lọc các dòng có số thứ tự. Việc đóng context xảy ra ở cuối **try-with-resources**, vì ví dụ là chương trình non-web ngắn hạn. Với web server phục vụ lâu dài, không nên tự đóng context ngay sau run nếu cần tiếp tục nhận request.

### 5.3. Đọc kết quả từng mốc

**01 | constructor:** mới có instance StageProbe, chưa thể kết luận initialization của bean đã hoàn tất.

**02 | @PostConstruct:** bean đã được Spring đưa tới một init callback. Đây vẫn là quá trình initialization của **một bean**, chưa phải mốc ứng dụng ready.

**03 | SmartInitializingSingleton:** Spring đã kết thúc bước pre-instantiate các singleton non-lazy thông thường trong BeanFactory. Đây là extension point thích hợp hơn @PostConstruct nếu cần thực hiện việc nhẹ sau khi các singleton regular đã được tạo, nhưng trước khi context hoàn tất refresh. Nó không đảm bảo lazy/prototype đã được tạo.

**04 | ContextRefreshedEvent:** ApplicationContext đã refresh xong. Đã vượt qua việc khởi tạo các singleton cần thiết và những hook của refresh.

**05 | ApplicationStartedEvent:** Spring Boot đã phát event started, **chưa chạy các runner**. Trong lifecycle mặc định Boot sau đó phát liveness state **CORRECT**.

**06 | ApplicationRunner:** code sau refresh đang chạy. Đây là lúc có thể làm một số bước chuẩn bị ngắn cần xong **trước ready**.

**07 | ApplicationReadyEvent:** các runner đã hoàn tất bình thường. Ngay sau event, Boot công bố availability state **ReadinessState.ACCEPTING_TRAFFIC** trong startup mặc định.

**08 | run returned; active=true:** phương thức **application.run(args)** đã trả context về main. Nhờ context chưa đóng nên **isActive()** là true.

**09 | @PreDestroy:** cuối khối try gọi **close()**. Spring bắt đầu đóng context và chạy destroy callback của bean.

Ví dụ cho thấy **một bean được khởi tạo từ rất sớm**, nhưng startup của toàn ứng dụng vẫn tiếp tục qua nhiều mốc khác.

### 5.4. Chứng minh: bean init xong nhưng ứng dụng có thể không ready

Đoạn ApplicationRunner trong ví dụ cố tình có nhánh lỗi khi có property **demo.fail-runner=true**. Đóng gói chương trình:

~~~bash
./mvnw package
~~~

Chạy JAR thực thi (điều chỉnh tên nếu version/artifact được Initializr tạo khác):

~~~bash
java -jar target/startup-stages-0.0.1-SNAPSHOT.jar --demo.fail-runner=true
~~~

Khi property này được bật:

1. Constructor và **@PostConstruct** của StageProbe đã chạy.
2. Context có thể refresh thành công và Boot đã phát **ApplicationStartedEvent**.
3. **ApplicationRunner** in dòng 06 rồi ném **IllegalStateException**.
4. Startup bị coi là thất bại; **ApplicationReadyEvent** không được phát, và đoạn code sau **application.run(args)** không chạy bình thường.
5. Spring Boot có thể ghi lỗi, phát **ApplicationFailedEvent** và đóng context/tài nguyên theo đường xử lý lỗi.

Vì vậy log **@PostConstruct thành công** hay thậm chí log **ApplicationStartedEvent** cũng **không chứng minh ứng dụng đã hoàn tất startup**.

Không dùng nhánh lỗi này trên môi trường production khi không có mục đích kiểm thử. Đây là cách tạo một failure có kiểm soát để hiểu ranh giới lifecycle.

## 6. Bean có thể khởi tạo sau khi ApplicationReadyEvent không?

**Có.** Hai trường hợp phổ biến:

### Lazy singleton

~~~java
@Bean
@Lazy
ReportFormatter reportFormatter() {
    return new ReportFormatter();
}
~~~

Đây là **mảnh cấu hình minh họa**, cần class ReportFormatter và import Bean/Lazy. Nếu không có bean eager nào buộc phải inject ReportFormatter và không có logic nào truy cập nó trong startup, singleton lazy có thể chỉ được tạo khi lần đầu được yêu cầu.

Một ứng dụng hoàn toàn có thể đã phát **ApplicationReadyEvent** mà ReportFormatter vẫn chưa chạy constructor hoặc init callback. Việc này **không vi phạm** vòng đời Spring.

### Prototype bean

~~~java
@Scope("prototype")
@Component
class RequestScratchpad {
}
~~~

Đây cũng là **mảnh minh họa** (cần import và nơi sử dụng). Prototype thường được tạo theo từng lần request từ BeanFactory thay vì pre-instantiate hàng loạt lúc startup. Nếu prototype được inject vào một singleton eager khi khởi tạo, có thể đã có một instance được tạo sớm, nhưng scope prototype không biến thành singleton.

**Hệ quả:** không định nghĩa readiness bằng cách “đếm số bean đã chạy @PostConstruct”. Cần xác định những dependency nào **bắt buộc** cho việc nhận request và kiểm tra chúng bằng cơ chế phù hợp.

## 7. ContextRefreshedEvent, ApplicationStartedEvent và ApplicationReadyEvent khác nhau ra sao?

### ContextRefreshedEvent

Đây là event của **Spring Framework** khi **ApplicationContext.refresh()** hoàn tất. Nó phản ánh trạng thái **container**. Trong một ứng dụng Boot, context có thể đã refresh thành công nhưng một runner vẫn chưa thực hiện công việc chuẩn bị hoặc chưa hoàn thành.

Một hệ thống dùng context hierarchy có thể phát nhiều ContextRefreshedEvent, mỗi context theo vòng đời riêng. Hãy kiểm tra **event.getApplicationContext()** khi cần phân biệt nguồn.

### ApplicationStartedEvent

Đây là event của **Spring Boot** sau khi ApplicationContext được refresh, **trước ApplicationRunner và CommandLineRunner**. Tên “Started” diễn tả mốc đã khởi chạy context thành công, **không đồng nghĩa ready**. Nếu một runner ném exception sau mốc này, Boot có thể phát **ApplicationFailedEvent** mà không có ApplicationReadyEvent.

### ApplicationReadyEvent

Đây là event của **Spring Boot** sau các runner; nó là mốc Boot đánh dấu startup hoàn tất ở mức ứng dụng. Theo thứ tự mặc định, Boot phát tiếp AvailabilityChangeEvent với **ReadinessState.ACCEPTING_TRAFFIC**.

**Một chi tiết tinh tế:** listener đang xử lý chính **ApplicationReadyEvent** không nên mặc định suy ra **ReadinessState.ACCEPTING_TRAFFIC** đã được công bố xong, vì availability change event này được phát **sau** ready event. Nếu cần quan sát chính xác state, sử dụng API **ApplicationAvailability** hoặc listener của **AvailabilityChangeEvent** ở thời điểm thích hợp.

### Có nên tự phát ApplicationReadyEvent?

Không nên tự phát event để “ép” ứng dụng thành ready khi những bước khởi động còn thiếu. Spring Boot quản lý các event trong trình tự startup. Nếu một ứng dụng cần chủ động tạm ngừng nhận traffic ở runtime, hãy sử dụng các cơ chế **ApplicationAvailability** hoặc health/readiness được thiết kế cho mục đích đó thay vì giả lập sự kiện startup.

## 8. Readiness khác liveness và khác HTTP port mở

Spring Boot mô hình hóa availability với hai loại trạng thái chính:

| Trạng thái | Mục đích | Ví dụ |
| --- | --- | --- |
| **LivenessState** | Ứng dụng có đang ở trạng thái sống hợp lệ, cần restart hay không? | **CORRECT**, **BROKEN** |
| **ReadinessState** | Ứng dụng có nên nhận traffic tại thời điểm này không? | **ACCEPTING_TRAFFIC**, **REFUSING_TRAFFIC** |

Theo startup mặc định, liveness **CORRECT** gắn với mốc sau **ApplicationStartedEvent**, còn readiness **ACCEPTING_TRAFFIC** gắn với mốc sau **ApplicationReadyEvent**. Nhưng readiness có thể thay đổi về sau; “từng ready một lần” không có nghĩa luôn sẵn sàng mãi mãi.

Với ứng dụng web, **embedded web server có thể đã bind port trong quá trình refresh**. Một client trực tiếp có thể kết nối vào cổng trong khi runner chưa hoàn thành, tùy loại server và trạng thái. Điều này **không chứng minh readiness**. Trong môi trường orchestration, readiness probe thường quyết định có đưa traffic tới instance hay không.

Để triển khai với Spring Boot Actuator, có thể cấu hình các health probes như **/actuator/health/liveness** và **/actuator/health/readiness** khi phù hợp phiên bản và môi trường. Các endpoint/probe phụ thuộc Actuator, cấu hình bảo vệ và khả năng kích hoạt; không giả định mọi project đều có sẵn.

**Không nên tùy tiện thêm database, external cache hoặc API bên ngoài vào liveness check.** Một sự cố phụ thuộc ngoài có thể khiến pod restart liên tục, gây hiệu ứng dây chuyền. Readiness phù hợp hơn để quyết định tạm ngừng nhận traffic nếu một phụ thuộc bắt buộc không sử dụng được, nhưng cần thiết kế theo mô hình phục vụ thực tế.

## 9. Chọn hook phù hợp với nhu cầu

| Nhu cầu | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| Validate cấu hình cục bộ của bean, khởi tạo dữ liệu nội bộ đơn giản | **@PostConstruct**, init method | Liên quan trực tiếp lifecycle của bean đó |
| Hành động nhẹ sau khi các singleton non-lazy thông thường được tạo | **SmartInitializingSingleton** | Tránh truy cập chéo bean tùy tiện trong constructor/@PostConstruct |
| Phản ứng khi ApplicationContext đã refresh | **@EventListener(ContextRefreshedEvent.class)** | Context vừa hoàn tất refresh |
| Xử lý sau refresh nhưng trước runner | **@EventListener(ApplicationStartedEvent.class)** | Mốc Spring Boot started |
| Chạy tác vụ chuẩn bị bắt buộc trước ready | **ApplicationRunner** / **CommandLineRunner** | Boot đợi các runner hoàn thành trước ready |
| Thông báo hoặc thực hiện việc nhẹ khi startup đã hoàn tất | **@EventListener(ApplicationReadyEvent.class)** | Mốc cuối của Boot startup |
| Quản lý một service chạy nền có start/stop theo context | **SmartLifecycle** | Quản lý vòng đời start/stop có phase |
| Bật/tắt trạng thái nhận traffic khi điều kiện runtime thay đổi | **ApplicationAvailability** hoặc readiness health/probe | Diễn tả khả năng nhận công việc đúng thời điểm |

### Tại sao không đặt mọi việc trong @PostConstruct?

Nếu mỗi bean tự gọi dịch vụ ngoài, scan toàn bộ dữ liệu, khởi động thread vô hạn hoặc truy vấn các bean khác một cách tùy tiện trong **@PostConstruct**, startup dễ gặp:

- Khóa tạo singleton bị giữ lâu, kéo dài refresh hoặc gây deadlock.
- Dependency cycle khó hiểu.
- Lỗi khởi tạo một bean khiến toàn ApplicationContext thất bại.
- Một bean tự cho mình là ready dù các thành phần khác chưa sẵn sàng.
- Cleanup phức tạp nếu startup thất bại giữa chừng.

Nên giữ initialization callback **ngắn và cục bộ**. Khi cần kiểm tra cả hệ thống hoặc thực hiện công việc startup sau refresh, chọn runner/lifecycle hook đúng giai đoạn.

### Runner có bảo đảm việc nền đã xong?

**Không nếu runner chỉ tạo một tác vụ bất đồng bộ rồi trả về ngay.** Spring Boot chỉ đợi phương thức **run** kết thúc; nó không tự biết một Future, thread, queue consumer hoặc asynchronous operation tự tạo đã hoàn thành. Nếu công việc thật sự bắt buộc trước readiness, phải đợi/xác nhận theo cơ chế có giới hạn thời gian thích hợp hoặc kiểm soát readiness rõ ràng.

Ví dụ, runner:

~~~java
return args -> {
    backgroundExecutor.submit(this::loadEssentialData);
};
~~~

chỉ minh họa cách **khởi động** công việc nền (biến backgroundExecutor và method loadEssentialData chưa được định nghĩa trong mảnh này). Nó không đợi loadEssentialData kết thúc. Vì vậy ApplicationReadyEvent có thể đến khi tải dữ liệu vẫn đang chạy. Trong ứng dụng thực tế cần chính sách readiness, timeout, retry và xử lý failure.

## 10. Những trường hợp startup lỗi

### Bean @PostConstruct ném exception

Với một singleton eager được khởi tạo khi refresh, exception không được xử lý trong **@PostConstruct** thường làm bean creation thất bại và khiến context refresh thất bại. Khi đó Boot **không đạt ApplicationReadyEvent**; **ApplicationFailedEvent** có thể được phát.

### Runner ném exception

Bean và context có thể đã khởi tạo/refresh thành công, thậm chí **ApplicationStartedEvent** đã được phát. Nhưng runner lỗi thì Boot vẫn coi startup thất bại; ready event không được phát. Đây chính là nhánh kiểm thử ở mục 5.4.

### Bean lazy bị lỗi sau ready

Một bean lazy có cấu hình sai có thể chỉ gây lỗi khi được truy cập sau khi ứng dụng đã ready. Spring Boot Reference nêu rõ trade-off này của lazy initialization: giảm thời gian startup nhưng dời thời điểm phát hiện lỗi đến lúc bean được sử dụng.

### Resource bên ngoài mất kết nối sau ready

ApplicationReadyEvent là một mốc trong lịch sử startup, không phải một cam kết vĩnh viễn về trạng thái các dependency. Cần timeout, retry, circuit breaker (khi thích hợp), health/readiness và quan sát hệ thống vận hành liên tục.

## 11. Các hiểu nhầm và cách sửa

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| **“@PostConstruct của service chạy nghĩa là app đã ready.”** | Nó chỉ xác nhận một callback của service; toàn bộ startup còn nhiều bước |
| **“Constructor chạy xong tức là bean hoàn tất initialization.”** | Injection, init callbacks, BeanPostProcessors có thể còn tiếp diễn |
| **“Tất cả singleton khởi tạo xong là mọi bean đã tồn tại.”** | Lazy/prototype có thể tạo sau |
| **“ContextRefreshedEvent đồng nghĩa ApplicationReadyEvent.”** | Context refresh xảy ra trước Boot runners và ready |
| **“ApplicationStartedEvent nghĩa là có thể nhận traffic ngay.”** | Started xảy ra trước runners; readiness event đến sau ready |
| **“Port 8080 mở nghĩa là pod ready.”** | Port có thể bind trước runner hoàn tất; routing phụ thuộc readiness |
| **“Runner gọi async rồi return nghĩa là async job đã hoàn tất.”** | Runner chỉ đợi phần nó thực thi/chờ trực tiếp |
| **“ApplicationReadyEvent nghĩa là dependencies luôn khỏe.”** | Trạng thái runtime có thể suy giảm sau startup |
| **“Mọi @EventListener đều luôn hoàn tất đồng bộ.”** | Phụ thuộc cấu hình event multicaster và cách xử lý async |
| **“Nếu ready listener chạy thì ReadinessState đã ACCEPTING.”** | Trong lifecycle Boot, availability change này phát ngay **sau** ready event |
| **“Spring Boot tự biết trạng thái dịch vụ ngoài.”** | Health/readiness cho external dependencies cần thiết kế theo ngữ cảnh |

## 12. Kiểm tra và quan sát trên hệ thống thực

1. **Gắn log theo mốc phù hợp:** không chỉ log constructor hoặc @PostConstruct; quan sát thêm ContextRefreshedEvent, ApplicationStartedEvent, runner và ApplicationReadyEvent.
2. **Phân biệt startup thành công và vận hành khỏe:** startup event hỗ trợ xác nhận trình tự; health, metrics và traces cho thấy trạng thái về sau.
3. **Tìm task tốn thời gian trong startup:** đặt đo thời lượng ở runner hoặc dùng công cụ theo dõi **ApplicationStartup / StartupStep**. Với Actuator được cấu hình phù hợp, endpoint **startup** có thể hỗ trợ phân tích quá trình khởi tạo.
4. **Kiểm tra cấu hình lazy initialization:** property **spring.main.lazy-initialization=true** có thể làm nhiều bean chỉ được khởi tạo khi dùng; không dùng số lượng @PostConstruct làm điều kiện ready.
5. **Xác nhận readiness probe của nền tảng:** endpoint đúng, port đúng, timeout hợp lý, phân biệt liveness và readiness.
6. **Chẩn đoán failure cụ thể:** xem stack trace gốc của bean creation hay runner failure để biết sự cố ở đâu, thay vì chỉ nhìn thông điệp “Application run failed”.
7. **Đánh giá việc nền:** nếu runner tạo background job, kiểm tra hệ thống có đánh dấu ready trước khi điều kiện quan trọng được đáp ứng không.

## 13. Bài tập củng cố

**Câu 1.** Một bean đã log “@PostConstruct OK”, nhưng một bean khác không thể kết nối database khiến refresh thất bại. Ứng dụng có được coi là ready không? Vì sao?

**Câu 2.** ContextRefreshedEvent đã phát, rồi ApplicationRunner chạy 30 giây để tải dữ liệu. Trong 30 giây đó, event nào đã xảy ra và event nào chưa?

**Câu 3.** Tại sao ứng dụng có thể ready trước khi một bean @Lazy chạy constructor? Khi bean đó lỗi sau ready, ảnh hưởng gì đến điều tra startup?

**Câu 4.** Trong code mẫu, đổi **demo.fail-runner** thành true. Dự đoán những dòng số nào chắc chắn thuộc đường startup thành công trước khi lỗi, và vì sao không có dòng 07/08 bình thường.

**Câu 5.** Một runner chỉ submit task lên executor rồi trả về. Có thể dùng thời điểm ApplicationReadyEvent làm bằng chứng task đã xử lý xong không?

**Câu 6.** Vì sao không nên tự thêm external database vào liveness probe của mọi microservice? Khi nào readiness phụ thuộc database có ý nghĩa?

**Đáp án gợi ý:** (1) không, bean cục bộ hoàn tất không làm cả context thành công; (2) refresh và started đã xảy ra, ready chưa; (3) bean lazy chỉ được tạo lúc cần nên có thể lộ lỗi muộn; (4) constructor, @PostConstruct, SmartInitializingSingleton, ContextRefreshed, Started và runner chạy trước nhánh lỗi, còn Ready và run trả về thành công không xảy ra; (5) không, runner không đợi việc bất đồng bộ nếu không được lập trình để đợi; (6) lỗi DB có thể kích hoạt restart dây chuyền, trong khi readiness quyết định có nên tạm ngừng nhận traffic nếu DB là dependency bắt buộc.

## 14. Ghi nhớ và nguồn tham khảo

**Bean khởi tạo xong là mốc của một đối tượng do Spring quản lý. Application ready là mốc Spring Boot đã refresh context và hoàn thành các startup runners.** Giữa hai mốc còn có việc khởi tạo các bean khác, context lifecycle events và bước chuẩn bị cấp ứng dụng. Một bean lazy còn có thể khởi tạo **sau** ready.

Các mốc cần nhớ theo thứ tự:

~~~text
Bean initialization
    -> ContextRefreshedEvent
    -> ApplicationStartedEvent
    -> ApplicationRunner / CommandLineRunner
    -> ApplicationReadyEvent
    -> ReadinessState.ACCEPTING_TRAFFIC
~~~

Đây là thứ tự quan sát điển hình trong startup thành công với singleton non-lazy. Nó **không áp dụng cho mọi bean lazy/prototype**, cũng không thay thế việc theo dõi runtime health sau startup.

Tài liệu chính thức để đối chiếu theo phiên bản:

1. Spring Framework — Customizing the Nature of a Bean, initialization callbacks và SmartLifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
2. Spring Framework — Container Extension Points (BeanPostProcessor và BeanFactoryPostProcessor): https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
3. Spring Boot 3.5 — SpringApplication, application events, runners, lazy initialization: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
4. Spring Boot 3.5 — ApplicationStartedEvent API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html

Ví dụ được thiết kế cho **Spring Boot 3.5.x, Spring Framework 6.x và Java 17+**. Với Spring Boot 4.x hoặc thay đổi lớn về phiên bản Framework, cần đối chiếu các API và lifecycle event trong tài liệu đúng phiên bản trước khi tái sử dụng nguyên mã.