# Cơ chế lazy proxy và bộ nhớ đệm target của @RefreshScope

Trong ứng dụng Spring Cloud, một bean có thể giữ cấu hình tại thời điểm được khởi tạo. Khi cấu hình thay đổi, việc chỉ cập nhật Environment chưa chắc thay đổi được đối tượng đang chạy: bean có thể vẫn giữ giá trị đã bind từ trước, một kết nối đã được tạo theo URL cũ hoặc một client đã lưu endpoint cũ.

`@RefreshScope` giải quyết nhóm trường hợp này bằng một **scoped proxy** và một **bộ nhớ đệm target**. Thành phần khác trong ứng dụng giữ tham chiếu đến proxy ổn định; proxy lấy target hiện tại từ scope khi có lời gọi. Khi refresh, Spring Cloud hủy target đang được cache. Lần gọi tiếp theo qua proxy sẽ tạo một target mới từ bean definition và nạp lại cấu hình hiện hành.

Bài học thuộc chương **Refresh Scope** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào cách proxy chuyển lời gọi, cách cache lưu target, vòng đời trước và sau refresh, cách quan sát bằng ví dụ Java và kiểm thử hành vi thay target mà không thay proxy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `@RefreshScope` dùng scoped proxy thay cho việc thay mọi tham chiếu bean trong toàn bộ application context.
- Phân biệt **proxy**, **target bean**, **bean definition** và **target cache**.
- Mô tả quá trình tạo target lần đầu, tái sử dụng target và hủy target khi refresh.
- Phân biệt `RefreshScope.refresh(beanName)` với `RefreshScope.refreshAll()`.
- Nhận biết vì sao target được tạo lại khi lời gọi kế tiếp đi qua proxy.
- Viết một bean `@RefreshScope` và một singleton sử dụng proxy đó.
- Kiểm thử rằng proxy giữ nguyên identity trong khi target được thay mới và nhận cấu hình mới.
- Nhận diện các giới hạn về bean phụ thuộc, constructor binding, HikariDataSource, AOT/native image và thao tác đồng thời.

### 1.1. Dependency cần có

`@RefreshScope` thuộc module `spring-cloud-context`. Nếu ứng dụng đã dùng một starter Spring Cloud có kéo module này vào classpath, hãy kiểm tra dependency graph trước khi khai báo thêm. Nếu chỉ cần Context và refresh scope, có thể khai báo trực tiếp:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Phiên bản được quản lý bởi `spring-cloud-dependencies` BOM tương thích với dòng Spring Boot của ứng dụng. Không tự chọn một version Context khác release train đang dùng. Nếu muốn gọi `/actuator/refresh` qua HTTP, thêm `spring-boot-starter-actuator` và cấu hình exposure/security cho endpoint.

## 2. Bốn thành phần của cơ chế

### 2.1. Bean definition

Bean definition là mô tả Spring dùng để tạo bean: class, constructor, dependency, property, init method, destroy method và các metadata khác. Với `@RefreshScope`, bean definition được đăng ký vào scope có tên `refresh`.

Ví dụ:

~~~java
@Component
@RefreshScope
public class GreetingTarget {
    // ...
}
~~~

`@RefreshScope` là annotation tiện ích, tương đương với khai báo scope `refresh` và scoped proxy. Mặc định proxy mode là `TARGET_CLASS`, tức Spring tạo proxy dựa trên class của bean.

### 2.2. Proxy

Proxy là đối tượng được inject vào những bean khác. Các bean gọi phương thức trên proxy như gọi bean bình thường. Proxy chặn lời gọi, tra cứu target hiện tại trong scope và chuyển tiếp lời gọi tới target đó.

Proxy không phải target. Nó có thể tồn tại trong suốt vòng đời application context, kể cả khi target phía sau đã bị hủy và được tạo lại nhiều lần.

### 2.3. Target bean

Target là instance thực hiện nghiệp vụ. Nó được tạo từ bean definition, được inject dependency và chạy các callback khởi tạo như `@PostConstruct` hoặc `InitializingBean`.

