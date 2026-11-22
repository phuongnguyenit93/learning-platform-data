# SmartInitializingSingleton sau khi tạo singleton không trì hoãn

**Chủ đề:** Spring Boot Application Runtime → Vòng đời bean. Bài học giải thích chính xác vai trò của `SmartInitializingSingleton`, phương thức `afterSingletonsInstantiated()`, thời điểm Spring gọi callback sau khi hoàn tất giai đoạn pre-instantiation của các singleton thông thường, và các trường hợp callback **không** được gọi. Bài có ứng dụng Spring Boot chạy được, đối chứng với bean lazy, ví dụ khởi động lỗi và tiêu chí kiểm chứng qua log/HTTP.

**Nền tảng ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x và Spring MVC. Trong ứng dụng dùng phiên bản khác, đọc Javadoc tương ứng để xác nhận package, hợp đồng và thứ tự startup. `SmartInitializingSingleton` là interface **của Spring Framework**, không phải annotation của Spring Boot.

## 1. Khi nào cần SmartInitializingSingleton?

Trong một `ApplicationContext`, Spring giữ **bean definitions** mô tả cách tạo bean. Trong giai đoạn refresh, container thường khởi tạo sẵn các **singleton không lazy**: tạo object, giải quyết dependency, gọi các callback khởi tạo và áp dụng `BeanPostProcessor`. Đôi khi một bean cần làm công việc **sau khi toàn bộ nhóm singleton thông thường này đã qua quá trình tạo**, chẳng hạn xây một registry từ các bean khác.

Nếu làm việc đó trong constructor hoặc `@PostConstruct`, ta có thể gặp vấn đề: các singleton khác chưa được tạo và việc dò bean bằng `getBeansOfType(...)` có thể kích hoạt khởi tạo sớm ngoài ý muốn. `SmartInitializingSingleton` cung cấp mốc rõ hơn:

~~~java
package org.springframework.beans.factory;

public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
~~~

Khi bean singleton của bạn implement interface này và được tạo trong giai đoạn pre-instantiation, BeanFactory sẽ gọi `afterSingletonsInstantiated()` ở **cuối giai đoạn** đó. Tại mốc ấy, các **regular singleton beans** theo hợp đồng pre-instantiation đã được tạo; tra cứu các singleton đó an toàn hơn so với lúc bean riêng vừa được tạo.

Ý nghĩa đúng cần nhớ:

- **Đúng:** callback chạy **sau** việc khởi tạo các singleton thông thường, không lazy của vòng bootstrap BeanFactory.
- **Sai:** callback đảm bảo tất cả bean thuộc mọi scope đã được tạo.
- **Sai:** callback chỉ chạy sau khi HTTP server nhận request hoặc sau `ApplicationReadyEvent`.
- **Sai:** bean singleton `@Lazy` được tạo theo nhu cầu sau startup cũng tự được gọi callback này.
- **Sai:** implement interface đồng nghĩa Spring quản lý một tác vụ nền hoặc tự shutdown tác vụ đó.

Javadoc Spring Framework mô tả interface này như một callback **cuối giai đoạn singleton pre-instantiation** và khuyến nghị dùng `Lifecycle` nếu mục tiêu là start/stop các tác vụ bất đồng bộ.

## 2. Đặt callback vào đúng sơ đồ vòng đời

Xét một Spring Boot application khởi động bình thường:

~~~text
SpringApplication.run(args)
   |
   +-- tạo/chuẩn bị ApplicationContext và Environment
   +-- đăng ký bean definitions
   +-- refresh ApplicationContext
   |    |
   |    +-- BeanFactoryPostProcessor xử lý metadata
   |    +-- đăng ký BeanPostProcessor
   |    +-- preInstantiateSingletons() tại giai đoạn hoàn tất BeanFactory
   |    |    |
   |    |    +-- khởi tạo các singleton không lazy
   |    |    |     constructor/factory method
   |    |    |     dependency injection
   |    |    |     @PostConstruct, afterPropertiesSet, custom init
   |    |    |     BeanPostProcessor sau init/proxy nếu có
   |    |    |
   |    |    +-- sau vòng tạo: SmartInitializingSingleton
   |    |          afterSingletonsInstantiated()
   |    |
   |    +-- hoàn tất refresh, lifecycle processor
   |    +-- ContextRefreshedEvent
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   v
Ứng dụng ở trạng thái hoạt động
   |
   +-- về sau có thể tạo thêm lazy/prototype/request-scoped bean
~~~

`DefaultListableBeanFactory.preInstantiateSingletons()` là giai đoạn liên quan trực tiếp. Mốc `afterSingletonsInstantiated()` thuộc cuối pre-instantiation, vốn được gọi trong `finishBeanFactoryInitialization(...)` của `AbstractApplicationContext.refresh()`. Nó xảy ra **trước** `ContextRefreshedEvent` và trước các sự kiện started/ready của Spring Boot trong startup thông thường.

Lưu ý: đây là chuỗi khái niệm. Spring có thể tạo một số infrastructure bean sớm hơn và tạo bean theo dependency graph; không nên suy luận các bean luôn được khởi tạo theo thứ tự tên class hoặc thứ tự component scan. Với Spring Framework 6.2, một số bean cấu hình background bootstrap cũng có thể được khởi tạo theo cơ chế concurrency riêng, nhưng các singleton non-lazy thường vẫn được hoàn tất trong giai đoạn bootstrap trước khi callback hậu pre-instantiation.

## 3. So sánh với các callback khác

