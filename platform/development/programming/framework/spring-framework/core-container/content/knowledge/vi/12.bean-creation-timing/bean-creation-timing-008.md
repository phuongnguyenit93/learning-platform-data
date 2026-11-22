# Quan hệ phụ thuộc và thứ tự hủy singleton trong Spring Core Container

## 1. Vì sao thứ tự hủy bean quan trọng?

Khi xây dựng ứng dụng Spring, chúng ta thường tập trung vào **cách tạo bean** và **cách inject dependency**. Nhưng nếu nhiều singleton bean cùng nắm tài nguyên, thứ tự **dừng và giải phóng** chúng cũng quan trọng không kém.

Giả sử:

- `dataStore` đại diện cho một client/connection pool dùng chung.
- `reportWriter` cần `dataStore` để ghi nốt kết quả trong `destroy()`.
- `jobCoordinator` cần `reportWriter` để hoàn tất hoặc yêu cầu flush một công việc trước khi đóng.

Quan hệ phụ thuộc là:

```text
jobCoordinator --> reportWriter --> dataStore
       "dùng"          "dùng"
```

Khi tạo, dependency phải sẵn sàng trước dependent:

```text
dataStore.init
reportWriter.init
jobCoordinator.init
```

Khi hủy, thứ tự mong muốn là **ngược lại**:

```text
jobCoordinator.destroy
reportWriter.destroy
dataStore.destroy
```

Nếu `dataStore` bị đóng trước `reportWriter`, lời gọi flush lúc shutdown của writer có thể thất bại. Đó là lý do Spring quản lý **dependency relationships** và sử dụng chúng cả ở **initialization** lẫn **destruction** của singleton beans.

**Quy tắc cốt lõi:**

> Nếu bean A phụ thuộc bean B theo quan hệ mà Spring biết, Spring cố gắng khởi tạo B trước A và, đối với các singleton được quản lý phù hợp, hủy A trước B.

Quy tắc này đặc biệt được tài liệu hóa cho **`@DependsOn` và XML `depends-on`**. Container còn theo dõi nhiều quan hệ phát sinh khi resolve dependency injection. Nhưng không phải **mọi Java reference ngoài container** đều tự trở thành một quan hệ mà Spring biết.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **phụ thuộc logic**, **injection dependency** và **registered dependency relationship**.
2. Hiểu tại sao thứ tự tạo thường đi từ dependency đến dependent, còn thứ tự hủy đi ngược lại.
3. Dùng `@DependsOn` và XML `depends-on` để biểu thị ràng buộc lifecycle không thể hiện bằng DI.
4. Hiểu các quan hệ được Spring ghi nhận qua constructor/method injection và API `registerDependentBean`.
5. Sử dụng `getDependentBeans(name)` và `getDependenciesForBean(name)` để chẩn đoán dependency graph.
6. Nắm vai trò của `@PreDestroy`, `DisposableBean`, `destroyMethod` và `ApplicationContext.close()`.
7. Phân biệt singleton với prototype, lazy singleton, custom scopes, inner beans và objects nằm ngoài IoC Container.
8. Hiểu những thứ Spring **không** cam kết: thứ tự toàn cục giữa beans không liên hệ, đóng thread tự tạo, readiness của remote services hoặc ordering giữa những ApplicationContexts độc lập.
9. Chạy ví dụ Java 17+/Spring Framework 6.2.19 để kiểm chứng **chain phụ thuộc, DI, XML, lazy và prototype**.
10. Thiết kế shutdown có kiểm thử, tránh mất dữ liệu và lỗi dùng tài nguyên sau khi đã đóng.

## 2. Ba loại quan hệ cần phân biệt

### 2.1. Quan hệ object thực sự: dependency injection

```java
public final class ReportWriter {
    private final DataStore store;

    public ReportWriter(DataStore store) {
        this.store = store;
    }
}
```

Đây là snippet minh họa, cần class/interface `DataStore`. Constructor thể hiện rõ object `ReportWriter` cần object `DataStore`. Khi Spring resolve dependency này, container phải chuẩn bị một candidate phù hợp trước khi có thể truyền vào constructor.

Ví dụ Java configuration:

```java
@Bean
ReportWriter reportWriter(DataStore store) {
    return new ReportWriter(store);
}
```

Hoặc XML:

```xml
<bean id="reportWriter" class="com.example.ReportWriter">
    <constructor-arg ref="dataStore"/>
</bean>
```

Spring còn có thể ghi nhận relation lúc giải quyết dependency để quản lý destruction ordering. Điều này khác với một reference mà code Java tự tạo và giữ bên ngoài bean factory, vì Spring không thể suy luận mọi đối tượng trong JVM.

### 2.2. Phụ thuộc side effect: @DependsOn

```java
@Bean("reportWriter")
@DependsOn("registryInitializer")
ReportWriter reportWriter(DataStore store) {
    return new ReportWriter(store);
}
```

Ở đây có **hai** relation:

- `reportWriter` nhận trực tiếp `DataStore` qua DI.
- `reportWriter` phải đợi `registryInitializer` thực hiện initialization dù không giữ reference của initializer.

`@DependsOn` chính là cách khai báo ràng buộc **bean lifecycle ordering** theo tên khi không có object injection tương ứng. Khi cả hai đều là singletons có destroy callbacks, relation này còn ảnh hưởng thứ tự hủy.

### 2.3. Quan hệ chỉ tồn tại trong business code

```java
public void run() {
    GlobalRegistry.getInstance().publish("report");
}
```

Nếu `GlobalRegistry` do một thư viện tự quản lý, Spring có thể **không biết** bean nào cần sống lâu hơn bean nào. Tương tự, gọi `new ExternalClient()` trong business method không làm external client trở thành một Spring-managed singleton.

**Không được nhầm:** việc “một class có sử dụng một class khác” ở runtime không đồng nghĩa Spring đã lưu một dependency edge để hủy theo đúng thứ tự. Nếu sự tồn tại của dependency là quan trọng, hãy inject một managed bean hoặc khai báo ordering relation đúng nghĩa.

## 3. Từ đồ thị tạo bean đến đồ thị hủy bean

Xem ba singleton:

```text
service -> repository -> connectionPool
```

Mỗi mũi tên `A -> B` nghĩa là **A depends on B**. Ta có thể mô hình hóa:

| Bean | Những dependency cần có trước |
| --- | --- |
| `connectionPool` | Không có |
| `repository` | `connectionPool` |
| `service` | `repository` |

Với quan hệ được container biết, một thứ tự tạo hợp lệ là:

```text
connectionPool -> repository -> service
```

Khi context đóng, một thứ tự hủy hợp lệ là:

```text
service -> repository -> connectionPool
```

Spring không bắt buộc tạo một **thứ tự tuyến tính duy nhất** cho các beans hoàn toàn độc lập. Ví dụ thêm `metricsFormatter` không liên hệ, không nên viết test đòi hỏi formatter nhất định được destroy trước hay sau pool nếu không khai báo quan hệ nào.

### 3.1. Vì sao thứ tự ngược lại?

Dependent bean cần dependency vẫn còn sống trong lúc cleanup. Một ví dụ shutdown:

```text
service.destroy():
    gửi nốt báo cáo qua repository
repository.destroy():
    flush dữ liệu chưa ghi qua connectionPool
connectionPool.destroy():
    đóng pool
```

Nếu connectionPool bị đóng đầu tiên, hai callbacks phía trên có thể không còn sử dụng được nó. Thứ tự ngược với dependency direction giữ resource sống đủ lâu cho dependent cleanup.

### 3.2. “Destroy” chính xác là gì?

Trong Spring, bean destruction có thể kích hoạt các cơ chế như:

- `@PreDestroy` khi hạ tầng Jakarta annotations tương ứng được đăng ký.
- Interface `org.springframework.beans.factory.DisposableBean` với method `destroy()`.
- Custom/inferred destroy method, ví dụ `@Bean(destroyMethod="close")` hoặc `destroy-method="close"`.
- Destruction-aware BeanPostProcessors và callbacks của những scope đặc biệt.

Cơ chế nào chạy, thứ tự callback **bên trong cùng một bean**, và việc suy ra destroy method phụ thuộc metadata/version. **Ordering giữa beans** là một vấn đề khác so với **callback order trong cùng bean**.

## 4. Thứ tự hủy được Spring thực hiện ở đâu?

`ConfigurableApplicationContext.close()` kích hoạt quá trình đóng context. Trong Spring Core Container, phần hủy singleton được thực hiện qua `BeanFactory`/singleton registry, trong đó `DefaultSingletonBeanRegistry` quản lý cached singletons, disposable bean registrations và dependency relations.

Một mô hình khái niệm:

```text
ApplicationContext.close()
             |
             v
        Context shutdown
             |
             v
      Destroy registered singletons
             |
             +--> Nếu X có các dependent beans:
             |       destroy các dependent beans trước
             |
             +--> callback destroy của X
             |
             +--> xử lý liên hệ containment/dependencies
             |
             v
       Singleton registry cleanup
```

**Quan trọng:** thứ tự hủy không được quyết định đơn giản bằng cách đảo ngược thứ tự các dòng XML, tên class, hay `@Bean` method declarations. Dependency graph được ghi nhận trong container có vai trò chủ đạo.

### 4.1. DefaultSingletonBeanRegistry lưu loại dữ liệu nào?

API của `DefaultSingletonBeanRegistry` có các phương thức:

```java
registerDependentBean(String beanName, String dependentBeanName);
getDependentBeans(String beanName);
getDependenciesForBean(String beanName);
```

Cách hiểu:

- `registerDependentBean("store", "writer")`: **writer là dependent của store**. Khi destroy store, phải destroy writer trước.
- `getDependentBeans("store")`: trả tên các beans phụ thuộc store mà registry biết.
- `getDependenciesForBean("writer")`: trả tên các bean mà writer phụ thuộc theo registered dependency relation.

Đây là **Spring container metadata**. Chúng không phải phương thức của application domain `DataStore`, cũng không tự dò mọi Java field reference.

### 4.2. Hai cách đọc ngược chiều

Với `writer depends on store`:

```text
getDependentBeans("store")          -> ["writer"] (quan hệ trực tiếp)
getDependenciesForBean("writer")    -> ["store"]  (quan hệ trực tiếp)
```

Danh sách chính xác còn phụ thuộc những registrations khác trong context. Đừng dựa vào **thứ tự phần tử trả về từ các mảng** để tạo global shutdown order; mục tiêu của hai API là quan sát relation names, không phải cung cấp một schedule đầy đủ cho mọi bean.

### 4.3. Đừng nhầm Dependency API với DI candidate API

`getBeanNamesForType(ReportWriter.class)` tìm beans **theo type**. `getDependentBeans("store")` đọc **registered relations**. Một type có thể tồn tại và được Spring quản lý nhưng không phụ thuộc store; ngược lại quan hệ `depends-on` không bắt buộc Java class chứa field của store.

## 5. Khai báo depends-on trong Java configuration

Một config thường dùng:

```java
@Configuration(proxyBeanMethods = false)
public class ReportsConfig {

    @Bean("store")
    DataStore store() {
        return new DataStore();
    }

    @Bean("writer")
    @DependsOn("store")
    ReportWriter writer() {
        return new ReportWriter();
    }
}
```

Đây là snippet cấu trúc, cần imports `Bean`, `Configuration`, `DependsOn` và hai Java types có constructors phù hợp.

`@DependsOn("store")` đặt trên bean **writer**, nghĩa là writer không được khởi tạo trước store. Nếu là hai managed singletons có destroy callbacks, Spring cũng cần destroy writer trước store.

### 5.1. Không đảo ngược mũi tên

Nếu mục tiêu **writer phải đóng trước store**, đặt:

```java
@Bean("writer")
@DependsOn("store")
ReportWriter writer() {
    return new ReportWriter();
}
```

**Không phải:**

```java
@Bean("store")
@DependsOn("writer")
DataStore store() {
    return new DataStore();
}
```

Đoạn thứ hai lại nói **store phụ thuộc writer** và đảo semantics. Mẹo nhớ: *dependent* là bean đang mang `@DependsOn`; bean được liệt kê là **prerequisite**.

### 5.2. Nhiều dependency names

```java
@Bean("reportProcessor")
@DependsOn({"metricsRegistry", "writeAheadLog"})
ReportProcessor reportProcessor() {
    return new ReportProcessor();
}
```

Cả hai prerequisites được yêu cầu khởi tạo trước processor. Khi hủy singletons, processor bị destroy trước cả hai prerequisites.

**Không suy ra** Spring bắt buộc metricsRegistry được destroy trước hay sau writeAheadLog chỉ vì hai tên xuất hiện theo một thứ tự trong mảng. Nếu hai prerequisites còn quan hệ thứ tự riêng, biểu diễn relation đó trực tiếp.

### 5.3. Annotation class-level và component scan

`@DependsOn` có thể đặt trên một class được component scanning đăng ký:

```java
@Component("reportWorker")
@DependsOn("metricsRegistry")
public class ReportWorker {
}
```

**Giới hạn:** Javadoc `@DependsOn` nêu rằng class-level annotation **chỉ có hiệu lực khi component scanning được dùng**. Nếu class chỉ được đăng ký bằng XML `<bean>`, Spring tôn trọng XML `depends-on` thay vì annotation class-level. Đây là bẫy khi chuyển cấu hình Java/annotation sang XML legacy.

## 6. Khai báo depends-on trong XML

XML có `depends-on` trên phần tử `<bean>`:

```xml
<bean id="reportWriter"
      class="com.example.ReportWriter"
      depends-on="dataStore"/>

<bean id="dataStore"
      class="com.example.DataStore"/>
```

Dù writer xuất hiện **trước store trong file XML**, store vẫn là bean prerequisite. Với hai singleton có destroy callbacks:

```text
Initialization: dataStore -> reportWriter
Destruction:    reportWriter -> dataStore
```

Khi có nhiều prerequisite names:

```xml
<bean id="reportWriter"
      class="com.example.ReportWriter"
      depends-on="metricsRegistry, dataStore"/>
```

Spring hỗ trợ danh sách names phân cách bằng **phẩy, chấm phẩy hoặc khoảng trắng**.

### 6.1. ref và depends-on không giống nhau

XML reference:

```xml
<bean id="reportWriter" class="com.example.ReportWriter">
    <constructor-arg ref="dataStore"/>
</bean>
```

sẽ inject **object bean dataStore** vào constructor.

XML depends-on:

```xml
<bean id="reportWriter" class="com.example.ReportWriter"
      depends-on="dataStore"/>
```

chỉ thêm **ordering constraint**. Nó không truyền object dataStore vào ReportWriter. Nếu writer thực sự cần sử dụng store, constructor/setter injection mới thể hiện dependency đúng về Java type.

### 6.2. XML khai báo bean tên gì?

`depends-on="dataStore"` dùng **bean name hoặc alias hợp lệ**, không phải class name tùy ý. Nếu XML khai báo `<bean id="primaryStore" class="com.example.DataStore"/>`, bạn không thể tự đoán tên `dataStore` từ Java type và mong Spring resolve. Chọn một canonical name ổn định và document quan hệ.

## 7. Phụ thuộc đã có DI còn cần @DependsOn không?

Không phải lúc nào cũng cần. Ví dụ:

```java
@Bean
DataStore store() {
    return new DataStore();
}

@Bean
ReportWriter writer(DataStore store) {
    return new ReportWriter(store);
}
```