Target có thể giữ trạng thái nội bộ, giá trị `@Value`, client hoặc tài nguyên đã được tạo theo cấu hình. Khi target bị refresh, instance cũ bị hủy và instance mới được tạo khi cần.

### 2.4. Target cache

`RefreshScope` lưu các target đã khởi tạo trong cache theo tên bean scoped target. Khi proxy cần target, scope kiểm tra cache:

- Có target hợp lệ: trả lại target đang được cache.
- Chưa có target: tạo target từ bean definition, khởi tạo và lưu vào cache.
- Target đã bị invalidate: tạo target mới khi có lần truy cập tiếp theo.

Cache này giữ **instance bean theo tên trong application context**. Nó không phải cache kết quả của từng phương thức, không phải cache theo HTTP request và không phải một cache dùng chung giữa nhiều JVM.

## 3. Sơ đồ proxy và target cache

~~~mermaid
flowchart TD
    A[Singleton service] --> P[Refresh scoped proxy]
    P --> L[Resolve target from RefreshScope]
    L --> C{Target cache has entry?}
    C -->|Yes| T1[Current target]
    C -->|No| B[Create from bean definition]
    B --> I[Inject dependencies and initialize]
    I --> S[Store target in cache]
    S --> T2[New target]
    T1 --> M[Invoke method]
    T2 --> M
    R[refresh or refreshAll] --> D[Destroy and remove cached target]
    D --> C
~~~

Khi refresh, Spring Cloud xóa entry trong cache và thực hiện callback hủy của target cũ. Proxy vẫn là đối tượng mà singleton đang giữ. Lần gọi phương thức kế tiếp đi qua proxy sẽ không tìm thấy target cũ, nên scope tạo target mới.

### 3.1. Luồng tạo target lần đầu

Giả sử `GreetingController` là singleton và inject `GreetingTarget`:

1. Spring tạo bean proxy để đăng ký dưới tên `greetingTarget`.
2. `GreetingController` nhận proxy này trong constructor.
3. Khi controller gọi `greetingTarget.render()`, proxy hỏi `RefreshScope` lấy target.
4. Nếu cache chưa có target, scope dùng bean definition để tạo instance.
5. Spring inject dependency, bind giá trị cấu hình và chạy lifecycle callback.
6. Scope lưu target vào cache rồi chuyển lời gọi `render()` tới target.
7. Những lần gọi sau tiếp tục dùng target đang cache.

Điểm cần nhớ: proxy có thể được tạo trong quá trình khởi động context, nhưng target của refresh scope được quản lý theo ngữ nghĩa lazy. Việc lấy proxy không đồng nghĩa đã khởi tạo target; target được lấy hoặc tạo khi scope cần phục vụ lời gọi.

### 3.2. Luồng refresh target

Khi có refresh:

1. Cấu hình mới phải được đưa vào Environment theo cơ chế cập nhật đang dùng.
2. `RefreshScope` invalidate target cache cho một bean hoặc toàn bộ scope.
3. Target cũ được hủy và các callback hủy đã đăng ký được thực thi.
4. Proxy vẫn được inject trong các singleton như trước.
5. Khi có lời gọi tiếp theo, proxy yêu cầu target từ scope.
6. Scope tạo target mới từ bean definition; placeholder và expression được đánh giá lại, dependency được inject lại và callback khởi tạo chạy.

Refresh không chủ động tạo tất cả target mới ngay tại thời điểm xóa cache. Việc tạo lại diễn ra khi bean được truy cập tiếp theo. Nếu một bean không được dùng sau refresh, target mới có thể chưa được tạo.

## 4. Ví dụ Java: theo dõi identity của proxy và target

Ta xây dựng `GreetingTarget` với một ID tăng dần. Mỗi lần target được tạo, `@PostConstruct` ghi log; khi target bị hủy, `@PreDestroy` ghi log.