| Cơ chế | Thời điểm chính | Bảo đảm hữu ích | Không bảo đảm |
|---|---|---|---|
| Constructor hoặc factory method | Khi tạo **chính bean đó** | Có object mới và dependency constructor được giải quyết | Các bean khác đã hoàn tất init |
| `@PostConstruct` | Khi bean đó được init sau injection | Có thể chuẩn bị trạng thái nội bộ của bean | Toàn bộ singleton đã được tạo |
| `InitializingBean.afterPropertiesSet()` | Cuối initialization của chính bean | Property injection cần thiết đã xong | ApplicationContext đã refresh |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Cuối singleton pre-instantiation | Nhóm regular singleton đã được tạo | Lazy/prototype/request beans đã được tạo hoặc app đã ready |
| `ContextRefreshedEvent` | Khi context hoàn tất refresh | Context cụ thể đã refresh | Runners của Boot đã xong |
| `ApplicationRunner` / `CommandLineRunner` | Sau refresh, trước ready | Chạy logic cấp ứng dụng trước mốc ready | Có thể thay đổi những bean đã dùng trong startup mà không có rủi ro |
| `ApplicationReadyEvent` | Sau runners | Boot đã đi đến mốc ready | Mọi endpoint nghiệp vụ luôn đúng |
| `SmartLifecycle` | Startup/shutdown do LifecycleProcessor quản lý, có phase | Quản lý start/stop các tác vụ và dependency vận hành | Tương đương chỉ một callback tạo registry |

**Chọn `SmartInitializingSingleton` khi:** cần xây dựng tập đăng ký, bảng tra cứu hoặc kiểm tra quan hệ giữa các **singleton eager** sau khi chúng đã khởi tạo. Với một tác vụ dài, kết nối nền, scheduler cần dừng đúng cách, cân nhắc `SmartLifecycle`; với workflow cấp ứng dụng trước khi báo sẵn sàng, có thể dùng runner và readiness policy.

## 4. Mô hình bean nào thực sự nhận callback?

Spring mặc định tạo trước singleton không lazy khi refresh. Nhưng `scope` và `lazy-init` thay đổi hợp đồng:

| Kiểu bean | Tạo trong pre-instantiation? | `afterSingletonsInstantiated()`? |
|---|---|---|
| Singleton không lazy, implement interface | Thường có | Có, cuối giai đoạn pre-instantiation |
| Singleton không lazy, không implement interface | Thường có | Không có method để gọi |
| Singleton `@Lazy`, chỉ tạo **sau** bootstrap | Không | Không được gọi khi tạo muộn |
| Singleton `@Lazy` nhưng bị dependency eager yêu cầu tạo sớm | Có thể được tạo trước khi callback pass | Phụ thuộc thời điểm nó đã được tạo trong bootstrap; không dùng lazy làm ranh giới tuyệt đối |
| Prototype implement interface | Tạo theo từng lần yêu cầu | Không thuộc callback singleton pre-instantiation |
| Request/session-scoped bean | Theo vòng đời scope web tương ứng | Không thuộc callback pre-instantiation |
| Bean chưa tồn tại vì `@Conditional...` không khớp | Không có definition phù hợp | Không |
| Singleton được tạo theo nhu cầu **sau** giai đoạn bootstrap | Không được pre-instantiate | Không có lượt callback bổ sung cho lần tạo muộn |

Từ khóa **“không trì hoãn”** trong đề bài chính là singleton **non-lazy/eager**; không được hiểu thành “mọi singleton của toàn ứng dụng” bất kể thời điểm. `BeanFactory` có thể chứa bean definition lazy nhưng chưa có instance. Trong Spring Boot, tùy chọn `spring.main.lazy-initialization=true` thay đổi việc tạo trước nhiều bean; một `SmartInitializingSingleton` bị lazy theo cơ chế này có thể không được gọi trong vòng bootstrap.

**Ngoại lệ cần phân tích khi gặp thực tế:** một singleton được đánh dấu `@Lazy` nhưng được inject trực tiếp vào một singleton eager thì Spring có thể vẫn phải tạo nó sớm để đáp ứng dependency; sử dụng `ObjectProvider` hoặc injection-point `@Lazy` mới thực sự trì hoãn việc lấy instance theo nhu cầu thích hợp.

## 5. Ứng dụng mẫu chạy được: rule registry hoàn thành sau eager singleton

Ta tạo hai `ReadyRule`, một `RuleCatalog` implement `SmartInitializingSingleton`, một bean lazy có callback cùng interface để minh họa ngoại lệ, và một controller trả dữ liệu HTTP. Trong callback của catalog, ta thu thập các rule đã tạo và công bố trạng thái cho controller.

### 5.1. Tạo project

Từ **Spring Initializr**, tạo:

- Project: Maven; Java: 17; Spring Boot: 3.5.x.
- Group: `com.example`; Artifact: `smart-init-lab`; package: `com.example.smartinit`.
- Dependency: **Spring Web**.
- Packaging: Jar.

Giữ nguyên `pom.xml`, dependency và phiên bản plugin do Initializr tạo. Cấu trúc nguồn:

~~~text
smart-init-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/smartinit/
    SmartInitApplication.java
    ReadyRule.java
    AlphaRule.java
    BetaRule.java
    RuleCatalog.java
    DeferredProbe.java
    StatusController.java
  src/main/resources/application.properties
~~~

Các lớp `public` được đặt trong file có tên tương ứng và cùng package. Vì đây là ứng dụng Spring Boot có dependency bên ngoài, hãy build bằng Maven Wrapper; chỉ gọi `javac` trên một file không kèm classpath Spring sẽ báo thiếu package.

### 5.2. Main class và các dấu mốc Boot startup

File `SmartInitApplication.java`:

~~~java
package com.example.smartinit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class SmartInitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SmartInitApplication.class, args);
    }

    @Bean
    ApplicationRunner markerRunner(RuleCatalog catalog) {
        return args -> System.out.println(
                "LAB_RUNNER_READY=" + catalog.initialized());
    }

    @EventListener(ContextRefreshedEvent.class)
    public void contextRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void applicationStarted() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