Spring phải resolve DataStore trước khi gọi `writer(DataStore store)`. Trong những đường DI tiêu chuẩn, framework còn đăng ký dependent relationship tương ứng nhằm hỗ trợ quản lý destruction.

Nhưng **đừng phát biểu** rằng chỉ vì class A có một field kiểu B thì framework chắc chắn ghi relationship: chỉ những dependencies được container **thực sự resolve và đăng ký** mới có thể quan sát trong registry. Nếu tự `new B()` hoặc gọi một static accessor ngoài Spring, không có guarantee như vậy.

### 7.1. Khi nào thêm @DependsOn có ý nghĩa dù có DI?

Ví dụ service inject `DataStore` nhưng cũng cần `globalCodecRegistrar` đăng ký một static codec không được biểu diễn qua constructor:

```java
@Bean
@DependsOn("globalCodecRegistrar")
ReportWriter writer(DataStore store) {
    return new ReportWriter(store);
}
```

Relation qua constructor bảo đảm DataStore; `@DependsOn` bảo đảm initializer. Điều này hợp lý nếu initializer thực sự cần thiết và có lifecycle managed.

### 7.2. Tránh @DependsOn thừa

Thêm `@DependsOn("store")` cho mọi bean vốn đã constructor-inject store chỉ để “cho chắc” tạo noise và dễ dẫn tới coupling bằng string names. DI rõ kiểu đã diễn đạt object dependency. Chỉ khai báo ordering metadata riêng khi nó có **nghĩa bổ sung**.

## 8. Lifecycle callbacks tham gia destruction

### 8.1. DisposableBean

```java
import org.springframework.beans.factory.DisposableBean;

public final class FileWriterService implements DisposableBean {
    @Override
    public void destroy() {
        // Flush rồi đóng file writer.
    }
}
```

Container gọi `destroy()` khi managed singleton được hủy theo lifecycle phù hợp. Interface phụ thuộc Spring API, nhưng là lựa chọn rõ ràng cho demo kiểm chứng thứ tự.

### 8.2. @PreDestroy

```java
import jakarta.annotation.PreDestroy;

public final class NetworkClient {
    @PreDestroy
    void shutdown() {
        // Gửi tín hiệu đóng tài nguyên.
    }
}
```

Đây là snippet minh họa. Với Spring 6+, cần `jakarta.annotation-api` trên classpath nếu source dùng `jakarta.annotation.PreDestroy` và context có post-processor thích hợp. Java 17 không tự cung cấp tất cả Jakarta annotations.

`@PreDestroy` là **callback của một bean**, không phải cách khai báo một bean cần destroy trước bean khác. Để ràng buộc ordering **giữa beans**, dùng DI/depends-on phù hợp.

### 8.3. @Bean(destroyMethod = "...")

```java
@Bean(destroyMethod = "close")
ClientConnection clientConnection() {
    return new ClientConnection();
}
```

Spring có thể gọi method `close()` khi singleton đóng nếu method hợp lệ và bean được container quản lý. Đây là cách cấu hình không đòi class implement Spring `DisposableBean`.

### 8.4. XML destroy-method

```xml
<bean id="fileClient"
      class="com.example.FileClient"
      destroy-method="close"/>
```

Container biết method cleanup. Nếu `reportWorker` còn dùng fileClient khi destroy, hãy đảm bảo relation qua DI hoặc:

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="fileClient"/>
```

### 8.5. AutoCloseable không phải toàn bộ hợp đồng

Spring có khả năng suy luận destroy methods như `close` hoặc `shutdown` trong nhiều trường hợp bean factory methods có default destroy method inference; tuy nhiên metadata và cách đăng ký bean quyết định việc thực tế callback nào được gọi. Đừng chỉ thấy Java object implement `AutoCloseable` rồi khẳng định mọi container/scope sẽ tự đóng nó. Với tài nguyên critical, cấu hình và kiểm thử destruction path rõ ràng.

### 8.6. Những callback chạy trong một bean

Một bean có thể vừa có `@PreDestroy`, vừa implement `DisposableBean`, vừa có custom destroy method. Spring có thứ tự callback phù hợp, nhưng bài này tập trung vào **thứ tự hủy giữa beans**. Không được suy luận “destroy callback của bean A đã chạy” chỉ từ việc bean B có một annotation khác.

## 9. Ví dụ hoàn chỉnh Java 17+: quan sát cả khởi tạo và hủy

Ví dụ sau dùng **Spring Framework 6.2.19** thuần (không cần Boot), Gradle và hai ApplicationContext APIs.

Nó tạo **năm trường hợp độc lập**:

1. Chuỗi ba singleton với `@DependsOn`.
2. Hai singleton khai báo bằng XML `depends-on`.
3. Hai singleton được kết nối bằng **constructor/method-parameter DI**.
4. Một `@Lazy` singleton vẫn bị non-lazy dependent kéo vào startup.
5. Một prototype bean được tạo, nhưng **không tự có destroy callback khi context đóng**.

Các beans ghi sự kiện thông qua `InitializingBean`/`DisposableBean`. Chương trình in **một thứ tự callback thực tế của các quan hệ đã cấu hình**, không suy đoán từ timestamps hoặc XML line ordering.

### 9.1. Cây thư mục

```text
singleton-shutdown-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ShutdownDemo.java
        └── resources/
            └── beans.xml
```

Một file Java duy nhất với nested public static classes và một resource XML. Tên nested class trong XML dùng **Java binary name** `demo.ShutdownDemo$Tracked`.

### 9.2. settings.gradle

```groovy
rootProject.name = 'singleton-shutdown-demo'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ShutdownDemo'
}
```

Project chỉ cần Spring Context cùng transitive dependencies, Java 17+ và Gradle tương thích Java toolchains. Không có database, network hoặc thư viện Jakarta extra vì demo dùng Spring lifecycle interfaces.

### 9.4. beans.xml

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Worker nằm trước trong XML nhưng phụ thuộc store. -->
    <bean id="xmlWorker"
          class="demo.ShutdownDemo$Tracked"
          depends-on="xmlStore">
        <constructor-arg value="xmlWorker"/>
    </bean>

    <bean id="xmlStore"
          class="demo.ShutdownDemo$Tracked">
        <constructor-arg value="xmlStore"/>
    </bean>

</beans>
```

Hai beans đều là singleton mặc định. `depends-on="xmlStore"` buộc XML store khởi tạo trước worker, và worker hủy trước store.

### 9.5. ShutdownDemo.java

