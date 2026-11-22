# ApplicationListenerDetector

`ApplicationListenerDetector` là một thành phần hạ tầng nội bộ của Spring Framework. Nó là một `BeanPostProcessor` được `AbstractApplicationContext` cài trực tiếp vào BeanFactory để phát hiện các bean instance triển khai `ApplicationListener` và đăng ký instance đó với ApplicationContext.

Đây không phải là một application listener, không nhận event nghiệp vụ và cũng không phải processor xử lý annotation `@EventListener`. Nhiệm vụ của nó nằm ở vòng đời tạo và hủy bean: quan sát bean sau initialization, nhận diện listener instance đủ điều kiện, đưa instance vào event multicaster và gỡ instance khi bean bị hủy.

Bài viết bám theo source tag Spring Framework **6.2.0**. `ApplicationListenerDetector` là implementation nội bộ, không phải public extension API. Có thể đọc source để hiểu startup và debug, nhưng không nên import, khởi tạo hoặc phụ thuộc vào class này trong code ứng dụng.

## 1. Ba khái niệm cần tách biệt

| Thành phần | Bản chất | Vai trò |
|---|---|---|
| `ApplicationListenerDetector` | Internal `BeanPostProcessor` | Phát hiện bean instance triển khai `ApplicationListener` trong lifecycle của BeanFactory |
| ApplicationListener bean | Bean ứng dụng triển khai `ApplicationListener<E>` | Xử lý event bằng `onApplicationEvent(E)` |
| `EventListenerMethodProcessor` | Internal `BeanFactoryPostProcessor` và `SmartInitializingSingleton` | Tìm method có `@EventListener`, tạo adapter và đăng ký adapter đó |

Ví dụ một bean ứng dụng:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Đơn hàng mới: " + event.getOrderId());
    }
}
~~~

`OrderCreatedListener` là listener thực sự. Nó nhận event và chạy nghiệp vụ. `ApplicationListenerDetector` chỉ quan sát việc Spring tạo bean này rồi đăng ký nó. Detector không gọi `onApplicationEvent` trực tiếp; event multicaster mới là thành phần phân phối event đến listener phù hợp.

## 2. Vị trí của detector trong Spring 6.2.0

Trong source `AbstractApplicationContext.prepareBeanFactory(...)`, Spring cài detector trực tiếp bằng lời gọi:

~~~java
beanFactory.addBeanPostProcessor(new ApplicationListenerDetector(this));
~~~

Lời gọi nằm trong `prepareBeanFactory`, sau khi context đăng ký các resolvable dependency như `ApplicationEventPublisher` và `ApplicationContext`. Nó xảy ra trước `invokeBeanFactoryPostProcessors(...)`, trước `registerBeanPostProcessors(...)` và trước khi các application singleton thông thường được khởi tạo.

Điều đó có nghĩa:

- Detector không cần được khai báo bằng `@Component`, `@Bean` hoặc XML.
- Detector không phải là một bean listener do người dùng cấu hình.
- Nó đã nằm trong danh sách post-processor trước khi Spring bắt đầu khởi tạo các bean ứng dụng.
- Nó có thể quan sát các bean được tạo trong những giai đoạn refresh tiếp theo, kể cả bean post-processor và bean listener.

Tên gọi “early post-processor” trong source nói về thời điểm nó được gắn vào BeanFactory. Nó không có nghĩa detector đăng ký listener trước khi listener instance được khởi tạo xong.

## 3. Detector triển khai những interface nào?

Trong Spring 6.2.0, detector kết hợp hai vai trò:

- `MergedBeanDefinitionPostProcessor`: nhận thông tin merged bean definition để biết bean có singleton scope hay không.
- `DestructionAwareBeanPostProcessor`: quan sát bean sau initialization và thực hiện cleanup trước khi bean bị hủy.

Hai vai trò giải quyết hai vấn đề khác nhau. Merged definition cho biết scope của bean; callback sau initialization cung cấp instance thực tế để kiểm tra `instanceof ApplicationListener`.

