# Thứ tự callback khi kết hợp nhiều cơ chế khởi tạo, hủy

Spring quản lý vòng đời của bean từ lúc tạo object, inject dependency, hoàn tất khởi tạo cho tới khi ApplicationContext đóng. Framework cung cấp nhiều cách để ứng dụng tham gia vào vòng đời đó: **@PostConstruct**, **InitializingBean**, phương thức init tùy chỉnh, **@PreDestroy**, **DisposableBean** và phương thức destroy tùy chỉnh.

Một bean có thể sử dụng nhiều cơ chế cùng lúc. Khi đó, thứ tự callback rất quan trọng: callback nào chạy trước, callback nào chạy sau, và callback nào được gọi khi context đóng? Nếu không nắm thứ tự, bạn có thể khởi tạo tài nguyên quá sớm, đóng tài nguyên trước khi công việc kết thúc hoặc vô tình thực hiện cùng một thao tác nhiều lần.

Bài học này tập trung vào **thứ tự callback khi kết hợp nhiều cơ chế khởi tạo và hủy**. Ta cũng phân biệt các callback vòng đời bean với BeanPostProcessor, Aware, SmartInitializingSingleton, sự kiện ApplicationContext và thứ tự phụ thuộc giữa nhiều bean.

## 1. Hai giai đoạn cần phân biệt: khởi tạo và hủy

Vòng đời một singleton bean có thể hình dung:

~~~text
Spring tạo object
       │
       ▼
Inject dependency và cấu hình
       │
       ▼
Các callback khởi tạo
       │
       ▼
Bean sẵn sàng được sử dụng
       │
       ▼
Ứng dụng tiếp tục chạy
       │
       ▼
ApplicationContext đóng
       │
       ▼
Các callback hủy
       │
       ▼
Tài nguyên được giải phóng
~~~

**Callback khởi tạo** chạy trong quá trình Spring hoàn tất một bean. Chúng thường dùng để kiểm tra cấu hình, chuẩn bị trạng thái nội bộ, khởi tạo cache cục bộ hoặc mở tài nguyên mà bean sở hữu.

**Callback hủy** chạy khi container thực hiện quy trình destruction cho bean. Chúng thường dùng để dừng nhận công việc mới, flush dữ liệu còn chờ, đóng connection hoặc giải phóng tài nguyên.

Hai giai đoạn này không phải hai lần gọi tùy ý của ứng dụng. Chúng gắn với vòng đời mà Spring quản lý. Một object được tạo bằng **new** bên ngoài container sẽ không tự động nhận những callback của Spring.

## 2. Thứ tự các callback khởi tạo

Spring hỗ trợ ba cơ chế khởi tạo thường gặp:

1. **@PostConstruct**
2. **InitializingBean.afterPropertiesSet()**
3. **Phương thức init tùy chỉnh** được khai báo qua cấu hình bean, chẳng hạn thuộc tính **initMethod** của **@Bean**

Nếu một bean sử dụng cả ba cơ chế và mỗi cơ chế là một phương thức khác nhau, thứ tự thực thi là:

1. **@PostConstruct**
2. **InitializingBean.afterPropertiesSet()**
3. **Custom init-method**

Ví dụ, bean có thể kiểm tra cấu hình ở **@PostConstruct**, chuẩn bị trạng thái sau khi các property đã được gán ở **afterPropertiesSet()**, rồi chạy một bước warm-up được khai báo là custom init method.

### 2.1. @PostConstruct

**@PostConstruct** là annotation chuẩn Jakarta dùng để đánh dấu phương thức cần chạy sau khi dependency injection hoàn tất và trước khi bean được đưa vào sử dụng bình thường.

Với Spring Boot 3.x, annotation này thuộc package **jakarta.annotation.PostConstruct**:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexClient {

    @PostConstruct
    public void validateConfiguration() {
        // Kiểm tra các giá trị đã được inject.
    }
}
~~~

Phương thức thường không nhận tham số và trả về void. Đây là nơi phù hợp cho việc kiểm tra cấu hình cục bộ hoặc chuẩn bị trạng thái ban đầu dựa trên các dependency đã được inject.

**@PostConstruct không chạy ngay trong constructor.** Constructor chạy trước, sau đó Spring thực hiện các bước populate/inject dependency và xử lý bean trước khi gọi callback này.

### 2.2. InitializingBean.afterPropertiesSet()

**InitializingBean** là interface của Spring. Bean implement interface này phải định nghĩa phương thức **afterPropertiesSet()**:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexClient implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Chuẩn bị trạng thái sau khi properties đã được thiết lập.
    }
}
~~~

Spring gọi phương thức này sau các callback **@PostConstruct** và trước custom init method.