**`src/main/java/demo/ShutdownDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class ShutdownDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static class Tracked
            implements InitializingBean, DisposableBean {

        private final String name;

        public Tracked(String name) {
            this.name = name;
            EVENTS.add(name + ".new");
        }

        @Override
        public void afterPropertiesSet() {
            EVENTS.add(name + ".init");
        }

        @Override
        public void destroy() {
            EVENTS.add(name + ".destroy");
        }
    }

    public static class Client
            implements InitializingBean, DisposableBean {

        private final Tracked store;

        public Client(Tracked store) {
            this.store = store;
            EVENTS.add("diClient.new");
        }

        @Override
        public void afterPropertiesSet() {
            if (store == null) {
                throw new IllegalStateException("missing store");
            }
            EVENTS.add("diClient.init");
        }

        @Override
        public void destroy() {
            EVENTS.add("diClient.destroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChainConfig {

        @Bean("service")
        @DependsOn("repository")
        Tracked service() {
            return new Tracked("service");
        }

        @Bean("repository")
        @DependsOn("cache")
        Tracked repository() {
            return new Tracked("repository");
        }

        @Bean("cache")
        Tracked cache() {
            return new Tracked("cache");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DiConfig {

        @Bean("diStore")
        Tracked diStore() {
            return new Tracked("diStore");
        }

        @Bean("diClient")
        Client diClient(Tracked diStore) {
            return new Client(diStore);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {

        @Bean("lazyStore")
        @Lazy
        Tracked lazyStore() {
            return new Tracked("lazyStore");
        }

        @Bean("lazyWorker")
        @DependsOn("lazyStore")
        Tracked lazyWorker() {
            return new Tracked("lazyWorker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrototypeConfig {

        @Bean("prototype")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        Tracked prototype() {
            return new Tracked("prototype");
        }
    }

    private static void run(
            String label,
            Supplier<? extends ConfigurableApplicationContext> supplier) {

        EVENTS.clear();
        int cutoff;

        try (ConfigurableApplicationContext context = supplier.get()) {
            System.out.println(label + ".init="
                    + String.join(",", EVENTS));

            if ("chain".equals(label)) {
                var factory = context.getBeanFactory();

                boolean cacheHasRepository = Arrays.asList(
                    factory.getDependentBeans("cache")
                ).contains("repository");

                boolean serviceNeedsRepository = Arrays.asList(
                    factory.getDependenciesForBean("service")
                ).contains("repository");

                System.out.println("chain.relations="
                    + cacheHasRepository + ","
                    + serviceNeedsRepository);
            }

            if ("di".equals(label)) {
                var factory = context.getBeanFactory();
                boolean clientDependsOnStore = Arrays.asList(
                    factory.getDependentBeans("diStore")
                ).contains("diClient");

                System.out.println("di.relation="
                    + clientDependsOnStore);
            }

            cutoff = EVENTS.size();
        }

        System.out.println(label + ".destroy="
            + String.join(",",
                EVENTS.subList(cutoff, EVENTS.size())));
    }

    public static void main(String[] args) {

        run("chain", () -> new AnnotationConfigApplicationContext(
            ChainConfig.class));

        run("xml", () -> new ClassPathXmlApplicationContext(
            "beans.xml"));

        run("di", () -> new AnnotationConfigApplicationContext(
            DiConfig.class));

        run("lazy", () -> new AnnotationConfigApplicationContext(
            LazyConfig.class));

        EVENTS.clear();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    PrototypeConfig.class)) {

            context.getBean("prototype");
            System.out.println("prototype.init="
                + String.join(",", EVENTS));
        }

        System.out.println("prototype.destroy-after-close="
            + EVENTS.contains("prototype.destroy"));
    }
}
```

### 9.6. Chạy

Từ thư mục `singleton-shutdown-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows sử dụng:

```bat
gradlew.bat run --quiet
```

Chạy `javac ShutdownDemo.java` độc lập sẽ thiếu Spring classes nếu chưa đặt dependencies vào classpath. Gradle tự compile, resolve thư viện và copy `src/main/resources/beans.xml` vào runtime classpath.

### 9.7. Stdout dự kiến từ các println

```text
chain.init=cache.new,cache.init,repository.new,repository.init,service.new,service.init
chain.relations=true,true
chain.destroy=service.destroy,repository.destroy,cache.destroy
xml.init=xmlStore.new,xmlStore.init,xmlWorker.new,xmlWorker.init
xml.destroy=xmlWorker.destroy,xmlStore.destroy
di.init=diStore.new,diStore.init,diClient.new,diClient.init
di.relation=true
di.destroy=diClient.destroy,diStore.destroy
lazy.init=lazyStore.new,lazyStore.init,lazyWorker.new,lazyWorker.init
lazy.destroy=lazyWorker.destroy,lazyStore.destroy
prototype.init=prototype.new,prototype.init
prototype.destroy-after-close=false
```

Đây là các dòng được chương trình chủ động in bằng `System.out.println`; log từ Gradle/framework, nếu có, không thuộc những dòng này. Recorder chỉ theo dõi các classes `Tracked`/`Client` trong demo, không giả định ghi toàn bộ Spring infrastructure events.

### 9.8. Giải thích case chuỗi @DependsOn

Quan hệ:

```text
service depends on repository
repository depends on cache
```

làm các callbacks chạy theo chuỗi:

```text
cache.new -> cache.init
repository.new -> repository.init
service.new -> service.init
```

Mặc dù `@Bean("service")` được **viết trước** `repository` và `cache` trong source, bean graph quyết định prerequisite ordering.

Khi đóng context:

```text
service.destroy -> repository.destroy -> cache.destroy
```

Đây là **reverse dependency order**, không phải ngẫu nhiên đảo ngược thứ tự source code.

`chain.relations=true,true` xác nhận registry có quan hệ `repository` phụ thuộc `cache` và `service` phụ thuộc `repository`. Hai APIs chỉ đọc metadata relations, không tạo một global shutdown list.

### 9.9. Giải thích case XML

`xmlWorker` được viết trước `xmlStore` nhưng có `depends-on="xmlStore"`. Spring khởi tạo store trước worker. Khi close:

```text
xmlWorker.destroy
xmlStore.destroy
```

Đây là một ví dụ cho thấy **thứ tự dòng trong XML không thay thế dependency declaration**.

### 9.10. Giải thích case DI

`DiConfig.diClient(Tracked diStore)` cần một bean `Tracked`. Trong context `DiConfig` chỉ có một bean type `Tracked` là `diStore`; Spring resolve tham số và ghi nhận quan hệ dependency.

Vì vậy `di.relation=true` từ `getDependentBeans("diStore")` chứng minh BeanFactory đã ghi nhận `diClient` là dependent của `diStore`. Khi close, `diClient.destroy` chạy trước `diStore.destroy`.

Đây là quan hệ do **DI resolution** sinh ra, không cần đặt `@DependsOn("diStore")` trùng lặp. Không mở rộng kết luận này sang mọi cách tự lấy object ngoài container.

### 9.11. Giải thích case lazy

`lazyStore` có `@Lazy` nhưng `lazyWorker` là singleton eager có `@DependsOn("lazyStore")`. Khi BeanFactory tạo lazyWorker trong refresh, nó buộc tạo lazyStore trước; vì vậy `lazy.init` hiển thị cả hai beans đã được khởi tạo trước khi main in.

Khi close, dependent `lazyWorker` bị hủy trước prerequisite `lazyStore`. **@Lazy không làm vô hiệu destruction relation**.

### 9.12. Giải thích case prototype

`PrototypeConfig` khai báo `Tracked` scope prototype. `context.getBean("prototype")` tạo instance và gọi init callback; tuy nhiên Spring **không tự đăng ký destroy callback cho prototype instances như với managed singleton cache**.

Bởi vậy, sau `context.close()`, `prototype.destroy-after-close=false`. Nếu prototype nắm resource cần cleanup, code chủ sở hữu object hoặc cơ chế custom thích hợp phải giải phóng; không đặt kỳ vọng vào singleton destruction order.

### 9.13. Vì sao ví dụ dùng một event list dùng chung?

Năm contexts chạy **tuần tự**, mỗi case gọi `EVENTS.clear()` trước khi tạo context, nên sự kiện được tách biệt. Các beans trong ví dụ sử dụng synchronized-free constructors/init/destruction đồng bộ; không cấu hình background bootstrap hoặc custom threads.

Trong ứng dụng thật, có thể có concurrent startup/background init; khi đó recorder để test cần thread-safe collections/appropriate synchronization và không được đòi hỏi thứ tự của những unrelated beans.

## 10. Tương tác với @Lazy và lazy-init

Một singleton lazy chưa từng được tạo **không có instance để destroy**. Nếu context chỉ đăng ký bean definition:

```java
@Bean
@Lazy
OptionalClient optionalClient() {
    return new OptionalClient();
}
```

mà không ai lookup/inject bắt buộc bean đó, callback cleanup của target có thể không chạy vì chưa có target instance nào tồn tại.

Nhưng:

```java
@Bean
@DependsOn("optionalClient")
CriticalWorker criticalWorker() {
    return new CriticalWorker();
}
```

khi criticalWorker là eager singleton, dependency relation sẽ khiến optionalClient được tạo sớm dù đánh dấu lazy. Khi các singleton này được destroy, criticalWorker bị destroy trước optionalClient.

**Đừng thiết kế cleanup theo giả định tất cả `@Lazy` beans chắc chắn đã được instantiate**. Nếu cần một bean chạy init/destroy không điều kiện trong lifecycle, nó thường không nên là lazy, hoặc cần có cơ chế khởi tạo/warm-up rõ.

## 11. Singleton và prototype có cùng quy tắc hủy không?

Không. `singleton` và `prototype` có lifecycle management khác nhau.

| Trường hợp | Tạo instance | Tự destroy khi ApplicationContext.close()? |
| --- | --- | --- |
| Eager singleton đã tạo | Khi refresh/được yêu cầu | Có, nếu destruction callback thích hợp được đăng ký |
| Lazy singleton chưa tạo | Chưa có instance | Không có target để destroy |
| Lazy singleton đã tạo | Khi được yêu cầu | Có, nếu callback thích hợp |
| Prototype được lookup | Mỗi request tạo instance mới | Container mặc định **không tự gọi configured destruction callbacks** cho prototype |
| Web request/session scope | Theo active scope | Theo semantics và callback management của scope implementation |
| Manually `new` object | Java code tạo | Spring không tự quản lý |
| Inner bean | Khi tạo enclosing bean theo semantics tương ứng | Lifecycle/containment có quy tắc riêng, không đồng nhất với top-level singleton |

### 11.1. Prototype cần explicit cleanup

Nếu prototype implement `AutoCloseable`, caller lấy nó bằng `getBean()` có thể giữ trách nhiệm gọi `close()`. Hoặc ứng dụng dùng custom scope/post-processor để đăng ký destruction theo contract. `ApplicationContext.close()` không phải bộ gom rác tự đóng mọi prototype instances đã từng tạo.

### 11.2. Singleton inject prototype

Một singleton consumer được inject một prototype dependency **một lần lúc consumer được dựng** thường giữ nguyên instance prototype ấy. BeanFactory không tự thay prototype theo mỗi business call; nếu cần object mới cho mỗi call, dùng `ObjectProvider<T>` hoặc phương thức lookup phù hợp. Việc destroy singleton cũng không tự giải quyết tài nguyên của mọi prototype như thể tất cả đều là top-level singleton resources.

### 11.3. Inner bean không đơn giản là prototype

Một `<bean>` nằm trong XML `<constructor-arg>`/`<property>` là inner bean, gắn với enclosing bean. Spring còn có cơ chế **containment relationships** ở singleton registry; đừng nhầm nó với top-level prototype có tên public. Khi inner bean nắm resource cần destroy, cần xem metadata/lifecycle cụ thể và test ownership thực tế.

## 12. Shutdown callbacks và thứ tự của chính một bean

Việc BeanFactory chọn **bean nào được hủy trước** khác với việc Spring chạy **callback nào bên trong bean ấy**.

Ví dụ bean có:

```java
@PreDestroy
void preDestroy() {
}