### 3.1. Ghi nhận scope của bean

Ở callback `postProcessMergedBeanDefinition(...)`, detector lưu trạng thái singleton theo bean name. Ý tưởng của đoạn xử lý là:

~~~java
@Override
public void postProcessMergedBeanDefinition(
        RootBeanDefinition beanDefinition,
        Class<?> beanType,
        String beanName) {

    singletonNames.put(beanName, beanDefinition.isSingleton());
}
~~~

Map này không chứa listener object. Nó chỉ lưu thông tin Boolean cho bean name để callback sau initialization biết instance vừa tạo có phải singleton theo merged definition hay không.

Việc kiểm tra scope rất quan trọng vì cách event multicaster giữ listener instance khác với cách nó giữ listener bean name. Singleton instance có thể được đăng ký trực tiếp. Top-level non-singleton bean được đăng ký bằng bean name để BeanFactory cung cấp instance theo scope khi cần.

### 3.2. Kiểm tra instance sau initialization

Trong `postProcessAfterInitialization(bean, beanName)`, detector chỉ quan tâm đến object triển khai `ApplicationListener`.

Luồng xử lý khái quát của Spring 6.2.0:

~~~java
if (bean instanceof ApplicationListener<?> listener) {
    Boolean singleton = singletonNames.get(beanName);

    if (Boolean.TRUE.equals(singleton)) {
        applicationContext.addApplicationListener(listener);
    }
    else if (Boolean.FALSE.equals(singleton)) {
        if (!applicationContext.containsBean(beanName)) {
            // Cảnh báo inner listener bean non-singleton.
        }
        singletonNames.remove(beanName);
    }
}

return bean;
~~~

Đây là sơ đồ logic rút gọn để giải thích, không phải bản sao đầy đủ của source. Code thật có logger, kiểm tra điều kiện log và generic type.

Nếu bean là singleton, detector gọi `applicationContext.addApplicationListener(listener)`. Trong `AbstractApplicationContext`, lời gọi này thêm instance vào tập listener của context và, nếu event multicaster đã được khởi tạo, thêm instance vào multicaster hiện tại.

Nếu bean là non-singleton, detector không đăng ký instance đó như một listener instance cố định. Với top-level bean, đường đăng ký theo bean name đã được `registerListeners()` xử lý. Với inner bean non-singleton, Spring không có top-level bean name ổn định để event multicaster tra cứu; detector phát cảnh báo rằng inner listener non-singleton không thể được auto-detect đáng tin cậy.

### 3.3. Vì sao callback chạy sau initialization?

`postProcessAfterInitialization` được gọi sau các initialization callback như `InitializingBean.afterPropertiesSet()` hoặc custom init method. Vì vậy detector đăng ký listener sau khi quá trình khởi tạo bean đã chạy qua các callback đó.

Điều này khác với `postProcessMergedBeanDefinition`, vốn diễn ra ở giai đoạn xử lý merged definition để lưu thông tin scope.

Detector không thay thế dependency injection, không tạo listener object và không sửa object thành một listener. Nó chỉ kiểm tra instance đã được BeanFactory tạo ra.

## 4. Registration timing: hai đường đăng ký bổ sung cho nhau

Một điểm dễ gây nhầm là Spring có cả `registerListeners()` và `ApplicationListenerDetector`. Hai cơ chế này không phải hai cách đặt tên cho cùng một bước.

### Đường 1 — Đăng ký top-level listener bean bằng bean name

Trong `AbstractApplicationContext.registerListeners()`, Spring thực hiện hai nhóm việc:

1. Thêm các listener instance được đăng ký tĩnh từ trước vào event multicaster.
2. Tìm tên các bean có kiểu `ApplicationListener` bằng:

~~~java
getBeanNamesForType(ApplicationListener.class, true, false)
~~~

Sau đó, Spring gọi `addApplicationListenerBean(listenerBeanName)` cho từng bean name.