Ưu điểm là phương thức được khai báo qua interface nên Spring nhận biết trực tiếp. Hạn chế là class phải phụ thuộc vào API Spring, làm mã gắn với framework hơn.

Trong ứng dụng mới, **@PostConstruct** thường được ưu tiên nếu chỉ cần một callback chuẩn. **InitializingBean** vẫn hữu ích khi làm việc với code hiện có hoặc khi class chủ động chọn tích hợp lifecycle interface của Spring.

### 2.3. Custom init method

Bạn có thể khai báo tên phương thức khởi tạo trong **@Bean**:

~~~java
@Configuration
public class SearchConfiguration {

    @Bean(initMethod = "warmUp")
    SearchIndexClient searchIndexClient() {
        return new SearchIndexClient();
    }
}
~~~

Class có phương thức **warmUp()**:

~~~java
public class SearchIndexClient {

    public void warmUp() {
        // Nạp dữ liệu hoặc chuẩn bị tài nguyên cần thiết.
    }
}
~~~

Custom init method cho phép cấu hình lifecycle mà không cần class phải implement **InitializingBean** hoặc gắn annotation **@PostConstruct**. Cách này đặc biệt hữu ích khi object đến từ thư viện bên ngoài và bạn không thể sửa source code của nó.

Spring cũng hỗ trợ khai báo init method qua XML bean definition hoặc các cơ chế cấu hình tương ứng.

## 3. Thứ tự các callback hủy

Ở giai đoạn hủy, Spring hỗ trợ ba cơ chế thường gặp:

1. **@PreDestroy**
2. **DisposableBean.destroy()**
3. **Phương thức destroy tùy chỉnh** được khai báo qua cấu hình bean, chẳng hạn thuộc tính **destroyMethod** của **@Bean**

Nếu cả ba cơ chế được cấu hình với các phương thức khác nhau, thứ tự là:

1. **@PreDestroy**
2. **DisposableBean.destroy()**
3. **Custom destroy-method**

Thứ tự này cho phép bean dừng hoạt động ở callback đầu, thực hiện phần cleanup theo lifecycle interface ở bước tiếp theo, rồi hoàn tất thao tác giải phóng theo cấu hình custom.

### 3.1. @PreDestroy

**@PreDestroy** là annotation chuẩn Jakarta, đánh dấu phương thức chạy trước khi bean được hủy:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MessageConsumer {

    @PreDestroy
    public void stopAcceptingMessages() {
        // Ngừng nhận công việc mới và chuẩn bị dừng.
    }
}
~~~

Phương thức này thích hợp để yêu cầu component ngừng nhận công việc mới, thông báo trạng thái dừng hoặc giải phóng tài nguyên mà bean trực tiếp sở hữu.

### 3.2. DisposableBean.destroy()

Bean có thể implement **DisposableBean**:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class MessageConsumer implements DisposableBean {

    @Override
    public void destroy() {
        // Hoàn tất cleanup theo lifecycle của Spring.
    }
}
~~~

Spring gọi **destroy()** sau callback **@PreDestroy** và trước custom destroy method.

Giống **InitializingBean**, interface này làm class phụ thuộc trực tiếp vào Spring. Nếu muốn class ít phụ thuộc framework, có thể chọn annotation hoặc custom destroy method.

### 3.3. Custom destroy method

Với bean tạo qua **@Bean**, có thể khai báo:

~~~java
@Configuration
public class ConsumerConfiguration {

    @Bean(destroyMethod = "release")
    MessageConsumer messageConsumer() {
        return new MessageConsumer();
    }
}
~~~

Class định nghĩa:

~~~java
public class MessageConsumer {

    public void release() {
        // Giải phóng tài nguyên cuối cùng.
    }
}
~~~

Spring gọi **release()** như custom destroy method khi thực hiện destruction cho bean. Điều này cũng hữu ích khi cấu hình vòng đời cho object thư viện ngoài.

## 4. Ví dụ kết hợp đủ ba cơ chế init và ba cơ chế destroy

Ta tạo một bean có ba bước khởi tạo riêng:

1. Kiểm tra cấu hình qua **@PostConstruct**.
2. Chuẩn bị trạng thái nội bộ qua **afterPropertiesSet()**.
3. Warm-up dữ liệu qua custom init method **warmUp()**.

Khi context đóng:

1. Ngừng nhận công việc qua **@PreDestroy**.
2. Flush dữ liệu còn chờ qua **DisposableBean.destroy()**.
3. Đóng tài nguyên cuối cùng qua custom destroy method **release()**.