@Override
public void destroy() {
}

public void close() {
}
```

Snippet này chỉ minh họa các kiểu callback: nó cần import `jakarta.annotation.PreDestroy`, class implement `DisposableBean` và metadata custom `close` mới có đầy đủ semantics.

Một context có thể gọi lifecycle callbacks theo quy tắc xử lý của Spring; không nên viết application logic dựa vào một callback “tình cờ” có mặt khi context thiếu processor/metadata tương ứng.

### 12.1. Không gọi destroy method bằng tay khi container đã quản lý

Nếu lấy singleton từ Spring và tự gọi `destroy()` giữa lúc ứng dụng chạy, Spring vẫn có thể coi bean đang sống trong container, và sau đó gọi destroy callback lúc close. Điều này có thể gây **double-close** hoặc làm những consumers khác dùng resource đã đóng.

Nếu ứng dụng cần chủ động stop/start nhiều lần, hãy thiết kế lifecycle interface/service có contract phù hợp; không coi `DisposableBean.destroy()` là business method để tùy tiện gọi giữa runtime.

### 12.2. Idempotent cleanup

Dù Spring cố điều phối destruction, mã cleanup tài nguyên quan trọng vẫn nên được thiết kế **idempotent** nếu có thể: gọi close hai lần không làm thất thoát/ghi đè dữ liệu hoặc ném lỗi khó phục hồi. Với những thư viện không idempotent, cần một wrapper quản lý trạng thái dừng.

## 13. registerDependentBean: API cho hạ tầng nâng cao

Ngoài metadata `@DependsOn` và XML, `ConfigurableBeanFactory`/`DefaultSingletonBeanRegistry` có API đăng ký quan hệ động:

```java
factory.registerDependentBean("store", "writer");
```

Ý nghĩa **writer depends on store**, nên phải destroy writer trước store.

Đây là API dành cho code hạ tầng/container integration, không phải gợi ý mặc định cho mọi service. Gọi tùy tiện có thể gây side effects khó chẩn đoán; nên khai báo relation sớm, trước quá trình destroy và phù hợp với graph thực tế.

### 13.1. registerDependentBean không inject object

Đăng ký relation không làm:

```java
writer.store = store;
```

hoặc tự gọi một setter. Đây là metadata cho dependency graph và cleanup ordering. Nếu object thực sự cần được truyền vào consumer, vẫn phải dùng DI hoặc lookup có chủ đích.

### 13.2. Relation direction phải chính xác

```java
factory.registerDependentBean("store", "writer");
```

đúng cho relation **writer → store**.

Đảo lại:

```java
factory.registerDependentBean("writer", "store");
```

mô tả **store → writer**, làm đảo shutdown order kỳ vọng. Trong code review hãy viết rõ chú thích “dependent = X, prerequisite = Y”.

### 13.3. Vòng quan hệ

Không tạo cycle như:

```text
A depends on B
B depends on A
```

Framework có cơ chế phát hiện nhiều circular dependency/depends-on relationships và có thể lỗi khi tạo beans. Nếu dùng API registry mức thấp, không dựa vào cách framework có thể tự đoán rồi sửa graph. **Vòng đời không thể có một thứ tự trước/sau hợp lệ cho cycle.**

### 13.4. Factory.getDependenciesForBean là công cụ chẩn đoán

```java
String[] deps = factory.getDependenciesForBean("writer");
```

Nếu mảng chứa `store`, container biết relation này. Không đồng nghĩa writer có Java field tên store, và cũng không mô tả toàn bộ call graph của chương trình.

## 14. @Order không điều khiển thứ tự hủy singleton

`@Order`, `Ordered`, `@Priority` hoặc danh sách beans có thứ tự phục vụ **những extension points cụ thể**; chúng không phải general-purpose shutdown ordering metadata.

Ví dụ:

```java
@Order(1)
@Component
class FirstHandler {
}