Hai tham số Boolean có ý nghĩa quan trọng:

- `includeNonSingletons = true`: cho phép tìm cả top-level listener bean không phải singleton.
- `allowEagerInit = false`: không chủ động khởi tạo FactoryBean chỉ để hoàn tất việc dò kiểu.

Ở bước này Spring đăng ký bean name, không cần khởi tạo tất cả listener bean. Event multicaster giữ tên bean và dùng BeanFactory để lấy listener instance khi cần phân phối event.

### Đường 2 — Đăng ký actual singleton instance bằng detector

Khi một bean listener được khởi tạo, detector kiểm tra instance trong `postProcessAfterInitialization`. Nếu bean là singleton, nó gọi `addApplicationListener(instance)`.

Đường này đặc biệt quan trọng đối với singleton inner bean. Inner bean không có top-level bean name để `getBeanNamesForType(ApplicationListener.class, ...)` tìm thấy, nhưng instance vẫn đi qua BeanFactory lifecycle và detector có thể nhìn thấy nó.

Đối với top-level singleton listener bean, hai đường có thể cùng xuất hiện: `registerListeners()` đã thêm bean name, rồi detector thêm actual instance sau initialization. Event multicaster quản lý listener instance và listener bean name, đồng thời tránh gọi lặp cùng một singleton listener object khi hợp nhất các candidate.

## 5. Detection scope: detector nhìn thấy những gì?

Phạm vi phát hiện cần được hiểu theo hai câu hỏi: object có đi qua BeanFactory lifecycle không, và bean definition có singleton scope hay không.

| Trường hợp | Đường đăng ký trong Spring 6.2.0 | Kết quả |
|---|---|---|
| Top-level singleton bean implements `ApplicationListener` | `registerListeners()` thêm bean name; detector thêm instance sau initialization | Được đăng ký |
| Top-level prototype listener bean | `registerListeners()` thêm bean name; detector không giữ prototype instance cố định | Được hỗ trợ theo bean name và scope |
| Singleton inner listener bean | Không có top-level bean name; detector nhìn thấy instance sau initialization | Detector đăng ký actual instance |
| Inner listener bean non-singleton | Không có top-level bean name ổn định; detector không thể đăng ký instance lâu dài | Cảnh báo, không auto-detect đáng tin cậy |
| Object được tạo bằng `new` bên trong một bean nhưng không phải bean riêng | Không đi qua BeanFactory post-processing như một bean độc lập | Detector không nhìn thấy |
| Listener được đăng ký trực tiếp bằng `context.addApplicationListener(...)` | Context đăng ký instance theo API công khai | Không cần detector phát hiện |

### 5.1. Top-level prototype không đồng nghĩa bị bỏ qua

Không nên đọc nhánh non-singleton của detector rồi kết luận rằng Spring không hỗ trợ prototype listener bean.

Top-level listener bean được `registerListeners()` tìm bằng `includeNonSingletons = true` và đăng ký bằng bean name. Multicaster có thể lấy listener qua BeanFactory theo tên bean; vòng đời instance vẫn tuân theo scope đã khai báo.

Detector chỉ không thêm prototype instance vào tập listener instance cố định. Đó là khác biệt giữa registration by bean name và registration by object instance.

### 5.2. Vì sao inner listener bean cần detector?

`getBeanNamesForType(...)` tìm bean names ở cấp BeanFactory, không duyệt mọi object lồng bên trong dependency graph. Một inner bean được khai báo trực tiếp trong property hoặc constructor argument không có bean name độc lập để đăng ký với multicaster.

Ví dụ XML về một inner bean:

~~~xml
<bean id="orderCoordinator" class="demo.OrderCoordinator">
    <property name="listener">
        <bean class="demo.OrderCreatedListener"/>
    </property>
</bean>
~~~