`ApplicationRunner` nhận `RuleCatalog` như dependency để in trạng thái quan sát được. Trong startup bình thường, callback `SmartInitializingSingleton` phải hoàn thành **trước** khi runner thực thi. `ContextRefreshedEvent` chứng minh context refresh hoàn tất; `ApplicationStartedEvent` tới sau refresh nhưng trước runner; `ApplicationReadyEvent` sau runner.

### 5.3. Interface và hai bean eager

File `ReadyRule.java`:

~~~java
package com.example.smartinit;

public interface ReadyRule {
    String code();
}
~~~

File `AlphaRule.java`:

~~~java
package com.example.smartinit;

import org.springframework.stereotype.Component;

@Component
public final class AlphaRule implements ReadyRule {

    public AlphaRule() {
        System.out.println("LAB_ALPHA_CONSTRUCTED");
    }

    @Override
    public String code() {
        return "alpha";
    }
}
~~~

File `BetaRule.java`:

~~~java
package com.example.smartinit;

import org.springframework.stereotype.Component;

@Component
public final class BetaRule implements ReadyRule {

    public BetaRule() {
        System.out.println("LAB_BETA_CONSTRUCTED");
    }

    @Override
    public String code() {
        return "beta";
    }
}
~~~

Hai class là singleton theo scope mặc định và không có `@Lazy`. Do đó trong ví dụ đơn giản, chúng được Spring tạo trong refresh. **Không** khẳng định Alpha luôn được tạo trước Beta: thứ tự giữa hai bean không có dependency chỉ nên kiểm chứng bằng marker, không dùng làm hợp đồng nghiệp vụ.

### 5.4. RuleCatalog: callback sau khi các eager singleton đã được tạo

File `RuleCatalog.java`:

~~~java
package com.example.smartinit;

import java.util.List;
import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.ListableBeanFactory;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class RuleCatalog implements SmartInitializingSingleton {

    private final ListableBeanFactory beanFactory;
    private final boolean failOnSmart;
    private volatile List<String> codes = List.of();

    public RuleCatalog(
            ListableBeanFactory beanFactory,
            @Value("${lab.fail-on-smart:false}") boolean failOnSmart) {
        this.beanFactory = beanFactory;
        this.failOnSmart = failOnSmart;
        System.out.println("LAB_CATALOG_CONSTRUCTED");
    }

    @PostConstruct
    public void init() {
        System.out.println("LAB_CATALOG_POST_CONSTRUCT");
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, ReadyRule> beans =
                beanFactory.getBeansOfType(ReadyRule.class);

        List<String> discovered = beans.values()
                .stream()
                .map(ReadyRule::code)
                .sorted()
                .toList();

        if (discovered.size() != 2) {
            throw new IllegalStateException(
                    "LAB_RULE_COUNT_INVALID: " + discovered.size());
        }
        if (failOnSmart) {
            System.out.println("LAB_SMART_FAILURE_TRIGGERED");
            throw new IllegalStateException("LAB_SMART_INIT_FAILED");
        }

        this.codes = List.copyOf(discovered);
        System.out.println("LAB_SMART_DONE=" + String.join(",", codes));
    }

    public boolean initialized() {
        return !codes.isEmpty();
    }

    public List<String> codes() {
        return codes;
    }
}
~~~

**Giải thích cơ chế:**

1. `@Component` giúp Spring đăng ký bean `RuleCatalog`; chỉ implement interface mà không đăng ký bean thì callback sẽ **không tự chạy**.
2. `@PostConstruct` là mốc **riêng của RuleCatalog**, nên thường xuất hiện **trước** `LAB_SMART_DONE`. Nó không chứng minh Alpha/Beta đã được tạo.
3. `afterSingletonsInstantiated()` được Spring gọi sau vòng pre-instantiation. Trong đó `beanFactory.getBeansOfType(ReadyRule.class)` lấy các rule đã được đăng ký; theo Javadoc, thời điểm này giúp tránh tác dụng phụ của việc vô tình tạo các **regular singleton** quá sớm.
4. Ta sắp xếp mã rule bằng `sorted()` để kết quả ổn định mà không dựa vào thứ tự component scan hoặc thứ tự Map.
5. `volatile List<String> codes` công bố danh sách bất biến sau callback; ứng dụng có thể đọc sau đó. Với logic nhiều bước thay đổi liên tục, cần thiết kế đồng bộ hóa thích hợp thay vì chỉ thêm `volatile` tùy ý.
6. Tham số `lab.fail-on-smart` chỉ phục vụ thí nghiệm lỗi ở phần sau; mặc định là `false`. Nếu được bật, exception ném từ callback chặn startup trước khi context hoàn tất refresh.

Trong ứng dụng lớn, `getBeansOfType(...)` vẫn có thể tương tác với các definition mang semantics đặc biệt như lazy, `FactoryBean` hoặc scoped proxy. Javadoc bảo đảm tính hợp lý của mốc hậu singleton pre-instantiation, **không** cho phép tùy ý quét và khởi tạo mọi bean không cùng phạm vi. Hãy giới hạn kiểu cần dò, hiểu scope và tránh gọi lookup làm thay đổi trạng thái ngoài dự kiến.

### 5.5. Đối chứng: bean lazy implement interface nhưng không được gọi callback muộn

File `DeferredProbe.java`:

~~~java
package com.example.smartinit;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public final class DeferredProbe implements SmartInitializingSingleton {

    public DeferredProbe() {
        System.out.println("LAB_DEFERRED_CONSTRUCTED");
    }

    public String message() {
        return "created-on-demand";
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_DEFERRED_SMART_CALLBACK");
    }
}
~~~

Bean này được đánh dấu `@Lazy` và chỉ được controller lấy thông qua `ObjectProvider` khi request đặc biệt được gọi. Trong điều kiện không có bean eager nào khác ép tạo `DeferredProbe`, callback `afterSingletonsInstantiated()` **không** chạy lúc refresh vì bean chưa tồn tại. Khi bean được tạo theo nhu cầu sau refresh, Spring cũng **không chạy bù** callback này. Đây là khác biệt cốt lõi so với `@PostConstruct` hoặc `InitializingBean` vốn gắn với việc tạo chính bean đó.