### 4.1. Bean có refresh scope

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class GreetingTarget {

    private static final Logger log =
            LoggerFactory.getLogger(GreetingTarget.class);

    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    private final int targetId = SEQUENCE.incrementAndGet();

    @Value("${greeting.message:Hello}")
    private String message;

    @PostConstruct
    public void initialize() {
        log.info("Create GreetingTarget id={}, message={}",
                targetId, message);
    }

    @PreDestroy
    public void destroy() {
        log.info("Destroy GreetingTarget id={}", targetId);
    }

    public String render() {
        return "target-" + targetId + ": " + message;
    }
}
~~~

Lớp không được khai báo `final` vì annotation mặc định tạo class-based proxy. Phương thức được gọi qua proxy phải có thể được proxy intercept theo kiểu proxy đã chọn. Nếu thiết kế bean theo interface, có thể cân nhắc `ScopedProxyMode.INTERFACES`.

### 4.2. Singleton sử dụng proxy

~~~java
package com.example.refresh;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final GreetingTarget greetingTarget;

    public GreetingService(GreetingTarget greetingTarget) {
        this.greetingTarget = greetingTarget;
    }

    public String greeting() {
        return greetingTarget.render();
    }
}
~~~

`GreetingService` là singleton. Constructor chỉ nhận proxy `GreetingTarget`. Sau refresh, field `greetingTarget` vẫn trỏ tới proxy cũ, nhưng proxy sẽ tìm target mới ở lần gọi `render()` kế tiếp.

### 4.3. Controller để quan sát

~~~java
package com.example.refresh;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting() {
        return greetingService.greeting();
    }
}
~~~

Mỗi request tới `/greeting` đi qua singleton `GreetingService`, rồi gọi proxy. Nếu target đã bị refresh, request đầu tiên tiếp theo sẽ kích hoạt tạo target mới.

### 4.4. Cấu hình ban đầu

`application.yml`:

~~~yaml
greeting:
  message: "Hello"

management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

Đoạn cấu hình Actuator chỉ để minh họa endpoint refresh trong môi trường học tập. Trong production, chỉ expose endpoint cần thiết và bảo vệ bằng Spring Security, xác thực/ủy quyền, HTTPS và network policy. Không mở `/actuator/refresh` cho người dùng Internet hoặc caller không có quyền quản trị.

## 5. Quan sát target cache qua các lần gọi

Sau khi chạy ứng dụng, gọi:

~~~bash
curl http://localhost:8080/greeting
~~~

Kết quả lần đầu có dạng:

~~~text
target-1: Hello
~~~

Gọi lại:

~~~bash
curl http://localhost:8080/greeting
~~~

Kết quả vẫn là:

~~~text
target-1: Hello
~~~

Target không được tạo mới cho mỗi request. Scope trả lại instance đã cache.

Giờ cập nhật giá trị cấu hình qua một nguồn mà ứng dụng có thể nạp lại, ví dụ Config Server, rồi gọi:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

Sau khi endpoint refresh hoàn tất, gọi lại:

~~~bash
curl http://localhost:8080/greeting
~~~

Kết quả minh họa:

~~~text
target-2: Bonjour
~~~

Log dự kiến có dạng:

~~~text
Create GreetingTarget id=1, message=Hello
Destroy GreetingTarget id=1
Create GreetingTarget id=2, message=Bonjour
~~~

Thứ tự quan trọng: cập nhật Environment trước, invalidate cache sau, rồi target mới mới được tạo theo giá trị mới. Nếu chỉ gọi `refreshAll()` mà Environment chưa nhận cấu hình mới, target tiếp theo vẫn được tạo từ giá trị cũ.

## 6. Refresh một bean hay toàn bộ scope?

`RefreshScope` cung cấp hai thao tác chính:

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Service;

@Service
public class RefreshOperations {

    private final RefreshScope refreshScope;

    public RefreshOperations(RefreshScope refreshScope) {
        this.refreshScope = refreshScope;
    }