Inner listener được tạo trong quá trình tạo bean chứa nó. Nó vẫn đi qua bean post-processing, nên detector có thể nhận ra instance triển khai `ApplicationListener` và đăng ký nếu instance đó là singleton theo merged definition.

Nếu tạo một object bằng `new OrderCreatedListener()` trong thân một phương thức Java rồi truyền nó vào bean khác, object đó không tự trở thành một bean riêng. Detector không quét mọi field hoặc object graph để tìm listener.

## 6. Refresh order trong Spring 6.2.0

Thứ tự refresh giải thích vì sao Spring cần cả đăng ký theo bean name và post-processing theo instance.

<text color="secondary" size="sm">Trình tự rút gọn theo AbstractApplicationContext.refresh()</text>

1. **`prepareRefresh()`** — Đánh dấu context đang active, lưu tập listener đã đăng ký trước refresh và tạo buffer cho early application events.
2. **`obtainFreshBeanFactory()`** — Tạo hoặc lấy BeanFactory của context.
3. **`prepareBeanFactory()`** — Cấu hình BeanFactory, đăng ký resolvable dependency và gắn `ApplicationListenerDetector` như một early BeanPostProcessor.
4. **`postProcessBeanFactory()`** — Cho phép context subclass tùy chỉnh BeanFactory.
5. **`invokeBeanFactoryPostProcessors()`** — Chạy BeanFactoryPostProcessor, trong đó có `EventListenerMethodProcessor.postProcessBeanFactory(...)` nếu annotation infrastructure đã đăng ký processor đó.
6. **`registerBeanPostProcessors()`** — Đăng ký các BeanPostProcessor được khai báo như bean.
7. **`initMessageSource()`** — Khởi tạo MessageSource.
8. **`initApplicationEventMulticaster()`** — Khởi tạo event multicaster, mặc định là `SimpleApplicationEventMulticaster` nếu không có bean tùy chỉnh.
9. **`onRefresh()`** — Thực hiện phần refresh riêng của context subclass.
10. **`registerListeners()`** — Thêm listener instance đăng ký tĩnh, thêm top-level listener bean names, sau đó phát lại các early event đã được buffer.
11. **`finishBeanFactoryInitialization()`** — Khởi tạo các non-lazy singleton còn lại. Detector chạy sau initialization của từng bean và đăng ký các singleton `ApplicationListener` instance.
12. **`finishRefresh()`** — Khởi tạo LifecycleProcessor, gọi `onRefresh()` của lifecycle processor và phát `ContextRefreshedEvent`.

Điểm cần nhớ: detector được cài ở bước 3, nhưng listener instance thường chỉ được đăng ký ở bước 11 khi bean hoàn tất initialization. Trong khi đó, bean name của top-level listener đã được multicaster biết từ bước 10.

Early event được phát trước khi multicaster sẵn sàng sẽ được buffer. Sau khi `registerListeners()` thiết lập listener instance và listener bean names, Spring replay các event đó. Vì vậy early event không bị mất chỉ vì multicaster chưa được khởi tạo tại thời điểm publish.

### 6.1. Vì sao ContextRefreshedEvent thường đến sau khi listener singleton sẵn sàng?

`finishRefresh()` nằm sau `finishBeanFactoryInitialization()`. Các non-lazy singleton thông thường đã được tạo và detector đã xử lý listener instance trước khi context phát `ContextRefreshedEvent`.

Điều này không có nghĩa mọi listener lazy đều đã được khởi tạo. Top-level lazy listener bean đã có thể được đăng ký bằng bean name; việc tạo instance có thể diễn ra khi BeanFactory cần cung cấp listener cho event phù hợp.

## 7. Không nhầm với EventListenerMethodProcessor

`EventListenerMethodProcessor` xử lý một bài toán khác: phát hiện method được đánh dấu `@EventListener` và biến từng method thành một listener adapter.

Trong Spring Framework 6.2.0, class này triển khai:

~~~java
public class EventListenerMethodProcessor
        implements SmartInitializingSingleton,
                   ApplicationContextAware,
                   BeanFactoryPostProcessor {
}
~~~