@Order(2)
@Component
class SecondHandler {
}
```

Không thể suy luận Spring sẽ destroy `SecondHandler` trước `FirstHandler` chỉ vì giá trị `@Order`. Nếu hai handlers không có dependency relation, không nên xây logic cleanup dựa trên thứ tự in logs tình cờ của một version.

Để điều phối lifecycle khi chúng có dependency thật, dùng **DI** hoặc **`@DependsOn`**. Với một nhóm components cần startup/shutdown phase orchestration, xem `SmartLifecycle` thay vì ép một chuỗi `@Order`.

## 15. @DependsOn so với SmartLifecycle

`@DependsOn` và `SmartLifecycle` giải quyết hai lớp vấn đề:

| Cơ chế | Trách nhiệm |
| --- | --- |
| `@DependsOn` | Bean prerequisite **initialized before** dependent; destroy dependent before prerequisite cho singleton |
| XML `depends-on` | Cùng ý nghĩa ở XML bean definition |
| Constructor injection | Cung cấp object dependency và bảo đảm resolution phù hợp |
| `SmartLifecycle` | Quản lý **start/stop phases** của components có lifecycle chạy/dừng |
| `@Order` | Ordering/precedence của các extension points phù hợp, không phải bean shutdown graph |
| `ApplicationContext.close()` | Kích hoạt context shutdown và bean destruction |
| `@PreDestroy`/`DisposableBean` | Callback cleanup của **một bean instance** |
| `ObjectProvider<T>` | Dynamic dependency lookup, có thể trì hoãn resolution |
| Kubernetes preStop/SIGTERM | Điều phối bên ngoài JVM, không trực tiếp thay bean dependency graph |

### 15.1. Khi cần stop trước nhưng không destroy ngay

Một web server, message listener và queue consumer thường cần **ngừng nhận công việc mới**, **drain công việc đang chạy**, rồi mới **đóng database/pools**. `SmartLifecycle` cung cấp mô hình phase start/stop và callbacks phù hợp hơn cho **coordinated stop**.

`@DependsOn` giúp quản lý bean construction/destruction order, nhưng không thay thế logic **drain**, **timeout** hay ngừng worker threads.

### 15.2. Shutdown của application phức tạp có nhiều giai đoạn

```text
1. Ngừng nhận traffic/message mới
2. Đợi in-flight work hoàn tất trong timeout
3. Flush writers/buffers
4. Đóng các client/pools phụ thuộc
5. Giải phóng infrastructure còn lại
```

Trong một Spring application, có thể cần kết hợp:
- lifecycle stop phases;
- registered depends-on relationships;
- bean destroy callbacks;
- timeout/retry/error handling cho external resources.

Không nên nghĩ chỉ khai báo depends-on names là hoàn thành mọi yêu cầu graceful shutdown của một hệ phân tán.

## 16. Thứ tự hủy có áp dụng giữa hai ApplicationContexts không?

Không như một **global singleton registry**.

Ví dụ:

```java
var parent = new AnnotationConfigApplicationContext(ParentConfig.class);
var child = new AnnotationConfigApplicationContext();
child.setParent(parent);
child.register(ChildConfig.class);
child.refresh();
```

Đây là snippet minh họa, cần `ParentConfig` và `ChildConfig` thật. Root/child contexts có lifecycle và BeanFactories khác nhau. Một bean của child có thể lookup bean của parent theo hierarchy, nhưng không tự suy ra một shutdown order toàn JVM khi ai đó đóng parent trước child.

Nếu một child consumer còn cần parent resource lúc destroy, ứng dụng nên đóng **child trước parent** và có lifecycle ownership rõ ràng. Với contexts độc lập hoàn toàn, một relation theo tên bean trong context A không tạo dependency relation trong registry của context B.

**Không gắn @DependsOn để điều phối shutdown giữa hai microservices hoặc nhiều JVM.** Đó là chuyện orchestration/distributed protocols.

## 17. Phụ thuộc vào @Lazy singleton

Một bean `@Lazy` có bean definition nhưng chưa được tạo. Nếu không bao giờ được yêu cầu, sẽ không có target instance để gọi destroy callback.

```java
@Bean("optionalIndex")
@Lazy
IndexClient optionalIndex() {
    return new IndexClient();
}
```

Nếu không có consumer hoặc getBean nào yêu cầu optionalIndex, context có thể đóng mà không bao giờ tạo `IndexClient`.

Ngược lại:

```java
@Bean("activeSearch")
@DependsOn("optionalIndex")
SearchService activeSearch() {
    return new SearchService();
}
```

Nếu `activeSearch` là eager singleton, BeanFactory sẽ tạo `optionalIndex` trước activeSearch để thỏa depends-on. Khi đóng context, activeSearch phải destroy trước optionalIndex.

### 17.1. Lazy không có nghĩa destroy trước/sau tùy ý

Lazy chỉ ảnh hưởng **thời điểm instantiation**. Khi bean đã được tạo và relation được đăng ký, destruction order vẫn do container graph quyết định. Không dùng `@Lazy` như công cụ “giữ tài nguyên lâu hơn khi shutdown”.

### 17.2. @Lazy trên injection point

`@Lazy` đặt ở injection point có thể tạo lazy-resolution proxy thay vì resolve target ngay. Nếu target được resolve muộn, thời điểm **registered dependency relationship** và destruction semantics có thể khác với direct eager injection; phải kiểm tra loại proxy/scope và quan hệ đang được container ghi nhận. Khi resource cần cleanup ordering chắc chắn, không nên dựa vào việc proxy tình cờ gọi target trước hay sau.

## 18. FactoryBean, aliases và tên bean khi shutdown

### 18.1. Alias là tên tham chiếu, không phải bean instance riêng

```xml
<bean id="primaryStore" class="com.example.Store"/>
<alias name="primaryStore" alias="reportStore"/>
```

`primaryStore` và `reportStore` thường quy về **một bean definition**. Singleton identity và destroy callback gắn với target bean; không có một callback destroy độc lập chỉ vì thêm alias.

### 18.2. FactoryBean có factory và product

Một `FactoryBean<T>` sinh ra product bean, và `&factoryName` thường được dùng để lookup chính factory instance. Đây không phải một alias bình thường. Nếu product/factory nắm tài nguyên khác nhau, hãy kiểm tra bean definition, scope và lifecycle callbacks thay vì chỉ nhìn tên từ `getBean()`.

### 18.3. Synthetic/infrastructure beans

Một số bean definitions do framework tự đăng ký có lifecycle sớm/đặc biệt. `@DependsOn` trên business service không nên được xem là một cơ chế thay đổi toàn bộ processor registration pipeline. Để quản lý framework extension, hãy dùng extension point đã được công bố và kiểm thử startup/shutdown.

## 19. Thực hành chẩn đoán bằng BeanFactory API

Từ `AnnotationConfigApplicationContext` trong ví dụ:

```java
var factory = context.getBeanFactory();

System.out.println(
    Arrays.toString(factory.getDependentBeans("cache")));

System.out.println(
    Arrays.toString(factory.getDependenciesForBean("repository")));
```

Trong `ChainConfig`, điều quan trọng là:

- `getDependentBeans("cache")` chứa `repository`.
- `getDependenciesForBean("repository")` chứa `cache`.

Không nên hard-code một exact string của mảng nếu context có thêm dependent registrations hoặc thứ tự phần tử khác. Dùng:

```java
boolean relationExists = Arrays.asList(
    factory.getDependentBeans("cache")
).contains("repository");
```

### 19.1. Kiểm tra BeanDefinition metadata

```java
var definition =
    factory.getBeanDefinition("service");