Ví dụ hoàn chỉnh:

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class SearchIndexClient
        implements InitializingBean, DisposableBean {

    @PostConstruct
    public void validateConfiguration() {
        System.out.println("1. @PostConstruct: validate configuration");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2. afterPropertiesSet: initialize state");
    }

    public void warmUp() {
        System.out.println("3. custom init: warm up index");
    }

    @PreDestroy
    public void stopAcceptingWork() {
        System.out.println("1. @PreDestroy: stop accepting work");
    }

    @Override
    public void destroy() {
        System.out.println("2. destroy: flush pending state");
    }

    public void release() {
        System.out.println("3. custom destroy: release resources");
    }
}
~~~

Cấu hình bean:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LifecycleConfiguration {

    @Bean(
        initMethod = "warmUp",
        destroyMethod = "release"
    )
    SearchIndexClient searchIndexClient() {
        return new SearchIndexClient();
    }
}
~~~

Khi context khởi tạo bean, thứ tự log minh họa:

~~~text
1. @PostConstruct: validate configuration
2. afterPropertiesSet: initialize state
3. custom init: warm up index
~~~

Khi context đóng bình thường:

~~~text
1. @PreDestroy: stop accepting work
2. destroy: flush pending state
3. custom destroy: release resources
~~~

Các phương thức trong ví dụ cố ý làm những việc khác nhau để minh họa thứ tự. Trong code thật, hãy thiết kế cleanup sao cho không đóng cùng một tài nguyên hai lần hoặc thực hiện một thao tác vừa ở **@PreDestroy** vừa ở **destroy()**.

## 5. Thứ tự đầy đủ khi đặt callback trong vòng đời bean

Ba callback init không phải những hoạt động đầu tiên của Spring. Trước đó còn có tạo object, inject dependency và các callback liên quan đến container.

Với một bean singleton thông thường, có thể hình dung trình tự khái quát:

~~~text
1. Instantiate
   Gọi constructor hoặc factory method
          │
          ▼
2. Populate properties
   Inject field/setter và cấu hình dependency
          │
          ▼
3. Aware callbacks
   BeanNameAware, BeanFactoryAware, ...
          │
          ▼
4. BeanPostProcessor before initialization
   Bao gồm xử lý @PostConstruct
          │
          ▼
5. InitializingBean.afterPropertiesSet()
          │
          ▼
6. Custom init-method
          │
          ▼
7. BeanPostProcessor after initialization
   Có thể tạo proxy
          │
          ▼
8. Bean sẵn sàng sử dụng
~~~

### 5.1. Constructor

Constructor tạo object. Những dependency khai báo qua constructor được Spring resolve trước khi gọi constructor. Các dependency qua field/setter thường được inject ở bước populate properties sau đó.

Không nên dùng setter-injected field trong constructor vì setter chưa được gọi:

~~~java
@Component
public class ReportService {

    private ReportExporter exporter;

    public ReportService() {
        // exporter chưa được setter injection gán ở đây.
    }