Nó không triển khai `BeanPostProcessor`.

Quy trình chính:

1. Trong `postProcessBeanFactory(...)`, processor giữ BeanFactory và tìm các `EventListenerFactory` phù hợp.
2. Ở callback `afterSingletonsInstantiated()`, nó quét các bean và các method được đánh dấu `@EventListener`.
3. Với mỗi method phù hợp, factory tạo một `ApplicationListener` adapter, thường là `ApplicationListenerMethodAdapter`.
4. Processor gọi `applicationContext.addApplicationListener(adapter)` để đăng ký adapter vào context.

Javadoc Spring 6.2.0 mô tả rõ class này đăng ký các `@EventListener` method thành các `ApplicationListener` instance riêng lẻ. Callback `afterSingletonsInstantiated()` chạy ở cuối singleton pre-instantiation phase, khi các regular singleton bean đã được tạo.

### 7.1. So sánh theo cơ chế phát hiện

| Tiêu chí | ApplicationListenerDetector | EventListenerMethodProcessor |
|---|---|---|
| Loại processor | BeanPostProcessor + DestructionAwareBeanPostProcessor + MergedBeanDefinitionPostProcessor | BeanFactoryPostProcessor + SmartInitializingSingleton |
| Đầu vào | Bean instance | Bean classes và method metadata |
| Điều kiện phát hiện | `bean instanceof ApplicationListener` | Method có `@EventListener` |
| Thời điểm chính | Sau initialization của từng bean | Scan và đăng ký adapter sau singleton pre-instantiation |
| Kết quả | Đăng ký listener bean instance | Tạo và đăng ký listener adapter cho method |
| Xử lý destruction của listener bean | Có callback remove listener | Adapter được processor đăng ký như listener instance; không phải bean listener được detector phát hiện |

Ví dụ một bean không triển khai `ApplicationListener` nhưng có method annotation:

~~~java
@Component
public class OrderAuditHandler {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.getOrderId());
    }
}
~~~

`ApplicationListenerDetector` không tìm thấy method này vì bean không phải `ApplicationListener`. `EventListenerMethodProcessor` mới là thành phần đọc annotation, tạo adapter và đăng ký adapter.

Ngược lại, một bean chỉ implements `ApplicationListener` không cần `@EventListener`; nó được phát hiện bằng type và đăng ký theo các đường listener bean name/instance.

Không nên gộp hai cơ chế thành một “annotation BeanPostProcessor”. Chúng có interface, lifecycle và đầu vào khác nhau. Nếu cùng một bean vừa implements `ApplicationListener` vừa có `@EventListener` method cho cùng event, hai cơ chế có thể đăng ký hai listener route riêng và dẫn đến xử lý lặp; chỉ kết hợp khi có chủ đích rõ ràng.

## 8. Spring Framework 6.2: những chi tiết phiên bản cần nhớ

### 8.1. Detector vẫn là internal implementation

Trong source tag `v6.2.0`, `AbstractApplicationContext.prepareBeanFactory()` trực tiếp tạo `ApplicationListenerDetector`. Đây là chi tiết triển khai của ApplicationContext, không phải API ứng dụng được bảo đảm tương thích qua mọi phiên bản.

Khi nâng Spring, hãy kiểm tra source tag tương ứng nếu đang debug nội bộ. Không nên viết code ứng dụng gọi constructor detector hoặc phụ thuộc vào map `singletonNames`.

### 8.2. ApplicationListener có supportsAsyncExecution()

`ApplicationListener.supportsAsyncExecution()` được thêm từ Spring 6.1 và có mặt trong Spring 6.2. Giá trị mặc định là `true`; nó cho multicaster biết listener có thể được chạy bất đồng bộ nếu multicaster được cấu hình executor.

Detector không quyết định listener chạy đồng bộ hay bất đồng bộ. Nó chỉ đăng ký listener instance. Việc dispatch phụ thuộc `ApplicationEventMulticaster`, cấu hình executor và khả năng async của listener.