### 5.6. Controller cho bằng chứng độc lập qua HTTP

File `StatusController.java`:

~~~java
package com.example.smartinit;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    private final RuleCatalog catalog;
    private final ObjectProvider<DeferredProbe> deferred;

    public StatusController(
            RuleCatalog catalog,
            ObjectProvider<DeferredProbe> deferred) {
        this.catalog = catalog;
        this.deferred = deferred;
    }

    @GetMapping("/status")
    public CatalogStatus status() {
        return new CatalogStatus(
                catalog.initialized(),
                catalog.codes());
    }

    @GetMapping("/deferred")
    public Map<String, String> deferred() {
        return Map.of("result", deferred.getObject().message());
    }

    public record CatalogStatus(boolean initialized, List<String> rules) {
    }
}
~~~

`/status` kiểm tra kết quả công bố từ callback; `/deferred` yêu cầu bean lazy lần đầu. `ObjectProvider<DeferredProbe>` ngăn controller phải tạo `DeferredProbe` ngay trong constructor của chính controller. `CatalogStatus` là Java record được Spring Web/Jackson tuần tự hóa thành JSON.

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=smart-init-lab
server.port=8080
lab.fail-on-smart=false
~~~

**Không cần gọi callback bằng tay.** Spring BeanFactory nhận ra interface ở bean singleton và điều phối tại đúng thời điểm.

## 6. Chạy thử và chứng minh thứ tự thực tế

### 6.1. Maven Wrapper

Tại thư mục `smart-init-lab`, trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

JDK và compiler phải đáp ứng Java 17. Nếu trên Windows `curl` là alias của PowerShell, dùng `curl.exe` cho ví dụ dưới đây.

### 6.2. Những marker cần nhìn thấy

Trong output thành công, các marker có quan hệ thứ tự quan trọng:

~~~text
LAB_ALPHA_CONSTRUCTED
LAB_BETA_CONSTRUCTED
LAB_CATALOG_CONSTRUCTED
LAB_CATALOG_POST_CONSTRUCT
LAB_SMART_DONE=alpha,beta
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_READY=true
LAB_APPLICATION_READY
~~~

**Đây là một trình tự minh họa hợp lệ, không phải log được bảo đảm nguyên từng dòng.** Hai rule và catalog có thể xuất hiện theo thứ tự khác nhau trước callback vì dependency graph và thứ tự tạo bean quyết định. Điều cần xác nhận là **mọi marker tạo rule và init của catalog xuất hiện trước `LAB_SMART_DONE`**, sau đó mới tới refresh/started/runner/ready. Timestamps, PID, thông báo Tomcat và dòng log khác cũng thay đổi.

Trong lần chạy mặc định, `LAB_DEFERRED_CONSTRUCTED` chưa xuất hiện; `LAB_DEFERRED_SMART_CALLBACK` cũng không xuất hiện.

### 6.3. Đọc HTTP response

Mở terminal khác khi server ở cổng 8080:

~~~bash
curl -i "http://localhost:8080/status"
~~~

Kỳ vọng HTTP 200 và nội dung JSON tương đương:

~~~json
{"initialized":true,"rules":["alpha","beta"]}
~~~

Có thể có header thêm và thứ tự property JSON tùy serializer. Trong ví dụ, body chứng minh callback đã xây catalog trước khi request được phục vụ sau ready. **Không** suy từ body rằng mọi dependency bên ngoài hệ thống đều khỏe; ứng dụng mẫu chỉ chứa rule nội bộ.

Tiếp tục:

~~~bash
curl -i "http://localhost:8080/deferred"
curl -i "http://localhost:8080/deferred"
~~~

Cả hai lần kỳ vọng trả HTTP 200 và:

~~~json
{"result":"created-on-demand"}
~~~

Sau request đầu tiên, console có:

~~~text
LAB_DEFERRED_CONSTRUCTED
~~~

Nhưng **không có**:

~~~text
LAB_DEFERRED_SMART_CALLBACK
~~~

Việc callback không xuất hiện là kết quả đúng theo hợp đồng: `SmartInitializingSingleton` chỉ được quét/gọi ở cuối pre-instantiation, không phát lại khi mỗi lazy singleton được tạo muộn. Muốn bean lazy có logic init **khi chính nó được tạo**, dùng `@PostConstruct` hoặc một cơ chế init khác phù hợp, không dùng callback này.

### 6.4. Chạy qua file JAR đã đóng gói

Dừng phiên Maven đang nghe cổng, rồi chạy:

~~~bash
./mvnw clean package
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar
~~~

Trên Windows dùng `./mvnw.cmd clean package` để build. Nếu artifact version khác `0.0.1-SNAPSHOT`, lấy đúng tên JAR trong `target/` thay vì dùng tên minh họa. Khi JAR hoạt động, gọi lại `/status`, `/deferred` và đối chiếu các marker. Không chạy đồng thời hai phiên trên cùng cổng.

## 7. Vì sao getBeansOfType(...) ở callback này an toàn hơn gọi trong PostConstruct?

Hãy tưởng tượng `RuleCatalog` muốn tìm tất cả `ReadyRule` bằng:

~~~java
beanFactory.getBeansOfType(ReadyRule.class);
~~~

Nếu gọi từ `RuleCatalog.@PostConstruct`, container có thể còn đang tạo các singleton khác. Một truy vấn “tìm mọi bean cùng loại” lúc đó có khả năng kéo theo khởi tạo sớm, làm thay đổi đồ thị thời điểm init hoặc khiến bean phụ thuộc vào thành phần chưa sẵn sàng.