    @Autowired
    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Nếu dependency bắt buộc để object có trạng thái hợp lệ ngay khi tạo, constructor injection diễn đạt yêu cầu đó rõ hơn.

### 5.2. Populate properties và dependency injection

Spring gán các dependency theo field injection, setter injection hoặc những điểm injection khác được cấu hình. Sau giai đoạn này, callback init có thể dùng các dependency đã được inject.

Ví dụ **@PostConstruct** có thể đọc **Environment**, một service hoặc property đã được gán. Tuy nhiên, không nên coi **@PostConstruct** là nơi thay thế constructor validation cho mọi bất biến; nếu class không thể tồn tại hợp lệ khi thiếu một dependency, hãy khai báo dependency bắt buộc ở constructor.

### 5.3. Aware callbacks

Các interface **Aware** cho phép bean nhận một số đối tượng/hạ tầng do container cung cấp, ví dụ:

- **BeanNameAware** nhận tên bean.
- **BeanClassLoaderAware** nhận class loader.
- **BeanFactoryAware** nhận BeanFactory.
- **EnvironmentAware** nhận Environment.
- **ApplicationContextAware** nhận ApplicationContext.

Một số callback như **ApplicationContextAware** được xử lý bởi BeanPostProcessor nội bộ của Spring trước initialization callbacks. Vì vậy, chúng thuộc giai đoạn chuẩn bị bean, không phải custom init method.

Trong ứng dụng thông thường, constructor injection thường dễ kiểm thử và minh bạch hơn việc implement nhiều interface Aware. Dùng Aware khi thật sự cần tích hợp trực tiếp với container.

### 5.4. BeanPostProcessor trước và sau initialization

**BeanPostProcessor** là extension point cho phép Spring hoặc ứng dụng can thiệp vào bean trước/sau các callback init.

- **postProcessBeforeInitialization(...)** chạy trước các initialization callbacks như **@PostConstruct**.
- **postProcessAfterInitialization(...)** chạy sau **afterPropertiesSet()** và custom init method.

Một số tính năng Spring sử dụng post-processor để xử lý annotation hoặc tạo proxy. Ví dụ, các cơ chế AOP có thể bọc bean bằng proxy sau initialization. Vì vậy object được inject vào nơi khác có thể là proxy đại diện cho bean.

Điều này giải thích tại sao không nên tự gọi thủ công **@PostConstruct** hoặc cố đoán proxy đã được tạo trước khi initialization hoàn tất.

## 6. Thứ tự destruction đầy đủ

Khi Spring thực hiện hủy một singleton bean, có thể hình dung:

~~~text
ApplicationContext bắt đầu đóng
          │
          ▼
DestructionAwareBeanPostProcessor
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy-method
          │
          ▼
Bean đã hoàn tất destruction
~~~

**@PreDestroy** được xử lý qua cơ chế destruction-aware post-processing. Sau đó Spring gọi **DisposableBean.destroy()**, rồi gọi custom destroy method nếu được khai báo.

Một bean có thể dùng những callback này để chia cleanup thành các bước có thứ tự, nhưng cần tránh phụ thuộc vào thứ tự callback của một bean khác nếu chưa khai báo quan hệ rõ ràng.

### Khi nào destruction được kích hoạt?

Với singleton bean được quản lý, destruction thường xảy ra khi:

- Ứng dụng gọi **ApplicationContext.close()**.
- Context được đóng qua **try-with-resources** hoặc quy trình shutdown phù hợp.
- JVM kết thúc và shutdown hook của ứng dụng/container thực hiện đóng context (nếu được đăng ký và có đủ thời gian chạy).

Trong Spring Boot, ứng dụng thường đóng context khi tiến trình shutdown bình thường. Nếu process bị kill cưỡng bức, máy bị mất điện hoặc container runtime dừng quá gấp, callback có thể không có cơ hội hoàn tất. Vì vậy, **@PreDestroy không thay thế cơ chế lưu trạng thái bền vững hoặc xử lý khôi phục sau sự cố**.

## 7. Khi cùng một phương thức được khai báo cho nhiều cơ chế

Spring có quy tắc tránh gọi lặp khi **cùng một method name** được khai báo cho nhiều lifecycle mechanism.

Ví dụ, nếu một phương thức được dùng làm custom init method và cũng là phương thức triển khai **afterPropertiesSet()** theo cách cấu hình tương ứng, Spring tránh thực hiện cùng phương thức hai lần trong trường hợp trùng tên được nhận diện.

Tuy nhiên, cách dễ hiểu và ít gây nhầm nhất là **mỗi trách nhiệm lifecycle có một phương thức riêng**:

~~~java
@PostConstruct
void validate() { }

@Override
public void afterPropertiesSet() { }

void warmUp() { }
~~~

Khi mỗi cơ chế dùng một method name riêng, thứ tự được xác định rõ:

~~~text
validate()
   → afterPropertiesSet()
       → warmUp()
~~~

Điều tương tự áp dụng cho hủy:

~~~java
@PreDestroy
void stop() { }

@Override
public void destroy() { }

void release() { }
~~~

Nếu cấu hình một custom init/destroy method trùng với một phương thức lifecycle khác, hãy kiểm tra quy tắc của phiên bản Spring đang dùng và tránh dựa vào side effect của việc gọi lặp. Đặc biệt, cleanup như đóng connection hoặc dừng executor cần được thiết kế idempotent khi có thể.

## 8. Dùng @Bean(initMethod, destroyMethod) cho object bên ngoài

Một lợi ích quan trọng của custom lifecycle method là có thể quản lý vòng đời object mà bạn không kiểm soát source code.

Giả sử thư viện ngoài cung cấp:

~~~java
public class ExternalClient {

    public void connect() {
        // Mở kết nối.
    }

    public void close() {
        // Đóng kết nối.
    }
}
~~~

Ta có thể cấu hình:

~~~java
@Configuration
public class ExternalClientConfiguration {