String[] explicitNames = definition.getDependsOn();
```

Với ChainConfig, explicitNames bao gồm `repository`. Nhưng `getDependsOn()` là **explicit metadata** từ bean definition; nếu null/rỗng không có nghĩa bean hoàn toàn không có injection dependencies. Muốn xem registered runtime relationships, dùng `getDependenciesForBean`/`getDependentBeans`.

### 19.2. Kiểm tra singleton đã được tạo

```java
boolean created = factory.containsSingleton("cache");
```

Có thể dùng khi debug `@Lazy`: bean definition có thể tồn tại nhưng instance chưa được tạo. Không gọi `getBean("cache")` chỉ để “kiểm tra chưa tạo”, vì lời gọi ấy có thể **kích hoạt tạo bean**.

### 19.3. Đừng quên đóng context trong test

Nếu bạn chỉ tạo `AnnotationConfigApplicationContext` rồi bỏ reference mà không đóng context, không nên trông chờ Spring tự chạy destroy callbacks ngay. Dùng `try-with-resources` hoặc `context.close()` trong test để kích hoạt lifecycle như ví dụ.

## 20. Các lỗi và hiểu lầm phổ biến

### Lỗi 1 — Đọc sai chiều depends-on

`@DependsOn("store")` trên bean writer nghĩa là **writer phụ thuộc store**, không phải store phụ thuộc writer. Init: store trước writer. Destroy: writer trước store.

### Lỗi 2 — Dùng @Order để ép destroy thứ tự

`@Order` không tạo bean dependency relationship. Nó dành cho ordering ở các extension points được hỗ trợ.

### Lỗi 3 — Dựa vào thứ tự khai báo @Bean/XML

Source order không phải hợp đồng lifecycle. Nếu ordering thật sự quan trọng, khai báo DI hoặc depends-on.

### Lỗi 4 — Chỉ nhìn Java fields và đoán container biết dependency

Nếu field được đặt bằng code ngoài Spring hoặc qua static holder, BeanFactory có thể không có registered relation. Đọc dependency graph của container.

### Lỗi 5 — Thêm @DependsOn dù DI đã đủ rõ

Nếu constructor đã inject dependency, `@DependsOn` cùng tên thường thừa. Chỉ thêm khi có side effect prerequisite riêng.

### Lỗi 6 — Đảo tham số registerDependentBean

`registerDependentBean("store","writer")` ghi **writer depends on store**. Đảo tham số sẽ đảo relation.

### Lỗi 7 — Class-level @DependsOn trên bean đăng ký bằng XML

Javadoc nói class-level annotation cần component scanning để áp dụng. Với bean thuần XML, dùng `depends-on` attribute.

### Lỗi 8 — Depends-on trỏ tới bean không tồn tại

Nếu name sai, profile/condition loại target hoặc resource chưa nạp, creation của dependent có thể thất bại. `@DependsOn` không tự khám phá Java class theo type.

### Lỗi 9 — Cycle A phụ thuộc B, B phụ thuộc A

Đây là ordering constraint không thể thỏa. Đổi thứ tự khai báo không sửa được; phải thay thiết kế dependency graph.

### Lỗi 10 — Nghĩ @Lazy sẽ ngăn mọi initialization

Một eager singleton có `@DependsOn` đến lazy bean vẫn có thể buộc lazy bean tạo trong refresh.

### Lỗi 11 — Trông chờ destroy của prototype khi close

Prototype được Spring tạo nhưng container mặc định không theo dõi destruction callback như singleton. Caller phải quản lý tài nguyên.

### Lỗi 12 — Context không được close

Không đóng context thì không có đảm bảo shutdown callbacks sẽ chạy ở thời điểm mong muốn. Khi chạy application, thiết lập shutdown/close handling phù hợp.

### Lỗi 13 — Chỉ có @PreDestroy nhưng thiếu processor/API

Với Spring 6+, cần đúng Jakarta annotation dependencies và annotation processing. Nếu callback không được đăng ký, ordering graph không giúp code shutdown chạy.

### Lỗi 14 — Đóng resource bằng tay trước khi Spring destroy consumers

Một pool do singleton quản lý nhưng bị business code gọi `close()` sớm khiến các consumers vẫn tồn tại mà resource đã đóng. Chọn một lifecycle owner.

### Lỗi 15 — Tin rằng destroy thứ tự giải quyết async readiness

`@DependsOn` không đợi mọi background task hoàn thành. Bean init callback return có thể xảy ra trước task. Khi stop, cần drain/await với timeout.

### Lỗi 16 — Tin rằng shutdown của hai contexts là tự động đồng bộ

Root/child contexts không phải một bean factory duy nhất. Đóng các contexts theo ownership chính xác, thường child trước parent khi child phụ thuộc parent.

### Lỗi 17 — Kiểm thử string order của unrelated beans

Nếu hai beans không có registered dependency edge, không có lý do bắt buộc chúng destroy theo một thứ tự trong test. Chỉ assert relation có hợp đồng.

### Lỗi 18 — Dùng static/global registries vô điều kiện

`@DependsOn` có thể vá order cho legacy, nhưng object graph type-safe qua DI thường rõ nghĩa và dễ test hơn.

### Lỗi 19 — Coi @PreDestroy là graceful-shutdown orchestration đầy đủ

Callback chỉ là bước cleanup của một object. Với message listener, HTTP server, thread pool, cần stop/drain/lifecycle strategy trước khi đóng resources quan trọng.

### Lỗi 20 — Giữ tài nguyên trong unmanaged thread

Spring có thể destroy beans đúng thứ tự nhưng một thread khác vẫn truy cập singleton đã đóng. Thread ownership và shutdown coordination phải được thiết kế riêng.

### Lỗi 21 — Suy luận callback luôn chạy trong shutdown bất thường

Nếu JVM bị `kill -9`, process crash hoặc host dừng đột ngột, callback Spring có thể không có cơ hội chạy. Critical persistence cần transaction/durable queues/flush guarantees phù hợp, không dựa duy nhất vào shutdown hook.

### Lỗi 22 — Không phân biệt lỗi callback và lỗi graph

Nếu dependent.destroy() ném exception, Spring có thể vẫn cố cleanup các beans khác theo contract của container; không nên đặt kỳ vọng một exception làm mọi cleanup dừng hoàn toàn. Log và xử lý lỗi cleanup cẩn thận, tránh che nguyên nhân trước đó.

## 21. Thiết kế graceful shutdown cho service thực tế

Một ứng dụng nhận messages và lưu database thường có:

```text
MessageListener --> JobExecutor --> TransactionalWriter --> DataSource
```

Những bước mong muốn:

1. Ngừng nhận message mới để không phát sinh thêm công việc.
2. Đợi các job đang chạy kết thúc hoặc cancel theo timeout.
3. Flush buffered writes.
4. Hủy writer/adapter đã ngừng sử dụng DataSource.
5. Đóng DataSource/pool sau cùng.

Bean destruction order theo DI/depends-on có thể hỗ trợ một số bước **4 → 5**. Nhưng các bước **1 → 3** cần lifecycle API hoặc application-specific draining policy.

### 21.1. Dùng SmartLifecycle khi phù hợp

`SmartLifecycle` hỗ trợ phases cho lifecycle start/stop của components. Nếu một listener cần dừng trước khi pool bị destroy, có thể đưa listener vào lifecycle orchestration thay vì dựa toàn bộ vào `destroy()`.

Lưu ý **stop phase order không tự động bằng bean destruction order**. Mỗi cơ chế có contract và vị trí trong quá trình close riêng. Hãy test cả việc dừng tiếp nhận công việc và thứ tự đóng tài nguyên.

### 21.2. Bảo đảm destroy idempotent

`destroy()` nên có khả năng chịu được trạng thái đã đóng/dừng nếu thư viện cho phép, và cố gắng không để một failure ở cleanup làm mất thông tin lỗi gốc. Sử dụng logging rõ ràng, resource ownership duy nhất, timeout hữu hạn.

### 21.3. External resources không phải Spring beans

Một broker hoặc database server chạy trên máy khác sẽ không được Spring shutdown theo bean graph trong JVM. Spring chỉ đóng **client/session/pool wrappers** mà application đang sở hữu; external service availability phải được quản lý ở lớp khác.

## 22. Mẫu kiểm thử xác nhận thứ tự

### 22.1. Assert relation thay vì source order

Nếu bean B depends on A, có thể kiểm tra:

```java
int aInit = events.indexOf("A.init");
int bInit = events.indexOf("B.init");

if (!(aInit >= 0 && bInit > aInit)) {
    throw new AssertionError("B initialized before A");
}
```

Đây là snippet minh họa; `events` là một `List<String>` ghi callback events. Với singleton chain, có thể kiểm tra tương tự:

```java
int bDestroy = events.indexOf("B.destroy");
int aDestroy = events.indexOf("A.destroy");