Với `SimpleApplicationEventMulticaster` mặc định không cấu hình executor, listener được gọi trong thread publish event. Nếu có executor, listener không hỗ trợ async execution vẫn phải chạy trong thread gọi multicaster.

### 8.3. @EventListener.defaultExecution() là thuộc tính của annotation

Spring 6.2 thêm thuộc tính `defaultExecution` vào `@EventListener`. Javadoc ghi rõ thuộc tính này có từ 6.2 và phục vụ các composed annotation như `@TransactionalEventListener`.

Đây là behavior thuộc annotation listener pipeline, được xử lý bởi adapter được tạo qua `EventListenerMethodProcessor`. Nó không làm thay đổi vai trò của `ApplicationListenerDetector` và không khiến detector bắt đầu scan annotation.

### 8.4. ApplicationListener và @EventListener có khác biệt về kiểu event

`ApplicationListener<E>` giới hạn `E extends ApplicationEvent`. Trong khi đó, `@EventListener` có thể nhận `ApplicationEvent` hoặc object Java thông thường. Spring bọc payload object thành `PayloadApplicationEvent` trong hạ tầng publish.

Điểm này quan trọng khi đọc detector: nó kiểm tra bean có implement interface `ApplicationListener` hay không. Nó không tự biến một bean có method nhận POJO thành ApplicationListener; adapter đó do `EventListenerMethodProcessor` tạo ra.

## 9. Ví dụ hoàn chỉnh: ApplicationListener bean trong Spring 6.2.0

Ví dụ sau dùng Java 17 và Spring Context 6.2.0. Nó đăng ký một listener bean cho event nghiệp vụ và một listener cho `ContextRefreshedEvent`. Không cần tự tạo hoặc đăng ký `ApplicationListenerDetector`; ApplicationContext tự cài internal processor.

**Cấu trúc dự án**

~~~text
application-listener-detector-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationListenerDetectorDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-listener-detector-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationListenerDetectorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ApplicationListenerDetectorDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ApplicationListenerDetectorDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("Publishing ORD-70");
            context.publishEvent(new OrderCreatedEvent(context, "ORD-70"));
        }
    }

    @Configuration
    public static class AppConfig {

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }

        @Bean
        public ApplicationListener<ContextRefreshedEvent> refreshListener() {
            return event ->
                    System.out.println("ContextRefreshedEvent received");
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private static final long serialVersionUID = 1L;

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(
                    "OrderCreatedEvent received: " + event.getOrderId());
        }
    }
}
~~~

**Chạy chương trình**

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
ContextRefreshedEvent received
Publishing ORD-70
OrderCreatedEvent received: ORD-70
~~~

**Diễn giải output**

1. `AnnotationConfigApplicationContext(AppConfig.class)` đăng ký cấu hình và tự refresh context.
2. Trong refresh, `registerListeners()` phát hiện tên hai listener bean và đăng ký bean name với multicaster.
3. Khi các singleton được khởi tạo, `ApplicationListenerDetector` nhận actual instance của `OrderCreatedListener` và `refreshListener` sau initialization, rồi đăng ký instance singleton.
4. `finishRefresh()` phát `ContextRefreshedEvent`, nên `refreshListener` in dòng đầu tiên.
5. Sau khi constructor context trả về, `main` publish `OrderCreatedEvent`; listener nghiệp vụ nhận event và in mã đơn.

Ví dụ này thể hiện registration của ApplicationListener bean trong ApplicationContext. Detector là thành phần nội bộ tự động được cài trong refresh; code ứng dụng chỉ khai báo listener bean và publish event.

## 10. Lỗi đọc source và chẩn đoán thường gặp