    @Bean(
        initMethod = "connect",
        destroyMethod = "close"
    )
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Container tạo **ExternalClient**, gọi **connect()** trong giai đoạn init và gọi **close()** trong giai đoạn destroy khi bean được quản lý và context đóng.

Bạn không cần sửa class thư viện để thêm **@PostConstruct**, **@PreDestroy**, **InitializingBean** hoặc **DisposableBean**. Cấu hình bean sở hữu trách nhiệm nối lifecycle của thư viện vào Spring.

### Inferred destroy method

Với **@Bean**, Spring có thể suy luận một số destroy method mặc định như **close** hoặc **shutdown** nếu bean có phương thức tương ứng và cấu hình không vô hiệu hóa suy luận. Vì vậy, trước khi khai báo destroy method thủ công, cần hiểu hành vi suy luận của phiên bản/framework đang dùng để tránh đóng tài nguyên lặp.

Nếu muốn tắt suy luận destroy method, Spring hỗ trợ cấu hình **destroyMethod = ""** trong những trường hợp phù hợp. Dùng tùy chọn này khi bạn chủ động quản lý cleanup bằng cơ chế khác và đã hiểu rõ vòng đời bean.

## 9. Thứ tự giữa nhiều bean: dependency quan trọng hơn thứ tự khai báo

Thứ tự callback **bên trong một bean** đã được xác định. Nhưng thứ tự init/destroy **giữa các bean khác nhau** là câu chuyện riêng.

Giả sử:

~~~text
OrderService
    └── cần OrderRepository
             └── cần DataSource
~~~

Spring phải tạo dependency trước khi tạo bean phụ thuộc vào nó. Theo quan hệ dependency này, **DataSource** cần sẵn sàng trước **OrderRepository**, rồi **OrderService** mới được tạo và inject đầy đủ.

Khi destruction, quan hệ phụ thuộc được đảo chiều: bean phụ thuộc thường được hủy trước dependency mà nó sử dụng. Ví dụ, service/repository ngừng sử dụng datasource trước khi datasource được đóng.

~~~text
Khởi tạo:
DataSource → OrderRepository → OrderService

Hủy:
OrderService → OrderRepository → DataSource
~~~

Đây là thứ tự theo dependency graph, không phải quy tắc đơn giản “bean nào viết trước trong file cấu hình thì init trước”.

### @DependsOn cho quan hệ không thể hiện qua injection

Nếu bean B cần một tác dụng khởi tạo của bean A nhưng không có dependency trực tiếp trong constructor/property, có thể khai báo **@DependsOn**:

~~~java
@Component
public class DatabaseWarmup {
    // Chuẩn bị schema/cache cần thiết.
}

@Component
@DependsOn("databaseWarmup")
public class SearchService {
    // Cần DatabaseWarmup hoàn tất trước khi khởi tạo.
}
~~~

**@DependsOn** yêu cầu bean được chỉ định khởi tạo trước bean mang annotation. Khi singleton context đóng, thứ tự destruction giữa những bean có quan hệ depends-on được đảo lại để bean phụ thuộc được hủy trước bean mà nó phụ thuộc.

Chỉ dùng **@DependsOn** khi có một quan hệ khởi tạo thật sự nhưng không được thể hiện qua dependency injection. Nếu SearchService cần DatabaseWarmup như một dependency sử dụng thường xuyên, constructor injection sẽ mô tả quan hệ rõ hơn.

### @Order không phải công cụ sắp xếp thứ tự lifecycle singleton

**@Order** thường ảnh hưởng thứ tự các bean trong collection injection hoặc một số cơ chế xử lý có xét order. Nó không phải quy tắc tổng quát để buộc mọi singleton bean khởi tạo/hủy theo thứ tự số tùy ý.

Nếu cần quan hệ phụ thuộc giữa hai bean, hãy thể hiện dependency qua constructor hoặc dùng **@DependsOn** khi phù hợp. Đừng dùng **@Order** thay cho dependency graph.

## 10. SmartInitializingSingleton và thời điểm tất cả singleton đã được tạo

Ngoài callback trên từng bean, Spring có **SmartInitializingSingleton**. Interface này cung cấp phương thức:

~~~java
void afterSingletonsInstantiated();
~~~

Phương thức được gọi khi quá trình khởi tạo eager singleton thông thường của BeanFactory đã hoàn tất. Điều này hữu ích nếu một bean cần quan sát hoặc tổng hợp thông tin từ các singleton khác sau khi chúng đã được tạo.

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class PluginRegistry implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Có thể tổng hợp các plugin singleton đã được đăng ký.
    }
}
~~~

Đây **không phải callback thay thế @PostConstruct**:

- **@PostConstruct** gắn với initialization của một bean cụ thể.
- **afterPropertiesSet()** và custom init method cũng gắn với bean cụ thể.
- **afterSingletonsInstantiated()** chạy sau khi các singleton eager thông thường đã được tạo.

Các bean lazy chưa được khởi tạo có thể chưa hiện diện tại thời điểm này. Vì vậy, không nên coi callback này là bảo đảm rằng mọi bean có thể tồn tại trong context, kể cả lazy bean, đã được tạo.