    public boolean refreshGreetingTarget() {
        return refreshScope.refresh("greetingTarget");
    }

    public void refreshAllScopedBeans() {
        refreshScope.refreshAll();
    }
}
~~~

| API | Tác động | Khi nên dùng |
| --- | --- | --- |
| `refresh(beanName)` | Hủy target được cache cho một bean | Chỉ một bean có cấu hình hoặc tài nguyên cần khởi tạo lại |
| `refreshAll()` | Hủy toàn bộ target trong refresh scope | Một đợt cập nhật cấu hình ảnh hưởng nhiều bean |

Tên truyền vào `refresh(beanName)` là tên bean Spring. Với scoped proxy, Spring Cloud chuyển tên bean thông thường sang tên target nội bộ để invalidate đúng cache entry. Trong ví dụ, tên bean là `greetingTarget`, không phải tên class đầy đủ.

Nếu bean chưa có target trong cache, `refresh(beanName)` có thể trả `false` vì chưa có instance để hủy. Điều đó không có nghĩa proxy bị xóa hoặc bean definition biến mất.

### 6.1. Endpoint Actuator

Spring Cloud Context cung cấp endpoint `POST /actuator/refresh` để thực hiện quy trình refresh. Endpoint này cần Actuator và cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

Trong ứng dụng dùng Spring Cloud Config, endpoint refresh yêu cầu Config Client cập nhật lại cấu hình theo cơ chế context refresher rồi refresh các bean thuộc scope. Response thường chứa danh sách key thay đổi. Chi tiết endpoint và hành vi phụ thuộc release train.

Chỉ expose endpoint này trên management interface được bảo vệ. `POST /actuator/refresh` có thể làm nhiều bean bị hủy và tạo lại ở request tiếp theo, nên đây là thao tác quản trị có ảnh hưởng đến runtime.

### 6.2. Cập nhật nhiều instance

`RefreshScope` là cache trong một application context của một JVM. Khi hệ thống chạy nhiều replica, gọi refresh trên một instance không tự động xóa target cache của các instance khác.

Có thể dùng Spring Cloud Bus để phát sự kiện refresh đến các instance đang tham gia bus. Nếu không dùng Bus, hệ thống triển khai phải gọi cơ chế refresh cho từng instance theo quy trình được bảo vệ. Cần quan sát kết quả từng instance vì một số instance có thể cập nhật chậm hoặc lỗi khi tạo target mới.

## 7. Vì sao proxy vẫn giữ nguyên sau refresh?

Hãy xem hai đối tượng riêng biệt:

~~~text
GreetingService (singleton)
        |
        | field greetingTarget
        v
  Refresh scoped proxy  --------------------+
        |                                   |
        | trước refresh                     | sau refresh
        v                                   v
  target-1: Hello                     target-2: Bonjour
~~~

Singleton giữ tham chiếu tới proxy. Khi target bị hủy, Spring không phải tìm tất cả singleton đang giữ tham chiếu để thay field của chúng. Proxy vẫn có mặt và có thể tra target mới trong scope.

Đây là lợi ích chính của scoped proxy: các bean tiêu thụ không cần biết target đã thay đổi. Chúng tiếp tục gọi cùng một reference, còn scope quản lý vòng đời target phía sau.

### 7.1. Không lưu bản sao giá trị từ target trong singleton

Ví dụ sau không tự cập nhật sau refresh:

~~~java
@Service
public class CachedGreeting {

    private final String startupMessage;

    public CachedGreeting(GreetingTarget target) {
        this.startupMessage = target.render();
    }

    public String message() {
        return startupMessage;
    }
}
~~~

Constructor gọi proxy và lấy một chuỗi tại thời điểm khởi tạo. Sau đó singleton giữ chuỗi đó; việc proxy chuyển sang target mới không thể thay giá trị đã copy vào `startupMessage`.