- **Nói detector là listener:** Sai vai trò. Detector là BPP; listener bean mới triển khai `ApplicationListener` và nhận event.
- **Cho rằng detector là bean do component scan phát hiện:** Trong Spring 6.2.0, `AbstractApplicationContext.prepareBeanFactory()` add trực tiếp detector vào BeanFactory.
- **Cho rằng detector scan tất cả object trong heap:** Nó chỉ xử lý instance đi qua bean lifecycle của BeanFactory.
- **Cho rằng mọi prototype listener đều bị bỏ qua:** Top-level prototype listener được `registerListeners()` đăng ký bằng bean name; detector không giữ prototype instance cố định.
- **Cho rằng detector phát hiện mọi inner bean:** Detector chỉ có thể đăng ký instance inner bean đủ điều kiện singleton. Inner non-singleton không có top-level bean name ổn định và bị cảnh báo.
- **Cho rằng detector xử lý @EventListener:** Annotation method được xử lý bởi `EventListenerMethodProcessor`, rồi tạo `ApplicationListenerMethodAdapter`.
- **Cho rằng listener được thêm trước init callback:** Detector dùng `postProcessAfterInitialization`, tức sau initialization callback của bean.
- **Cho rằng detector là nơi quyết định async:** Detector chỉ đăng ký listener. Multicaster và `supportsAsyncExecution()` quyết định listener có thể chạy async hay không.
- **Cho rằng registerListeners() khởi tạo hết listener bean:** Spring đăng ký bean names với `allowEagerInit=false`; regular bean initialization diễn ra ở bước tiếp theo.
- **Quên cleanup:** Detector có destruction-aware callback để gỡ singleton listener instance khỏi context khi bean bị hủy.

## 11. Checklist khi debug ApplicationListenerDetector

Khi một listener không nhận event hoặc bị nhận nhiều lần, lần lượt kiểm tra:

1. Bean có thực sự triển khai `ApplicationListener` hay chỉ có method `@EventListener`?
2. Listener là top-level bean, inner bean hay object tự tạo bằng `new`?
3. Scope của bean là singleton hay non-singleton?
4. Top-level bean name có được `registerListeners()` phát hiện qua `getBeanNamesForType(ApplicationListener.class, true, false)` không?
5. Bean đã được khởi tạo để detector chạy `postProcessAfterInitialization` chưa?
6. Listener được đăng ký bằng instance, bean name hay adapter của `@EventListener`?
7. Có hai đường listener riêng cùng xử lý một event dẫn đến duplicate handling không?
8. Context đã hoàn tất refresh và event được publish vào đúng ApplicationContext chưa?
9. Nếu có executor, listener có hỗ trợ async execution và multicaster có cấu hình executor không?

## 12. Ghi nhớ

`ApplicationListenerDetector` là internal BeanPostProcessor được `AbstractApplicationContext` cài sớm trong `prepareBeanFactory()`. Nó quan sát bean instance sau initialization, đăng ký actual singleton `ApplicationListener` instance và gỡ instance khi bean bị hủy.

`registerListeners()` đảm nhận đường đăng ký top-level listener bean names trước khi singleton được khởi tạo; detector bổ sung khả năng phát hiện singleton inner listener bean mà truy vấn bean names không tìm thấy. Top-level non-singleton listener vẫn có thể được đăng ký bằng bean name.

`EventListenerMethodProcessor` là một pipeline độc lập: nó quét method `@EventListener` và tạo ApplicationListener adapter. Trong Spring 6.2, cần phân biệt rõ ba vai trò này khi đọc refresh lifecycle, debug registration timing và xử lý duplicate listener.

## Tài liệu tham khảo — Spring Framework 6.2.0

- [ApplicationListenerDetector.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/support/ApplicationListenerDetector.java)
- [AbstractApplicationContext.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
- [AbstractApplicationEventMulticaster.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java)
- [EventListenerMethodProcessor.java — source tag v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/event/EventListenerMethodProcessor.java)
- [EventListenerMethodProcessor Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [EventListener Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [ApplicationListener Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
- [ApplicationEventMulticaster Javadoc — 6.2.0](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