if (!(bDestroy >= 0 && aDestroy > bDestroy)) {
    throw new AssertionError("A destroyed before B");
}
```

### 22.2. Test cần kích hoạt context.close()

Để test destruction callback, buộc context close thực tế:

```java
try (var context =
         new AnnotationConfigApplicationContext(TestConfig.class)) {
    // assert initialization / relations
}
// assert destruction events SAU khi close
```

`TestConfig` là class test minh họa, cần implementation thật. Đừng assert destroy events **trước** khi đóng context.

### 22.3. Test startup graph và shutdown graph

Đừng chỉ assert `A.init < B.init`. Hãy kiểm tra thêm `B.destroy < A.destroy` nếu yêu cầu cleanup order quan trọng. Một configuration có thể khởi tạo đúng do tình cờ nhưng thiếu registered relation nên teardown không có guarantee phù hợp.

### 22.4. Integration test khi dependency được scan

Nếu dùng `@DependsOn` trên class `@Component`, test thực tế với component scan. Nếu đổi sang XML `<bean>`, test lại bằng XML `depends-on` để tránh annotation class-level bị bỏ qua.

### 22.5. Prototype test

Tạo prototype, xác nhận constructor/init chạy; close context rồi xác nhận destroy chưa chạy tự động. Nếu prototype nắm tài nguyên, test riêng cleanup do owner thực hiện.

## 23. Câu hỏi ôn tập có đáp án

**Câu 1.** Với A depends on B, bean nào khởi tạo trước?

**Đáp:** B trước A.

**Câu 2.** Với hai singleton A depends on B, bean nào được hủy trước?

**Đáp:** A trước B.

**Câu 3.** `@DependsOn("store")` có tự inject store vào field của bean không?

**Đáp:** Không. Nó khai báo initialization/destruction relationship theo tên, không cấp object reference.

**Câu 4.** Constructor injection có thể ảnh hưởng shutdown order không?

**Đáp:** Có. Với các dependency được BeanFactory resolve và đăng ký quan hệ, container có thể dùng relation đó để hủy dependent trước dependency.

**Câu 5.** `getDependentBeans("store")` khác `getDependenciesForBean("store")` thế nào?

**Đáp:** Cái đầu liệt kê beans phụ thuộc store; cái sau liệt kê beans mà store phụ thuộc.

**Câu 6.** Vì sao `@Order(1)` không đủ để quản lý shutdown?

**Đáp:** `@Order` không tạo explicit bean dependency relationship cho destruction registry.

**Câu 7.** XML `depends-on="cache,metrics"` có yêu cầu cache hủy trước metrics không?

**Đáp:** Không theo nghĩa hai prerequisites phải có total order với nhau; nó buộc bean dependent hủy trước từng prerequisite.

**Câu 8.** Bean có `@Lazy` nhưng chưa bao giờ tạo có chạy destroy không?

**Đáp:** Không có instance để destroy.

**Câu 9.** Singleton eager A depends on lazy singleton B, B có thể bị tạo trong startup không?

**Đáp:** Có. A buộc phải đợi B khởi tạo.

**Câu 10.** Prototype bean implement `DisposableBean` sẽ tự destroy khi context close không?

**Đáp:** Mặc định không. Client/cơ chế quản lý phù hợp phải cleanup prototype instances.

**Câu 11.** `registerDependentBean("pool","worker")` biểu thị chiều nào?

**Đáp:** Worker depends on pool; destroy worker trước pool.

**Câu 12.** `getDependenciesForBean("worker")` có thể trả null vì thiếu depends-on?

**Đáp:** API trả mảng tên hoặc mảng rỗng khi không có registered dependencies; `BeanDefinition.getDependsOn()` mới có thể trả null khi không khai báo explicit depends-on metadata.

**Câu 13.** @PreDestroy và @DependsOn có cùng tác dụng không?

**Đáp:** Không. `@PreDestroy` là callback cleanup của một bean; `@DependsOn` xác định thứ tự giữa các beans.

**Câu 14.** Có thể dựa vào thứ tự khai báo bean trong Java file không?

**Đáp:** Không để bảo đảm lifecycle ordering. Cần DI hoặc explicit depends-on.

**Câu 15.** Tại sao một static global registry khó an toàn khi shutdown?

**Đáp:** Container có thể không thấy quan hệ giữa consumers với registry. Prefer DI hoặc declare explicit dependency relationship khi phù hợp.

**Câu 16.** Nếu background task chưa kết thúc khi initializer return, @DependsOn có tự chờ không?

**Đáp:** Không. Nó chờ bean initialization theo Spring lifecycle, không chờ mọi tác vụ bên ngoài.

**Câu 17.** Spring có tự điều khiển thứ tự hủy beans ở hai independent ApplicationContexts không?

**Đáp:** Không. Cần quản lý close order giữa contexts riêng.

**Câu 18.** Khi nào cần SmartLifecycle hơn chỉ destroy callbacks?

**Đáp:** Khi cần có giai đoạn start/stop/drain, phase ordering và coordinated shutdown trước khi singleton resources bị hủy.

## 24. Checklist ứng dụng

- [ ] Vẽ graph “A dùng B” cho các singleton quan trọng.
- [ ] Dùng constructor injection khi B là object dependency thật sự của A.
- [ ] Dùng `@DependsOn`/`depends-on` cho side effect/init prerequisite không biểu diễn qua DI.
- [ ] Kiểm tra đúng chiều: dependent mang annotation, prerequisite nằm trong list names.
- [ ] Không tạo cycle trong graph.
- [ ] Đặt tên bean ổn định; xem xét aliases/profiles/conditions.
- [ ] Xác nhận bean thực sự được container quản lý, không phải manually `new`.
- [ ] Kiểm tra các beans cleanup có `@PreDestroy`/`DisposableBean`/destroyMethod hợp lệ.
- [ ] Test cả initialization **và** destruction relation.
- [ ] Không assert order cho unrelated beans.
- [ ] Kiểm tra prototype/lazy/custom scopes khác singleton.
- [ ] Không bỏ qua parent-child contexts và resource ownership.
- [ ] Dùng `getDependentBeans`/`getDependenciesForBean` để debug graph thực tế.
- [ ] Với task async/web consumers, thiết kế stop/drain và timeouts bên cạnh destroy callback.
- [ ] Đừng dựa vào shutdown callback để thay thế data durability trên process crash.
- [ ] Quan sát logs, resource leaks và warnings khi deploy/stop thực tế.

## 25. Tài liệu chính thức

- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): bảo đảm initialization và destruction ngược chiều của singleton.
- [Spring Framework 6.2.19 — DependsOn Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): định nghĩa, TYPE/METHOD targets, giới hạn class-level khi đăng ký XML.
- [Spring Framework 6.2.19 — DefaultSingletonBeanRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/DefaultSingletonBeanRegistry.html): `registerDependentBean`, `getDependentBeans`, `getDependenciesForBean`, `destroySingletons`.
- [Spring Framework 6.2.19 — ConfigurableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): xem registered bean dependencies và quản lý destruction.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): init/destroy methods, `InitializingBean`, `DisposableBean` và annotation callbacks.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype và giới hạn destruction của prototype.
- [Spring Framework — ApplicationContext Shutdown](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle khi đóng container.
- [Spring Framework — SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/SmartLifecycle.html): phase-based startup/shutdown orchestration.

**Kết luận:** Spring không chỉ tạo beans theo dependency graph; với những managed singletons có quan hệ phụ thuộc được container nhận biết, nó còn **hủy dependent trước dependency** để tài nguyên prerequisite còn sống trong lúc dependent cleanup. `@DependsOn`/XML `depends-on` là cách khai báo explicit cho quan hệ không biểu diễn bằng DI; `getDependentBeans` và `getDependenciesForBean` giúp kiểm chứng graph. Đừng nhầm thứ tự hủy singleton với prototype destruction, thứ tự `@Order`, hay graceful shutdown của threads và external services. Hãy để **DI biểu diễn object dependency, depends-on biểu diễn lifecycle constraint và lifecycle APIs xử lý stop/drain**.