Trong `afterSingletonsInstantiated()`, Spring đã đi hết pre-instantiation của các **regular singleton** nên các đối tượng cần thiết thuộc nhóm này đã được tạo. Vì vậy đây là một chỗ tốt để tạo bảng mapping plugin → bean, handler → strategy, hoặc thu thập metadata từ các singleton. Tuy nhiên:

- Nếu muốn duyệt **đúng một tập dịch vụ cố định**, constructor injection `List<ReadyRule>` có thể là giải pháp đơn giản, dễ type-safe; thời điểm chạy callback vẫn hữu ích nếu quá trình kết hợp cần đợi các singleton hoàn tất.
- Không tự gọi `getBeansOfType(Object.class)` trên toàn BeanFactory rồi mong mọi thứ đều an toàn; nhiều loại bean và factory có semantics riêng.
- Không giả định `getBeansOfType` chỉ trả non-lazy khi default lookup đi qua cả definition đặc biệt; hiểu chính sách lookup và thiết kế interface cần quét đủ cụ thể.
- Không dựa vào thứ tự Map trả về nếu kết quả nghiệp vụ cần thứ tự; dùng `@Order`/`Ordered` hoặc sắp xếp theo key có quy tắc.
- Một số bean có thể là proxy: nếu gọi method interface để lấy metadata, method đó có thể bị advice; tránh đặt I/O và side effect khó kiểm soát vào bước lập catalog.

Một ứng dụng plugin system đôi khi dùng `Map<String, Handler>` được Spring inject trực tiếp thay vì truy vấn BeanFactory. Khi không có yêu cầu mốc hậu pre-instantiation, không cần thêm `SmartInitializingSingleton` chỉ vì có nhiều handler.

## 8. So sánh @PostConstruct, InitializingBean và SmartInitializingSingleton

Một singleton có thể implement cả `InitializingBean` và `SmartInitializingSingleton`:

~~~java
@Component
class ExampleBean implements InitializingBean, SmartInitializingSingleton {

    @PostConstruct
    void postConstruct() {
        System.out.println("POST_CONSTRUCT");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("AFTER_PROPERTIES_SET");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("AFTER_ALL_REGULAR_SINGLETONS");
    }
}
~~~

**Đây là snippet cần đặt trong project có Spring imports và class thích hợp**, không phải file `ExampleBean.java` hoàn chỉnh độc lập. Thứ tự điển hình cho bean eager:

~~~text
POST_CONSTRUCT
AFTER_PROPERTIES_SET
AFTER_ALL_REGULAR_SINGLETONS
~~~

`@PostConstruct` được gọi bởi post-processor liên quan trong bước init bean; `InitializingBean.afterPropertiesSet()` gọi tại bước initialization của **chính bean**; `SmartInitializingSingleton` lại chạy sau pre-instantiation **toàn tập regular singleton**. Nếu bean này được lazy tạo sau bootstrap, hai callback đầu vẫn có thể chạy ở thời điểm tạo bean, còn callback cuối không được gọi bù.

Phân biệt `SmartInitializingSingleton` với `SmartLifecycle`: tên đều bắt đầu bằng “Smart” nhưng mục tiêu khác nhau. `SmartLifecycle` có trạng thái running, `start()`, `stop()`, phase và auto-startup, phù hợp các consumer/task dài có start/stop; callback ở đây chỉ là mốc **khởi tạo registry/singleton** một lần trong bootstrap.

## 9. Phân biệt callback với ContextRefreshedEvent

Hai cách đều có thể được dùng cho logic “sau nhiều bean đã có”, nhưng khác hợp đồng:

### SmartInitializingSingleton

- Thuộc module `spring-beans`, không cần một `ApplicationContext` có event publisher.
- Có thể được gọi bởi `ListableBeanFactory` thích hợp thực hiện `preInstantiateSingletons()`.
- Gắn với **singleton pre-instantiation**, không phải event refresh.
- Không cần lọc context hierarchy hoặc kiểm tra event có đến từ child context hay không.
- Không chạy lại chỉ vì một listener nhận thêm `ContextRefreshedEvent` hoặc có bean lazy mới.

### ContextRefreshedEvent

- Thuộc event system của `ApplicationContext`.
- Phát sau khi context hoàn tất refresh.
- Với hierarchy parent/child, event của context con có thể được truyền lên context cha; listener muốn đúng context phải lọc `event.getApplicationContext()`.
- Một số context hỗ trợ nhiều lần refresh hoặc các context được tạo lại, nên event có thể xuất hiện nhiều lần trong lifecycle tổng thể.
- Phù hợp khi cần phản ứng ở mức context đã refresh và event architecture, chứ không chỉ pre-instantiation của bean factory.

**Quy tắc lựa chọn:** muốn một callback bean-level cuối pre-instantiation, chọn `SmartInitializingSingleton`. Muốn quan sát context đã refresh và có event handling rõ ràng, cân nhắc `ContextRefreshedEvent`. Muốn thực hiện công việc cấp ứng dụng sau refresh nhưng trước ready, dùng `ApplicationRunner` hoặc `CommandLineRunner`.

## 10. Thí nghiệm 1 — Cho callback ném exception

Code của `RuleCatalog` đã có nhánh `lab.fail-on-smart`. Dừng ứng dụng tốt ở cổng 8080, đảm bảo JAR đã build, rồi chạy:

~~~bash
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar --lab.fail-on-smart=true
~~~

Khi Spring gọi `afterSingletonsInstantiated()`, nhánh lỗi in:

~~~text
LAB_SMART_FAILURE_TRIGGERED
~~~

Sau đó ném `IllegalStateException` mang chuỗi `LAB_SMART_INIT_FAILED`. Kỳ vọng:

1. Stack trace báo nguyên nhân liên quan `LAB_SMART_INIT_FAILED`; lớp exception bọc ngoài tùy stack.
2. Bean constructors và init callback của nhiều singleton có thể đã chạy.
3. **Không có** `LAB_SMART_DONE=alpha,beta` vì callback không hoàn thành.
4. **Không có** các marker `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_READY=true` hoặc `LAB_APPLICATION_READY` của lần startup thất bại.
5. Spring Boot kết thúc startup với lỗi; ứng dụng không được coi là ready. Một số web infrastructure có thể đã được khởi tạo trước đó nhưng Spring sẽ cố thực hiện cleanup trong quá trình hủy startup.

Đây là **startup failure xảy ra bên trong pre-instantiation**, khác với lỗi lúc controller xử lý request. Nếu callback là phần kiểm chứng cấu hình bắt buộc, việc ném exception có thể là chính sách đúng để chặn app phục vụ sai trạng thái. Nếu lỗi chỉ tạm thời và công việc nên retry, cần thiết kế retry/timeout và readiness phù hợp; không làm vòng lặp vô hạn trong callback.

Chạy lại mà không truyền cờ lỗi hoặc dùng `--lab.fail-on-smart=false` để xác nhận startup trở lại bình thường.

## 11. Thí nghiệm 2 — Đổi global lazy initialization

Với một bản chạy riêng, thử:

~~~bash
java -jar target/smart-init-lab-0.0.1-SNAPSHOT.jar --spring.main.lazy-initialization=true
~~~

Không áp đặt kết quả theo số marker cố định, vì bean nào vẫn được hạ tầng cần sớm phụ thuộc cấu hình và phiên bản. Nhưng nguyên lý quan trọng là: một bean implement `SmartInitializingSingleton` chỉ được gọi trong callback sweep nếu nó đã tồn tại đúng trong giai đoạn pre-instantiation. Bean bị tạo muộn do global lazy có thể **không nhận callback**.

Trong project này, `ApplicationRunner` cần `RuleCatalog`, nên framework có thể phải tạo catalog khi tìm và chạy runner **sau refresh** trong chế độ global lazy. Khi đó catalog có constructor và `@PostConstruct`, nhưng callback hậu pre-instantiation đã qua; runner có thể in:

~~~text
LAB_RUNNER_READY=false
~~~

và `/status` có thể trả `initialized=false` với mảng rỗng, vì không có ai gọi callback bù. Đây là ví dụ giúp nhận ra global lazy có thể phá một thiết kế phụ thuộc callback eager. Kết quả thực tế cần đối chiếu marker ở chính bản ứng dụng và phiên bản đang dùng.

Nếu catalog là thành phần **bắt buộc** phải dựng trước ready, cần đảm bảo bean và các dependency cần thiết được bootstrap ở thời điểm phù hợp, hoặc chuyển logic sang một lifecycle phase có hợp đồng rõ hơn cho global lazy (ví dụ runner phối hợp khởi tạo tường minh với kiểm soát thứ tự). Không nên gọi thủ công `afterSingletonsInstantiated()` một cách tùy tiện để “vá” chế độ lazy, vì nó biến callback container thành phương thức nghiệp vụ có thể bị gọi lặp.

## 12. Thí nghiệm 3 — Prototype và request scope

`SmartInitializingSingleton` không phải “mọi bean sau khi nó được tạo”. Để kiểm tra, trong **bản copy lab**, thêm snippet bean prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PrototypeProbe implements SmartInitializingSingleton {

    public PrototypeProbe() {
        System.out.println("LAB_PROTOTYPE_CONSTRUCTED");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("LAB_PROTOTYPE_SMART");
    }
}
~~~

Snippet cần các import `org.springframework.context.annotation.Scope`, `org.springframework.beans.factory.config.ConfigurableBeanFactory`, `org.springframework.stereotype.Component` và `org.springframework.beans.factory.SmartInitializingSingleton`. Đặt trong một class/file riêng trong package scan. Nếu bạn lấy bean prototype bằng `ObjectProvider<PrototypeProbe>.getObject()`, constructor chạy mỗi lần tạo mới nhưng `LAB_PROTOTYPE_SMART` không được BeanFactory gọi theo vòng callback pre-instantiation.

Với `@RequestScope`, mỗi request có thể nhận một instance riêng; nó cũng không thuộc sweep cuối eager singleton. Những callback gắn với lifecycle của chính bean như `@PostConstruct` phù hợp hơn cho từng instance theo scope, và cleanup cần theo hợp đồng scope cụ thể.

Không nhầm singleton **được truy cập lần đầu sau startup** với prototype: singleton lazy thường vẫn chỉ tạo một instance trong context, nhưng `SmartInitializingSingleton` của nó không nhận callback muộn.

## 13. Mẫu thiết kế thực tế: Registry của nhiều strategy singleton

Một trường hợp dùng callback hợp lý là hệ thống có nhiều strategy eager và cần xây bảng tra cứu một lần, tránh khởi tạo ngẫu nhiên trong bean constructor:

~~~java
@Override
public void afterSingletonsInstantiated() {
    Map<String, MyStrategy> beans =
            beanFactory.getBeansOfType(MyStrategy.class);

    Map<String, MyStrategy> byCode = new HashMap<>();
    for (MyStrategy strategy : beans.values()) {
        MyStrategy old = byCode.putIfAbsent(strategy.code(), strategy);
        if (old != null) {
            throw new IllegalStateException(
                    "Duplicate strategy code: " + strategy.code());
        }
    }
    this.registry = Map.copyOf(byCode);
}
~~~

Đây là **đoạn method minh họa** đặt trong class đã có `beanFactory`, `registry` và các import tương ứng; không phải chương trình độc lập. Một thiết kế tốt:

- Giới hạn kiểu bean được dò để không kích hoạt tác dụng phụ ngoài ý muốn.
- Đảm bảo registry không bị biến đổi sau công bố, hoặc đồng bộ hóa rõ ràng nếu cần cập nhật runtime.
- Kiểm tra mã strategy trùng lặp ngay trong startup để lỗi hiện ra sớm.
- Không lưu những bean prototype/request scope như các singleton dùng chung lâu dài.
- Khi không có lý do yêu cầu “sau tất cả singleton”, constructor injection `List<MyStrategy>` thường gọn hơn.
- Nếu strategy phụ thuộc data source, message broker hoặc I/O bên ngoài, cần quản lý readiness/retry/timeout riêng. Callback này không thay thế health check.

**Độ tin cậy khi triển khai:** nếu ứng dụng dựa vào việc gọi callback để xây trạng thái quan trọng, hãy kiểm thử cả cấu hình lazy, conditional beans, parent/child contexts và startup failures. Đừng dựa vào một cờ boolean tự đặt mà thiếu bằng chứng nghiệp vụ.

## 14. Startup time, asynchronous work và thread safety

Callback `afterSingletonsInstantiated()` thường chạy đồng bộ trong luồng bootstrap. Công việc kéo dài ở đây sẽ kéo dài `ApplicationContext.refresh()` và có thể chặn mốc ready. Các thao tác CPU nhẹ như dựng bảng tra cứu, validate schema nội bộ, kiểm tra trùng khóa thường phù hợp; truy vấn mạng không timeout, sleep dài hoặc polling vô hạn thường không phù hợp.

Nếu cần khởi động tác vụ nền, tài liệu Spring khuyến nghị xem `Lifecycle`/`SmartLifecycle` để quản lý cả start và stop. Một background consumer cần được dừng khi context đóng; interface callback đơn lẻ không có `stop()`. Nếu cần phát trạng thái sẵn sàng theo dependency, phải thiết kế readiness đúng thay vì chỉ tự in “initialized”.

Dữ liệu sẽ được nhiều thread HTTP đọc có thể lưu trong immutable collection, `final` field đã dựng trong constructor, hoặc công bố qua `volatile`/atomic reference nếu hình thành sau constructor. Trong ví dụ, `codes` là `volatile` và gán một immutable list sau callback; đủ để minh họa visibility của tham chiếu. Không suy ra một chuỗi thao tác nhiều trường sẽ atomic chỉ nhờ một biến volatile.

Nếu callback ném exception, bean khác có thể đã thực hiện init side effect. Spring cố cleanup context nhưng không bảo đảm rollback mọi thao tác với file, database hay hệ thống bên ngoài. Các tác vụ khởi tạo phải idempotent khi có khả năng ứng dụng restart nhiều lần.

## 15. Chẩn đoán các lỗi phổ biến

| Hiện tượng | Giả thuyết hợp lý | Cách kiểm tra |
|---|---|---|
| Không thấy `afterSingletonsInstantiated()` | Class không phải Spring-managed bean; bean lazy; bean không phải singleton; context chưa hoàn tất bootstrap | Kiểm tra `@Component`/`@Bean`, scope, lazy flag và stack trace |
| Có constructor nhưng thiếu callback | Bean được tạo sau pre-instantiation, thường do lazy | So thời điểm marker constructor với `ContextRefreshedEvent`; xem ai gọi `getBean` |
| Callback chạy trước một bean lazy khác | Hoàn toàn có thể đúng | Kiểm tra bean lazy có bị eager dependency yêu cầu không |
| Callback báo số rule không như mong đợi | `@Conditional`, component scan, profile, hoặc implementation thiếu/trùng | In bean names của đúng interface; xem điều kiện và package scan |
| Nhìn thấy `@PostConstruct` rồi coi catalog đã hoàn tất | Hai mốc khác nhau | Kiểm tra `LAB_SMART_DONE` và HTTP `/status` |
| Startup lỗi `LAB_SMART_INIT_FAILED` | Exception từ callback trong refresh | Đọc `Caused by`, cờ `lab.fail-on-smart`, trạng thái trước ready |
| App báo started nhưng API trả sai | Không phải mọi kết quả nghiệp vụ được chứng minh bởi event | Đối chiếu JSON, bean dependencies, request path |
| Bật global lazy thì callback không chạy | Bean bị tạo sau singleton bootstrap | So marker với runner; thiết kế eager hoặc lifecycle phù hợp |
| Dùng callback để start thread nhưng thread không dừng | Interface không có shutdown contract | Chuyển sang `SmartLifecycle` hoặc quản lý resource bằng destroy callback phù hợp |
| Parent/child context cho kết quả trùng | Mỗi BeanFactory có pre-instantiation của riêng nó | Ghi context identity, xác định bean thuộc context nào |
| Hai bean implement callback nhưng log thứ tự ngược | Không nên dựa vào thứ tự callback không được quy định cho nghiệp vụ | Biểu diễn dependency/lifecycle ordering bằng cơ chế rõ ràng |
| Bean được tạo sau bootstrap rồi gọi callback bằng tay | Nguy cơ chạy hai logic hoặc bỏ qua invariant của container | Chọn hook đúng thời điểm, không biến callback thành public operation |
| Registry bị request đọc khi chưa xây xong | Startup/lazy policy không phù hợp hoặc thiết kế concurrency yếu | Kiểm tra readiness và immutable publication |

**Lỗi thiết kế đáng chú ý:** dùng `SmartInitializingSingleton` như một hình thức `@PostConstruct` “an toàn hơn” cho mọi bean. Điều đó sai về scope và timing. Với prototype/lazy tạo muộn, callback không được gọi; với singleton eager, callback có thể bị chặn nếu một bean khác lỗi trước khi bootstrap hoàn tất.

## 16. Bảng kiểm thử và tiêu chí nghiệm thu

Thực hành theo trình tự dưới đây:

| Thử nghiệm | Đầu vào/trigger | Quan sát cần ghi | Kết luận đúng |
|---|---|---|---|
| Mặc định | `./mvnw spring-boot:run` | Rule constructors và catalog init trước `LAB_SMART_DONE` | Callback sau eager singleton bootstrap |
| Event startup | Theo dõi marker | `LAB_SMART_DONE` trước context refreshed và started/ready | Callback nằm trong refresh |
| API hoạt động | `GET /status` | 200, `initialized=true`, `alpha/beta` | Registry đã được dựng |
| Lazy bean | `GET /deferred` lần đầu | Constructor lazy xuất hiện sau startup; không có smart callback | Callback không chạy bù |
| Lỗi startup | `--lab.fail-on-smart=true` | Exception marker, không có ready | Callback failure chặn refresh |
| Global lazy | `--spring.main.lazy-initialization=true` | Thời điểm tạo catalog và callback có thể thay đổi | Không dựa callback nếu bean bị trì hoãn |
| Prototype | Yêu cầu một bean prototype implement interface | Constructor chạy, callback không được gọi | Scope khác singleton không thuộc sweep |

Mỗi thử nghiệm nên lưu: phiên bản JDK/Spring Boot; lệnh chạy; các dòng marker có timestamp; HTTP status và body (nếu có); exception gốc; câu giải thích ngắn tại sao có hoặc không có callback. Log marker do chúng ta tự đặt **không** phải log built-in của framework.

### Câu hỏi tự kiểm tra

**1. Tại sao `afterSingletonsInstantiated()` không tương đương `@PostConstruct`?** Vì `@PostConstruct` chạy khi **chính bean** được khởi tạo, còn callback Smart chạy cuối giai đoạn tạo **các regular singleton**.

**2. Có nên viết service singleton `@Lazy` rồi kỳ vọng callback tự chạy khi request đầu tiên gọi service?** Không. Bean lazy tạo muộn sẽ không được gọi `afterSingletonsInstantiated()` theo sweep trước đó.

**3. Bean eager implement interface, nhưng startup của một bean khác thất bại trước khi pre-instantiation hoàn tất thì sao?** Không có bảo đảm callback của nó đã được gọi. Startup thất bại không được xem là đạt mốc này.

**4. Có phải `ContextRefreshedEvent` xảy ra trước callback?** Không trong luồng refresh tiêu chuẩn: sweep Smart nằm ở phần hoàn tất BeanFactory trước `finishRefresh()` phát event.

**5. Nếu cần start/stop một worker nền, dùng interface này có đủ không?** Không. Cần `Lifecycle`/`SmartLifecycle` và chính sách shutdown hoặc tương đương để có cặp start/stop.

**6. `getBeansOfType(...)` trong callback có tự động bảo đảm không bao giờ tạo bất kỳ bean lazy nào không?** Không. Hợp đồng chỉ cho điểm mốc ổn định sau regular singleton pre-instantiation; lookup vẫn cần hiểu phạm vi loại bean và semantics của những definition đặc biệt.

**7. Vì sao nên sắp xếp các code rule ở ví dụ?** Vì thứ tự tạo bean và thứ tự Map không nên là giả định nghiệp vụ. `sorted()` cho kết quả JSON dễ đối chiếu.

**8. Có nên gọi `afterSingletonsInstantiated()` trực tiếp trong controller khi catalog chưa sẵn sàng?** Không. Cách đó bỏ qua vòng đời container và có thể làm lặp side effect; cần sửa policy khởi tạo và readiness.

**9. `ApplicationRunner` chạy trước hay sau callback trong startup bình thường?** Sau, vì runner của Boot chạy sau context refresh.

**10. Callback có thể chạy trong một BeanFactory không dùng ApplicationContext events không?** Có, interface thuộc `spring-beans` và được các `ListableBeanFactory` triển khai bootstrap thích hợp tôn trọng, không phụ thuộc riêng hệ thống event của `ApplicationContext`.

## 17. Checklist hoàn thành bài

- [ ] Giải thích được `SmartInitializingSingleton` thuộc Spring Framework và được callback vào cuối singleton pre-instantiation.
- [ ] Chỉ ra vị trí callback trong `finishBeanFactoryInitialization` và trước `ContextRefreshedEvent`.
- [ ] Phân biệt bean definition, eager singleton, lazy singleton, prototype và request scope.
- [ ] Viết được Spring bean implement `SmartInitializingSingleton` và thấy callback chạy đúng một lần trong bootstrap thành công.
- [ ] So thứ tự `@PostConstruct`, smart callback, context refreshed, runner và ready.
- [ ] Dựng/running project Java 17 và Spring Boot 3.5.x với Maven Wrapper.
- [ ] Gọi được `GET /status` và kiểm chứng registry được xây từ hai `ReadyRule`.
- [ ] Gọi được `GET /deferred` và chứng minh bean lazy không nhận callback muộn.
- [ ] Gây lỗi có kiểm soát trong callback và phân tích startup failure.
- [ ] Mô tả tác động của global lazy initialization lên hợp đồng callback.
- [ ] Chọn đúng hook cho việc khởi tạo nội bộ, registry, công việc cấp ứng dụng và tác vụ nền có stop.
- [ ] Nêu giới hạn của `getBeansOfType`, callback ordering, concurrency và cleanup sau startup lỗi.

## 18. Tài liệu chính thức

- Spring Framework 6.2 — Javadoc `SmartInitializingSingleton`: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework 6.2 — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Framework — Lazy initialization: https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Application startup steps (`spring.beans.smart-initialize`): https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html
- Spring Boot 3.5 — Application events/runner: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html

Mục tiêu cuối cùng của bài là có **bằng chứng tái lập** cho ranh giới vòng đời: các singleton eager được tạo trước callback, callback hoàn tất trước context refreshed, còn bean lazy tạo sau bootstrap không được gọi callback Smart thêm một lượt. Đọc đúng ranh giới này sẽ giúp thiết kế code khởi tạo registry và dịch vụ đáng tin cậy hơn khi cấu hình ứng dụng thay đổi.