## 11. ApplicationContext events và SmartLifecycle không phải callback của một bean đơn lẻ

Spring có nhiều mốc vòng đời ở cấp ApplicationContext. Chúng thường bị nhầm với callback init/destroy của từng bean.

### ContextRefreshedEvent

Khi ApplicationContext hoàn tất refresh, Spring phát sự kiện **ContextRefreshedEvent**. Một listener có thể nhận sự kiện:

~~~java
@Component
public class ContextReadyListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // Xử lý khi context đã refresh.
    }
}
~~~

Đây là sự kiện ở cấp context. Nó có thể được phát lại nếu context được refresh theo một cơ chế hỗ trợ; do đó, listener cần cân nhắc việc tránh thực hiện side effect lặp ngoài ý muốn.

### ApplicationRunner và CommandLineRunner

Spring Boot gọi **ApplicationRunner** và **CommandLineRunner** sau khi ApplicationContext được refresh trong quy trình khởi động ứng dụng:

~~~java
@Component
public class StartupReport implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Thực hiện công việc sau khi context đã refresh.
    }
}
~~~

Runner phù hợp cho công việc cần thực hiện sau giai đoạn khởi tạo context. Nhưng nó không phải init callback của từng bean. Nếu runner thực hiện tác vụ dài, cần xem xét tác động tới thời gian startup và cách điều phối công việc nền.

### SmartLifecycle

**SmartLifecycle** là một cơ chế quản lý vòng đời cho các component cần start/stop theo phase. Nó phù hợp với những thành phần như listener container hoặc service nền cần được khởi động và dừng có phối hợp với ApplicationContext.

SmartLifecycle có quy tắc riêng về phase và auto-startup; nó không thay thế thứ tự **@PostConstruct → afterPropertiesSet() → custom init method** của một bean.

## 12. Prototype bean có được gọi destroy callback không?

Đây là một giới hạn quan trọng của lifecycle management:

- Với **singleton bean**, Spring quản lý đầy đủ quá trình destruction khi context đóng.
- Với **prototype bean**, Spring tạo và cấu hình instance, nhưng sau khi giao instance cho client, container không quản lý đầy đủ vòng đời hủy của nó như singleton. Các destroy callback như **@PreDestroy** không được tự động gọi cho prototype bean theo cách thông thường.

Ví dụ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryReport {

    @PreDestroy
    public void cleanup() {
        // Không nên giả định Spring tự gọi cho mỗi prototype instance.
    }
}
~~~

Nếu prototype object sở hữu file handle, connection hoặc tài nguyên cần đóng, bên lấy object phải có trách nhiệm cleanup, hoặc dùng một factory/try-with-resources/API đóng tường minh.

**Scope thay đổi vòng đời instance**, nên khi thiết kế destroy callback, phải biết bean đang dùng scope nào.

## 13. Callback lỗi thì điều gì xảy ra?

Nếu một initialization callback ném exception, quá trình tạo bean thất bại. ApplicationContext có thể không khởi động thành công nếu bean đó là dependency bắt buộc hoặc singleton cần khởi tạo eager.

Ví dụ:

~~~java
@PostConstruct
public void validateConfiguration() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("Endpoint chưa được cấu hình");
    }
}
~~~

Fail-fast trong giai đoạn khởi tạo có thể hữu ích khi thiếu cấu hình khiến component không thể hoạt động đúng. Nhưng callback init không nên thực hiện một chuỗi nghiệp vụ dài và có side effect khó rollback.

Ở giai đoạn destruction, nếu một callback ném exception, Spring vẫn có cơ chế xử lý việc hủy các bean khác trong quá trình đóng context và ghi nhận lỗi. Tuy nhiên, bạn không nên dựa vào callback sau để khắc phục mọi hậu quả của callback trước. Cleanup nên được thiết kế độc lập, có kiểm tra trạng thái và càng idempotent càng tốt.

### Idempotent cleanup

Một thao tác cleanup idempotent có thể được gọi nhiều lần mà không làm hỏng trạng thái:

~~~java
public class ResourceHolder {

    private boolean closed;

    public synchronized void close() {
        if (closed) {
            return;
        }

        // Đóng tài nguyên nếu còn mở.
        closed = true;
    }
}
~~~

Ví dụ trên chỉ minh họa ý tưởng; tài nguyên thật cần xử lý exception và trạng thái đóng chính xác. Idempotency hữu ích khi một thư viện có cả callback lifecycle và API đóng thủ công, hoặc khi shutdown có thể được kích hoạt từ nhiều đường đi.

## 14. Tránh đặt công việc nghiệp vụ lớn vào callback init/destroy