Nếu cần đọc cấu hình mới, hãy gọi phương thức qua proxy khi cần, hoặc thiết kế service nhận một abstraction đọc cấu hình tại thời điểm sử dụng. Không sao chép dữ liệu từ target vào field singleton rồi kỳ vọng scope tự cập nhật field đó.

### 7.2. Không giữ tham chiếu trực tiếp tới target

Scoped proxy chỉ điều phối những lời gọi đi qua proxy. Nếu code chủ động unwrap proxy, lấy target nội bộ rồi lưu lại, hoặc tự tạo object bằng `new`, reference đó không tự chuyển sang target mới sau refresh.

Tương tự, nếu một phương thức trả về object mutable thuộc target và caller giữ object đó lâu dài, object đã trả về vẫn là object cũ. Proxy chỉ có thể điều phối những lời gọi tiếp tục đi qua proxy; nó không thay mọi reference đã được trả ra trước đó.

## 8. Proxy mode và yêu cầu đối với class

`@RefreshScope` mặc định dùng `ScopedProxyMode.TARGET_CLASS`. Spring tạo proxy dựa trên class để bean khác có thể inject bằng kiểu class.

Nếu muốn proxy theo interface:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

public interface Greeting {
    String render();
}

@Component
@RefreshScope(proxyMode = ScopedProxyMode.INTERFACES)
public class DefaultGreeting implements Greeting {

    @Override
    public String render() {
        return "Hello";
    }
}
~~~

Khi dùng interface proxy, nơi inject nên phụ thuộc vào interface `Greeting`. Nếu inject theo class `DefaultGreeting`, kiểu proxy interface có thể không đáp ứng kiểu đó.

Với class-based proxy, tránh khai báo class hoặc phương thức cần intercept là `final`, vì proxy không thể override class/method final. Chọn proxy mode phù hợp với thiết kế class và kiểu dependency.

## 9. Lazy target không có nghĩa mọi thứ đều trì hoãn

Có ba thời điểm khác nhau:

1. **Đăng ký bean definition và proxy:** xảy ra trong quá trình khởi tạo application context.
2. **Tạo target:** scope thực hiện khi cần target cho lời gọi, theo ngữ nghĩa lazy của refresh scope.
3. **Tạo target sau refresh:** xảy ra khi proxy được gọi lần tiếp theo sau khi cache entry đã bị hủy.

Do đó, việc ứng dụng khởi động thành công chưa chắc chứng minh target có thể tạo lại thành công sau refresh. Một dependency có thể chỉ lỗi khi target mới được tạo; ví dụ endpoint mới sai định dạng, credential không hợp lệ hoặc client constructor không kết nối được tới hệ thống ngoài.

Đội vận hành nên theo dõi lỗi khởi tạo target sau refresh và có phương án rollback cấu hình. Không nên chỉ kiểm tra HTTP response của endpoint refresh rồi kết luận mọi bean đã được tạo lại thành công.

## 10. Lifecycle và đồng thời

Khi target cũ bị invalidate, Spring Cloud gọi các destruction callback đã đăng ký cho target đó. Khi target mới được tạo, các dependency được inject và initialization callback chạy như một bean bình thường.

Điều này có nghĩa:

- `@PreDestroy`, `DisposableBean.destroy()` hoặc destroy method được cấu hình có thể chạy khi target cũ bị hủy.
- `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc init method chạy khi target mới được tạo.
- Tài nguyên do target sở hữu phải được đóng đúng cách; tài nguyên mới được tạo lại theo cấu hình mới.
- Các state chỉ nằm trong memory của target cũ sẽ mất khi target được thay thế.

`RefreshScope` có cơ chế đồng bộ truy cập và refresh cho bean trong scope. Tài liệu Spring Cloud mô tả việc đọc bean trong scope được tuần tự hóa với thao tác refresh để tránh đọc một target đang bị thay đổi vòng đời. Tuy nhiên, điều đó **không biến refresh thành một transaction nguyên tử trên toàn application context**, cũng không đồng bộ các replica khác nhau.

Không nên lưu trạng thái nghiệp vụ duy nhất trong target refresh-scoped. Ví dụ, số dư, giỏ hàng hoặc tiến trình xử lý đơn hàng phải nằm trong storage có vòng đời phù hợp, không dựa vào field của bean có thể bị hủy khi refresh.

## 11. Phân biệt RefreshScope với rebinding @ConfigurationProperties

Spring Cloud Context có thể xử lý `EnvironmentChangeEvent` theo nhiều cách. Hai cơ chế thường bị nhầm:

| Cơ chế | Cách cập nhật | Identity của bean |
| --- | --- | --- |
| Rebinding `@ConfigurationProperties` | Bind lại các field của bean đang tồn tại theo giá trị trong `Environment` | Thường giữ nguyên instance và cập nhật trạng thái bên trong |
| `@RefreshScope` | Invalidate target cache, rồi tạo lại target từ bean definition khi được truy cập | Target mới là instance khác; proxy vẫn giữ nguyên |

Rebinding tại chỗ có thể khiến một thread đọc bean đúng lúc các field đang được cập nhật. Tài liệu Spring Cloud lưu ý trường hợp cần một góc nhìn nhất quán qua refresh nên cân nhắc `@RefreshScope`, vì scope điều phối việc đọc với quá trình refresh theo từng bean.

`@RefreshScope` cũng không có nghĩa mọi bean có `@ConfigurationProperties` tự động trở thành refresh scoped. Hãy xác định bean nào thực sự cần được tạo lại và kiểm tra cách bean đó được đăng ký.

## 12. Những trường hợp không nên kỳ vọng target được refresh

### 12.1. Bean được khai báo trong @Configuration

Đặt `@RefreshScope` lên một lớp `@Configuration` không làm mọi `@Bean` method trong lớp đó tự động trở thành refresh scoped. Các bean khác phụ thuộc vào bean được khai báo trong cấu hình đó cũng không tự động nhận target mới nếu bản thân chúng không được thiết kế để tham gia refresh.

Nên đặt scope trực tiếp lên bean cần tạo lại:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @RefreshScope
    RemoteClient remoteClient(RemoteClientFactory factory,
                              RemoteClientProperties properties) {
        return factory.create(properties.endpoint());
    }
}
~~~

Trong ví dụ, bean `remoteClient` được đưa vào refresh scope. Các bean tiêu thụ nó cần inject proxy tương ứng. Nếu một bean khác đã copy trạng thái hoặc giữ reference nội bộ tới target cũ, nó cần được thiết kế lại để đi qua proxy.

### 12.2. Constructor binding và Java record

Theo tài liệu Spring Cloud Context, object dùng constructor binding, bao gồm Java record được đánh dấu `@ConfigurationProperties`, không thuộc nhóm có thể refresh theo cơ chế rebinding thông thường. Nếu cần tạo lại một object cấu hình immutable, phải chọn cách đăng ký bean và lifecycle phù hợp, rồi kiểm thử với đúng release train; không mặc định rằng chỉ thêm `@RefreshScope` vào mọi kiểu configuration properties là đủ.

### 12.3. HikariDataSource

`HikariDataSource` mặc định nằm trong danh sách `spring.cloud.refresh.never-refreshable`. Vì vậy, không nên kỳ vọng pool này được hủy và tạo lại chỉ bằng `@RefreshScope`. Tài liệu Spring Cloud khuyến nghị chọn implementation `DataSource` khác nếu thực sự cần refresh datasource theo cách này.

Không tùy tiện loại một datasource khỏi danh sách `never-refreshable`: pool đang có connection hoạt động và tài nguyên được chia sẻ cần một quy trình đóng/mở, drain request và rollback rõ ràng.

### 12.4. Native image và AOT

Context Refresh không được hỗ trợ cho Spring AOT transformations và native images theo tài liệu Spring Cloud hiện hành. Với ứng dụng AOT/native, cấu hình:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Trong trường hợp đó, thiết kế cấu hình cần dựa trên restart/rollout hoặc một cơ chế runtime khác được hỗ trợ.

### 12.5. Xóa một property khỏi nguồn cấu hình

Xóa property khỏi một file hoặc repository rồi refresh không đồng nghĩa mọi trường hợp đều khôi phục đúng sự vắng mặt của property. Tài liệu Spring Cloud lưu ý việc loại bỏ một giá trị cấu hình và refresh không cập nhật sự hiện diện của giá trị đó theo cách mà ứng dụng có thể kỳ vọng. Nếu logic phụ thuộc vào việc một key không còn tồn tại, hãy thiết kế default/absence semantics rõ ràng và kiểm thử tình huống xóa key trên đúng phiên bản.

## 13. Kiểm thử proxy ổn định và target được tạo lại

Một kiểm thử hữu ích cần chứng minh ba điều:

1. Lần gọi đầu tiên tạo target với giá trị cấu hình hiện tại.
2. Sau khi thay nguồn cấu hình và refresh, proxy mà test đang giữ vẫn là cùng một object.
3. Lần gọi tiếp theo đi qua proxy tạo target mới và trả giá trị mới.

Ví dụ với `@DynamicPropertySource`:

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RefreshScopeTest {

    private static final AtomicReference<String> MESSAGE =
            new AtomicReference<>("Hello");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("greeting.message", MESSAGE::get);
    }

    @Autowired
    GreetingTarget greetingTarget;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void keepsProxyButRecreatesTargetAfterRefresh() {
        GreetingTarget proxyReference = greetingTarget;

        String first = greetingTarget.render();
        assertThat(first).contains("Hello");

        MESSAGE.set("Bonjour");
        assertThat(refreshScope.refresh("greetingTarget")).isTrue();

        assertThat(greetingTarget).isSameAs(proxyReference);

        String second = greetingTarget.render();
        assertThat(second).contains("Bonjour");
        assertThat(second).isNotEqualTo(first);
    }
}
~~~

Test dùng dependency test của Spring Boot và một property supplier có thể thay đổi. `refresh("greetingTarget")` hủy target cũ; khi `render()` được gọi lại, `@Value` được đánh giá trên target mới. Proxy được inject vào test không thay identity.

Nếu test chạy song song hoặc dùng chung application context, phải reset `MESSAGE` về giá trị mặc định sau mỗi test để tránh trạng thái của test này ảnh hưởng test khác. Có thể dùng `@DirtiesContext` nếu cần cô lập context.

### 13.1. Các trường hợp kiểm thử bổ sung

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Gọi nhiều lần trước refresh | Target ID không đổi, target không bị tạo lại mỗi request |
| Refresh một bean | Chỉ target bean được chọn bị hủy và tạo lại khi truy cập |
| Refresh toàn bộ | Các target trong refresh scope bị invalidate |
| Bean chưa từng được gọi | Refresh không bắt buộc tạo target ngay; lần gọi đầu sau đó mới tạo |
| Target mới khởi tạo thất bại | Lỗi được quan sát qua log/health indicator và request không âm thầm dùng target đã hủy |
| Lifecycle callback | `@PreDestroy` của target cũ và `@PostConstruct` của target mới chạy đúng |
| Nhiều thread gọi đồng thời | Không quan sát target bị thay đổi một phần trong lúc scope refresh |
| Nhiều application instance | Mỗi instance được refresh theo cơ chế broadcast/operation tương ứng |

## 14. Chẩn đoán khi refresh không có tác dụng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Bean vẫn trả giá trị cũ | Cấu hình chưa được cập nhật vào `Environment` | Kiểm tra nguồn cấu hình và giá trị hiệu lực trước khi refresh scope |
| Target không được tạo lại | Không có lời gọi qua proxy sau refresh | Gọi phương thức bean qua reference được inject |
| Một singleton vẫn dùng giá trị cũ | Singleton đã copy giá trị từ target vào field của nó | Loại bỏ bản sao hoặc đọc qua proxy tại thời điểm sử dụng |
| `refresh(beanName)` trả `false` | Tên bean sai hoặc target chưa từng được cache | Kiểm tra bean name và xem target đã được gọi chưa |
| Không thấy `@PreDestroy` | Target chưa được tạo, destroy callback chưa đăng ký hoặc tên bean/scope không đúng | Kiểm tra log init, bean definition và lifecycle callback |
| `@Configuration` refresh nhưng `@Bean` không đổi | Scope đặt trên class cấu hình không tự áp dụng cho từng bean method | Đặt `@RefreshScope` trực tiếp trên bean cần tạo lại |
| Datasource không được thay | Datasource nằm trong `never-refreshable`, đặc biệt HikariDataSource | Kiểm tra `spring.cloud.refresh.never-refreshable` và loại datasource |
| Chỉ một replica nhận cấu hình mới | Refresh chỉ được gọi ở một JVM | Dùng Spring Cloud Bus hoặc gọi refresh từng instance |
| Native image không hỗ trợ | Context Refresh không hỗ trợ AOT/native | Tắt refresh và chọn chiến lược rollout/restart |

## 15. Quy trình vận hành có kiểm soát

Khi áp dụng refresh trong môi trường thật, nên thực hiện theo trình tự:

1. Cập nhật nguồn cấu hình và xác nhận version/label đã phát hành.
2. Gửi yêu cầu refresh qua kênh quản trị được xác thực.
3. Xác nhận Environment của instance nhận đúng giá trị mới.
4. Invalidate target cache bằng endpoint hoặc API refresh.
5. Kích hoạt health check/đường gọi nghiệp vụ để target mới được khởi tạo.
6. Theo dõi log lifecycle, lỗi tạo target, health indicator, request error rate và latency.
7. Nếu target mới lỗi, khôi phục cấu hình trước đó và refresh lại theo quy trình rollback.

Không coi HTTP `200` từ endpoint refresh là bằng chứng mọi target đã được tạo lại thành công. Endpoint chủ yếu kích hoạt cập nhật và invalidate cache; target được tạo lại khi có lời gọi tiếp theo.

## 16. Tổng kết

`@RefreshScope` tạo một scoped proxy ổn định để các bean khác tiếp tục sử dụng cùng một reference. Scope lưu target bean trong cache; khi có refresh, target hiện tại bị hủy và cache entry bị xóa. Lần gọi phương thức tiếp theo qua proxy sẽ tạo một target mới từ bean definition, inject dependency và chạy lại lifecycle callback.

Cơ chế này tránh phải thay reference trong mọi singleton, nhưng không tự làm mới các giá trị đã được copy ra ngoài proxy, không refresh tất cả bean trong application context và không broadcast giữa nhiều JVM. Cần cập nhật `Environment` trước khi invalidate target, bảo vệ endpoint refresh và kiểm thử cả trường hợp target mới khởi tạo thất bại.

## Tài liệu tham khảo

- [Spring Cloud Context — Application Context Services, Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): lazy proxy, target cache, `refreshAll()`, `refresh(String)`, lifecycle, giới hạn bean và AOT/native.
- [Spring Cloud `@RefreshScope` annotation source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/config/annotation/RefreshScope.java): annotation ánh xạ tới scope `refresh` và proxy mode mặc định.
- [Spring Cloud `RefreshScope` implementation](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): hủy target theo tên, `refreshAll()` và sự kiện sau refresh.
- [Spring Cloud `GenericScope` and refresh tests](https://github.com/spring-cloud/spring-cloud-commons/tree/main/spring-cloud-context/src/test/java/org/springframework/cloud/context/scope/refresh): kiểm thử target được tạo lại sau refresh và lifecycle callback.

Hãy đối chiếu tài liệu với release train Spring Cloud đang dùng. Chi tiết về bean không refresh được, rebinding, AOT và health indicator có thể thay đổi theo phiên bản.