Lifecycle callback có mục tiêu quản lý tài nguyên và trạng thái kỹ thuật của bean. Không nên mặc định dùng chúng để:

- Import hàng triệu bản ghi khi context vừa khởi động.
- Gửi email hàng loạt mỗi khi bean được tạo.
- Thanh toán hoặc thay đổi trạng thái đơn hàng khi context đóng.
- Chạy một quy trình nghiệp vụ dài mà không có trạng thái tiến độ.
- Thực hiện lời gọi ngoài không có timeout/retry trong khi giữ startup hoặc shutdown.

Nếu cần công việc chạy sau startup, hãy xác định nó là runner, job, message consumer hoặc một ca sử dụng được điều phối rõ. Nếu cần xử lý khi shutdown, hãy phân biệt **dừng nhận công việc**, **chờ công việc đang chạy hoàn tất**, **flush dữ liệu**, và **đóng tài nguyên**.

Ví dụ một worker có thể dùng **SmartLifecycle** để quản lý start/stop và một service riêng để thực hiện nghiệp vụ. Callback lifecycle chỉ điều khiển vòng đời kỹ thuật; logic xử lý message nằm ở application service.

## 15. Bảng tổng hợp các cơ chế và thứ tự

| Giai đoạn | Cơ chế | Thời điểm |
|---|---|---|
| Trước init callback | Constructor | Tạo object |
| Trước init callback | Populate properties / dependency injection | Gán dependency |
| Trước init callback | Aware callbacks | Cung cấp một số thông tin từ container |
| Init | **@PostConstruct** | Callback init đầu tiên trong ba cơ chế phổ biến |
| Init | **InitializingBean.afterPropertiesSet()** | Sau @PostConstruct |
| Init | **Custom init method** | Sau afterPropertiesSet() |
| Sau init | BeanPostProcessor after initialization | Có thể bọc bean/proxy |
| Sau eager singleton creation | **SmartInitializingSingleton** | Sau khi các singleton eager thông thường được khởi tạo |
| Context đã refresh | **ContextRefreshedEvent**, Boot runners theo startup flow | Mốc ở cấp context/ứng dụng |
| Destroy | **@PreDestroy** | Callback hủy đầu tiên trong ba cơ chế phổ biến |
| Destroy | **DisposableBean.destroy()** | Sau @PreDestroy |
| Destroy | **Custom destroy method** | Sau destroy() |

Hai chuỗi cần nhớ:

~~~text
INITIALIZATION
@PostConstruct
      ↓
afterPropertiesSet()
      ↓
custom init-method

DESTRUCTION
@PreDestroy
      ↓
DisposableBean.destroy()
      ↓
custom destroy-method
~~~

Thứ tự trên mô tả **các callback của một bean**. Thứ tự giữa nhiều bean còn phụ thuộc vào dependency graph, @DependsOn, scope và quy trình đóng context.

## 16. Chọn cơ chế nào trong dự án Spring Boot?

| Nhu cầu | Cách thường nên chọn | Lý do |
|---|---|---|
| Kiểm tra cấu hình sau khi inject | **@PostConstruct** | Annotation chuẩn, dễ đọc |
| Tích hợp lifecycle interface có sẵn | **InitializingBean** | Hữu ích khi class chủ động phụ thuộc Spring |
| Cấu hình init cho object thư viện ngoài | **@Bean(initMethod = "...")** | Không cần sửa class thư viện |
| Dọn dẹp tài nguyên trước khi bean bị hủy | **@PreDestroy** | Annotation chuẩn, không cần implement interface Spring |
| Dùng lifecycle interface hủy của Spring | **DisposableBean** | Tích hợp trực tiếp với container |
| Cấu hình destroy cho object bên ngoài | **@Bean(destroyMethod = "...")** | Khai báo cleanup tại nơi tạo bean |
| Cần biết các eager singleton đã được tạo | **SmartInitializingSingleton** | Callback ở mốc sau singleton instantiation |
| Cần start/stop component theo phase | **SmartLifecycle** | Quản lý vòng đời hoạt động có phối hợp |
| Chạy công việc sau khi context refresh | **ApplicationRunner / CommandLineRunner** | Điểm vào ở cấp Spring Boot application |

Không cần sử dụng tất cả cơ chế trong mọi bean. Chọn một cơ chế đơn giản phù hợp với trách nhiệm; chỉ kết hợp nhiều cơ chế khi các bước có ý nghĩa riêng và thứ tự được hiểu rõ.

## 17. Thực hành quan sát thứ tự callback

Tạo một Spring Boot project nhỏ, thêm class **LifecycleProbe** implement **InitializingBean** và **DisposableBean**, đồng thời có **@PostConstruct**, **@PreDestroy** và hai custom method được khai báo qua **@Bean**.

Ví dụ cấu hình:

~~~java
@Configuration
public class ProbeConfiguration {

    @Bean(initMethod = "customStart", destroyMethod = "customStop")
    LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe();
    }
}
~~~

Trong từng callback, in một dòng log khác nhau. Khởi động ứng dụng và quan sát thứ tự ba dòng init. Sau đó đóng ApplicationContext bình thường và quan sát ba dòng destroy.

Tiếp theo, thử:

1. Bỏ **InitializingBean** và quan sát thứ tự còn lại.
2. Bỏ **@PostConstruct** và quan sát custom init vẫn được gọi.
3. Bỏ custom destroy method và quan sát hai callback hủy còn lại.
4. Đổi bean sang **prototype** rồi quan sát việc Spring không tự gọi destruction callback cho từng instance.
5. Tạo bean B phụ thuộc bean A và quan sát A được tạo trước B, B được hủy trước A.
6. Thêm **@DependsOn** khi không có dependency injection trực tiếp và quan sát tác động tới thứ tự.

Khi kiểm tra, hãy đóng context bằng cách rõ ràng, chẳng hạn:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(ProbeConfiguration.class)) {
    // Bean được tạo và sử dụng tại đây.
}
// Context đóng khi rời khỏi try; destruction callback được gọi.
~~~

Đoạn ví dụ dùng **AnnotationConfigApplicationContext** để minh họa cơ chế Spring Framework. Trong Spring Boot, có thể quan sát tương tự khi đóng context hoặc kết thúc ứng dụng bình thường.

## 18. Những lỗi thường gặp khi kết hợp callback

**Cho rằng @PostConstruct chạy trước dependency injection.** Thực tế, nó chạy sau các bước inject dependency mà Spring quản lý. Không dùng setter-injected field trong constructor.

**Cho rằng custom init method chạy trước afterPropertiesSet().** Thứ tự chuẩn là @PostConstruct, afterPropertiesSet(), rồi custom init method.

**Cho rằng @PreDestroy chạy sau destroy().** Thứ tự chuẩn là @PreDestroy, DisposableBean.destroy(), rồi custom destroy method.

**Thực hiện cùng một cleanup trong nhiều callback.** Điều này có thể đóng tài nguyên hai lần. Chia rõ trách nhiệm hoặc làm cleanup idempotent.

**Dựa vào thứ tự khai báo @Bean trong file để suy ra lifecycle order.** Thứ tự giữa bean chủ yếu phụ thuộc dependency graph và những quy tắc lifecycle cụ thể; dùng dependency injection hoặc @DependsOn khi cần biểu diễn quan hệ.

**Dùng @Order để điều khiển thứ tự init/destroy singleton.** @Order không phải công cụ tổng quát cho việc này.

**Cho rằng mọi bean đều được hủy khi context đóng.** Prototype bean không được container quản lý destruction đầy đủ như singleton.

**Cho rằng @PreDestroy luôn chạy khi process kết thúc.** Shutdown cưỡng bức hoặc sự cố máy có thể khiến callback không có cơ hội chạy.

**Đặt tác vụ nghiệp vụ dài vào @PostConstruct.** Startup có thể bị chậm hoặc thất bại; nên tách công việc thành runner/job/worker với trạng thái và cơ chế xử lý lỗi phù hợp.

**Nhầm callback bean với sự kiện context.** SmartInitializingSingleton, ContextRefreshedEvent và ApplicationRunner hoạt động ở các mốc rộng hơn vòng đời init của một bean cụ thể.

## Kết luận

Khi kết hợp nhiều cơ chế vòng đời của Spring, thứ tự callback trong một bean là:

- **Khởi tạo:** **@PostConstruct → InitializingBean.afterPropertiesSet() → custom init method**.
- **Hủy:** **@PreDestroy → DisposableBean.destroy() → custom destroy method**.

Trước các callback init còn có constructor, dependency injection, Aware callbacks và BeanPostProcessor trước initialization; sau init còn có BeanPostProcessor sau initialization. Ở cấp context, **SmartInitializingSingleton**, sự kiện refresh và Spring Boot runners là những mốc khác, không thay thế callback của từng bean.

Hãy phân chia mỗi callback theo một trách nhiệm riêng, tránh thực hiện cùng thao tác nhiều lần, và nhớ rằng thứ tự giữa các bean được quyết định bởi quan hệ dependency và cơ chế quản lý context. Nắm đúng chuỗi này giúp bạn khởi tạo tài nguyên đúng lúc, dừng component có trật tự và tránh lỗi khi ứng dụng Spring Boot shutdown.
