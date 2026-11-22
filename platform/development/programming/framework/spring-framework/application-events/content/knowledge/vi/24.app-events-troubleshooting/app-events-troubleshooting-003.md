# Bean listener không được scan trong Spring Application Events

Một tình huống quen thuộc khi sử dụng **Spring Framework Application Events**: service gọi `ApplicationEventPublisher.publishEvent(...)` không báo lỗi, nhưng phương thức gắn `@EventListener` không in log và không thực hiện công việc. Một nguyên nhân rất phổ biến là **class chứa listener không được đăng ký thành Spring bean** do nằm ngoài phạm vi component scan, thiếu stereotype annotation, bị filter loại trừ, hoặc bị điều kiện cấu hình vô hiệu hóa.

Điểm cốt lõi: **`@EventListener` chỉ đánh dấu một phương thức xử lý event trên một bean đã được Spring quản lý; bản thân annotation này không đăng ký class thành bean.** Nếu class không thuộc `ApplicationContext` đang phát event, Spring không có listener method nào để gọi.

Bài học này hướng dẫn phân biệt lỗi **không được scan/không có bean** với các nguyên nhân khác cùng biểu hiện “không nhận event”: sai kiểu payload, điều kiện `@EventListener`, context chưa refresh, event quá sớm, transaction không tồn tại, listener chạy bất đồng bộ hoặc sự cố ở context hierarchy.

## 1. Cơ chế: từ class trên classpath đến một event listener thực sự

Một phương thức `@EventListener` chỉ có thể được sử dụng khi các bước cần thiết đã xảy ra:

```text
Class OrderPlacedListener có trong JAR / classpath
            |
            v
@ComponentScan quét đúng package và class qua các bộ lọc?
            |
            +-- KHÔNG --> không có bean definition
            |             -> @EventListener không được đăng ký
            |
            +-- CÓ --> bean definition được đăng ký
                           |
                           v
                    Bean được tạo/khởi tạo theo lifecycle
                           |
                           v
                    EventListenerMethodProcessor
                    phát hiện @EventListener
                    và tạo listener adapter
                           |
                           v
                    ApplicationEventMulticaster
                    có listener phù hợp với event
                           |
                           v
                    Publisher phát event đúng type/context
                           |
                           v
                    Listener method được gọi
```

`@ComponentScan` tìm kiếm các **candidate components** trên classpath theo base package và bộ lọc. Các class được đánh dấu `@Component`, `@Service`, `@Repository`, `@Controller` hoặc các custom stereotype được meta-annotate đúng cách có thể được phát hiện, nhưng vẫn phải nằm trong vùng quét. Ngoài component scanning, bean cũng có thể được đăng ký **tường minh** qua `@Bean`, `@Import` hoặc các API đăng ký bean definition.

`EventListenerMethodProcessor` xử lý `@EventListener` trên Spring-managed beans trong giai đoạn xử lý bean/context. Với `ApplicationContext` đã khởi tạo đúng cách, bạn thường **không cần** đăng ký processor này bằng tay. Nhưng nếu tự tạo đối tượng bằng `new` mà không khai báo nó là bean, processor sẽ không xem xét đối tượng đó.

### Một ví dụ sai rất điển hình

```java
package com.acme.listeners;

import org.springframework.context.event.EventListener;

public class OrderPlacedListener {

    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Received " + event.orderId());
    }
}
```

Đây là **mã minh họa**, giả định `OrderPlaced` đã được import hoặc khai báo phù hợp. Class không có `@Component` và cũng không được khai báo qua `@Bean`/`@Import`, vì vậy không có lý do gì để Spring tự đăng ký nó là bean.

Thêm `@Component` là một bước cần thiết **nếu dùng component scanning**, nhưng **chưa đủ** nếu package `com.acme.listeners` nằm ngoài base packages đang được scan.

## 2. Kiểm tra vị trí package: nguyên nhân thường gặp nhất trong Spring Boot

Khi ứng dụng dùng `@SpringBootApplication`, annotation này bao gồm cơ chế component scan. Theo cách cấu hình thông thường, phạm vi quét bắt đầu từ **package chứa class khởi động** và đi xuống các **subpackage**.

### 2.1. Bố cục sai: listener là package ngang cấp

```text
src/main/java/
└── com/acme/
    ├── app/
    │   ├── StoreApplication.java
    │   └── service/
    │       └── OrderService.java
    └── listeners/
        └── OrderPlacedListener.java
```

Ví dụ `StoreApplication`:

```java
package com.acme.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    // main(...) gọi SpringApplication.run(...).
}
```

Mặc định, scan bắt đầu tại `com.acme.app`, bao gồm `com.acme.app.service`. Nó **không mặc nhiên bao gồm `com.acme.listeners`** vì đây là một package **ngang cấp**, không phải subpackage. `OrderPlacedListener` có `@Component` vẫn bị bỏ qua trong bố cục này.

### 2.2. Cách sửa 1: đặt class khởi động ở root package chung

```text
com/acme/
├── StoreApplication.java       <-- @SpringBootApplication ở com.acme
├── app/service/OrderService.java
└── listeners/OrderPlacedListener.java
```

Khi `StoreApplication` nằm ở `com.acme`, mặc định component scan phủ các package con. Đây thường là cách đơn giản và dễ bảo trì đối với ứng dụng Spring Boot một context.

**Không đặt class khởi động ở default package** (không khai báo `package`). Điều đó có thể khiến Spring phải scan quá rộng, gây vấn đề hiệu năng và đăng ký bean không mong muốn.

### 2.3. Cách sửa 2: chỉ định các package cần quét

Nếu cấu trúc dự án không cho phép di chuyển class khởi động:

```java
package com.acme.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = {
        "com.acme.app",
        "com.acme.listeners"
})
public class StoreApplication {
}
```

Đây là **đoạn cấu hình minh họa**, không độc lập. Có thể ưu tiên biến thể **type-safe**:

```java
@SpringBootApplication(scanBasePackageClasses = {
        StoreApplication.class,
        OrderPlacedListener.class
})
public class StoreApplication {
}
```

Khi dùng biến thể trên, cần import `OrderPlacedListener`. Spring sẽ dùng **package của từng class** làm mốc quét. Đây là cách tránh lỗi chính tả chuỗi package khi refactor.

**Lưu ý giới hạn:** `scanBasePackages`/`scanBasePackageClasses` điều khiển **component scan**, không tự thay thế mọi quy tắc quét entity JPA hoặc Spring Data repositories. Nếu ứng dụng có JPA/repository ở package khác, hãy kiểm tra riêng cấu hình `@EntityScan` hoặc `@EnableJpaRepositories` khi cần. Đừng sửa một lỗi listener bằng cách mở rộng scanning vô tội vạ cho toàn bộ dependencies.

### 2.4. Cách sửa 3: đăng ký chính xác bean listener

Khi chỉ cần một listener ngoài vùng scan, có thể khai báo tường minh:

```java
@Configuration
@Import(OrderPlacedListener.class)
class EventListenerConfiguration {
}
```

Hoặc:

```java
@Configuration
class EventListenerConfiguration {

    @Bean
    OrderPlacedListener orderPlacedListener() {
        return new OrderPlacedListener();
    }
}
```

Đây là **hai phương án minh họa tách biệt**, mỗi phương án cần import phù hợp, và `EventListenerConfiguration` cũng phải là configuration class được Spring nạp. Không áp dụng cả hai nếu chúng vô tình tạo **hai bean listener** cùng xử lý một event. Một listener không nhất thiết phải có `@Component` nếu nó đã được khai báo bằng `@Bean`.

## 3. Thực hành Java 17+ chạy được: quét thiếu listener, rồi sửa component scan

Ví dụ thuần **Spring Framework 6.2.9**, không cần Spring Boot hay cơ sở dữ liệu. Hai `ApplicationContext` được tạo tuần tự với cấu hình khác nhau:

1. `ServiceOnlyConfig` chỉ quét `example.service`, nên `OrderService` là bean nhưng `OrderPlacedListener` không phải bean. Service vẫn publish event; listener không in gì.
2. `ServiceAndListenerConfig` quét cả `example.service` và `example.listener`, nên listener là Spring bean; cùng một kiểu event được xử lý bình thường.

Cấu trúc này cho thấy sự khác biệt do **component scan**, không phải do event API hoặc cấu hình transaction.

### 3.1. Cấu trúc thư mục

```text
listener-scan-demo/
├── pom.xml
└── src/main/java/example/
    ├── ScanDiagnosisDemo.java
    ├── config/
    │   ├── ServiceOnlyConfig.java
    │   └── ServiceAndListenerConfig.java
    ├── events/
    │   └── OrderPlaced.java
    ├── service/
    │   └── OrderService.java
    └── listener/
        └── OrderPlacedListener.java
```

Các file được lưu đúng đường dẫn tương ứng với dòng `package`. Không bỏ chung nhiều class `public` vào một file Java.

### 3.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>listener-scan-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ScanDiagnosisDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. src/main/java/example/events/OrderPlaced.java

```java
package example.events;

public record OrderPlaced(String orderId) {
}
```

Java record là payload event bình thường; không bắt buộc kế thừa `ApplicationEvent`. Khi dùng `publishEvent(Object)`, Spring có thể đóng gói payload này thành `PayloadApplicationEvent` và lựa chọn `@EventListener` theo kiểu payload.

### 3.4. src/main/java/example/service/OrderService.java

```java
package example.service;

import example.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void place(String orderId) {
        System.out.println("service: publish " + orderId);
        publisher.publishEvent(new OrderPlaced(orderId));
    }
}
```

Service là Spring bean vì có `@Service` và được quét bởi cả hai cấu hình. `ApplicationEventPublisher` là dependency do Spring cung cấp. `place(...)` in một dòng trước khi publish để cho thấy việc gọi publisher **không bắt buộc phải thất bại khi không có listener**.

### 3.5. src/main/java/example/listener/OrderPlacedListener.java

```java
package example.listener;

import example.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPlacedListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("listener: received " + event.orderId());
    }
}
```

Class có `@Component`, phương thức có `@EventListener`. Đây là cấu hình listener hợp lệ **nếu `example.listener` được scan**; không cần implement `ApplicationListener<?>`.

### 3.6. src/main/java/example/config/ServiceOnlyConfig.java

```java
package example.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "example.service")
public class ServiceOnlyConfig {
}
```

Chỉ quét `example.service`, nên `OrderService` có trong context. Class `example.listener.OrderPlacedListener` nằm ngoài vùng scan, dù hoàn toàn có mặt trên classpath.

### 3.7. src/main/java/example/config/ServiceAndListenerConfig.java

```java
package example.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = {
        "example.service",
        "example.listener"
})
public class ServiceAndListenerConfig {
}
```

Điểm khác với `ServiceOnlyConfig` chỉ nằm ở **base packages của `@ComponentScan`**.

### 3.8. src/main/java/example/ScanDiagnosisDemo.java

```java
package example;

import example.config.ServiceAndListenerConfig;
import example.config.ServiceOnlyConfig;
import example.listener.OrderPlacedListener;
import example.service.OrderService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ScanDiagnosisDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ServiceOnlyConfig.class)) {

            int listenerBeans =
                    context.getBeanNamesForType(
                            OrderPlacedListener.class).length;

            System.out.println(
                    "case=missing listenerBeans=" + listenerBeans);
            context.getBean(OrderService.class).place("PO-42");
        }

        try (var context =
                     new AnnotationConfigApplicationContext(
                             ServiceAndListenerConfig.class)) {

            int listenerBeans =
                    context.getBeanNamesForType(
                            OrderPlacedListener.class).length;

            System.out.println(
                    "case=fixed listenerBeans=" + listenerBeans);
            context.getBean(OrderService.class).place("PO-43");
        }
    }
}
```

Chạy từ thư mục dự án, cần JDK 17+ và Maven (lần đầu có thể cần tải dependencies):

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình in**, theo thứ tự (bỏ qua log khác của Maven/Spring):

```text
case=missing listenerBeans=0
service: publish PO-42
case=fixed listenerBeans=1
service: publish PO-43
listener: received PO-43
```

**Phân tích từng bước:**

1. Context thứ nhất được tạo bằng `ServiceOnlyConfig`; Spring scan `example.service`, đăng ký `OrderService`, nhưng không scan `example.listener`. Kết quả `listenerBeans=0`.
2. `OrderService.place("PO-42")` vẫn gọi `publishEvent` bình thường. Không có bean `OrderPlacedListener` trong context để đăng ký phương thức xử lý `@EventListener`, nên không có dòng `listener: received PO-42`.
3. Context thứ nhất được đóng; context thứ hai được tạo **mới và độc lập** để tránh trạng thái bean còn sót.
4. Context thứ hai scan cả hai package; Spring có `OrderPlacedListener` bean, `EventListenerMethodProcessor` xử lý phương thức listener khi context refresh. Kết quả `listenerBeans=1`.
5. `OrderService.place("PO-43")` publish cùng kiểu payload `OrderPlaced` và listener in `listener: received PO-43`.

Ví dụ cố ý không tạo async executor, condition hoặc transaction; vì vậy nó cô lập được **nguyên nhân scan**. Nếu một ứng dụng thật có custom multicaster hoặc transaction-bound listener, cần thêm kiểm tra tương ứng ở các mục sau.

## 4. Quy trình chẩn đoán: từ “không in log” đến nguyên nhân cụ thể

Không nên sửa `@ComponentScan` ngay khi không thấy log. Trước hết cần xác định **listener có phải Spring bean không**. Đây là điểm phân nhánh hữu ích nhất.

### Bước 1: xác minh đang làm việc với đúng ApplicationContext

Một ứng dụng có thể có parent/child contexts, context cho test, context web riêng hoặc nhiều `SpringApplication` được khởi động. Việc một listener là bean trong **context A** không chứng minh event được phát trong **context B** sẽ đến được listener đó.

Trong Spring context hierarchy, event từ **child có thể được chuyển lên parent**; event ở parent **không tự động gửi xuống tất cả child**. Đừng giả định hai context là một event bus toàn cục.

Cần biết publisher nào đã inject vào service và bean nào thuộc context tương ứng. Trong test, đảm bảo producer và listener thuộc **cùng một context hoặc hướng truyền event hợp lệ**.

### Bước 2: xác nhận listener bean có mặt không

Trong một thành phần chẩn đoán được Spring quản lý, có thể kiểm tra:

```java
String[] beans = applicationContext.getBeanNamesForType(
        OrderPlacedListener.class);
System.out.println("listener bean count=" + beans.length);
```

Đây là **mã minh họa**; `applicationContext` và `OrderPlacedListener` là đối tượng/kiểu trong ứng dụng. `getBeanNamesForType(...)` kiểm tra bean theo type trong context, không phải tìm class trên filesystem.

Phân biệt:

- **`0` bean:** listener chưa được đăng ký, bị condition loại hoặc đang ở context khác. Cần điều tra `@ComponentScan`, `@Component`, `@Bean`, `@Profile`, `@Conditional...`.
- **`1` bean:** bean đã có. Chưa bảo đảm phương thức `@EventListener` được đăng ký, nhưng lỗi **scan thiếu class** không còn là kết luận chính.
- **Nhiều bean:** có thể vô tình đăng ký cùng listener qua `@Component` và `@Bean`; nguy cơ xử lý event nhiều lần. Kiểm tra bean names/configuration.

Đừng dùng `Class.forName("...OrderPlacedListener")` để chứng minh listener có bean: class có trên classpath **khác với** bean đã đăng ký trong `ApplicationContext`.

### Bước 3: xác định scan base package

Kiểm tra package của class có `@SpringBootApplication` hoặc `@ComponentScan`, ví dụ:

```java
@SpringBootApplication
public class StoreApplication {
}
```

Nếu `StoreApplication` ở `com.acme.app`, hãy so path package của listener:

```text
com.acme.app.listener.OrderPlacedListener      -> nằm dưới vùng quét
com.acme.listeners.OrderPlacedListener         -> nằm ngoài vùng quét
```

Trong dự án nhiều module Maven/Gradle, còn phải bảo đảm module chứa listener **đã được thêm vào runtime classpath**. Nếu JAR module không có trong dependencies, thay base package cũng không làm Spring tìm thấy class.

### Bước 4: xem annotation và bộ lọc

Class được quét phải là candidate hợp lệ. Ví dụ:

```java
@Component
public class OrderPlacedListener {
    @EventListener
    public void on(OrderPlaced event) {
        // ...
    }
}
```

Đoạn này **chưa đủ** để bảo đảm listener được gọi: vẫn cần vùng scan đúng, bean active, event type phù hợp và lifecycle hợp lệ.

Hãy tìm:

- Có thiếu `@Component`/`@Service` hoặc không có `@Bean`/`@Import`?
- Có `@ComponentScan(useDefaultFilters = false)` nhưng thiếu `includeFilters` cần thiết?
- Có `excludeFilters` loại theo type/annotation/package?
- Có custom stereotype nhưng chưa meta-annotate `@Component` đúng cách?
- Có `@Profile("prod")` nhưng đang chạy profile `test` hoặc `dev`?
- Có `@ConditionalOnProperty`, `@ConditionalOnBean`, feature flag hoặc condition khác khiến bean bị loại? Các condition kiểu này thường nằm trong Spring Boot.
- Có `@Lazy` trên bean chứa `@EventListener`? Theo tài liệu Spring, việc đánh dấu bean listener lazy có thể khiến listener method **không được đăng ký** như kỳ vọng, vì container tôn trọng lazy bean và không khởi tạo nó cho mục đích listener registration.
- Có lỗi khởi tạo bean khiến cả context fail trước khi có thể phát event?

Nếu class có mặt và bean được đăng ký nhưng phương thức vẫn không nhận event, đừng dừng ở kết luận “scan lỗi”. Kiểm tra event processor/lifecycle/multicaster theo bước kế tiếp.

### Bước 5: chứng minh event được publish và đúng kiểu

Gắn log hoặc test ở chỗ phát:

```java
System.out.println("publish OrderPlaced id=" + orderId);
applicationEventPublisher.publishEvent(new OrderPlaced(orderId));
```

Đây là **mã minh họa**. Một dòng log trước `publishEvent` xác minh code đi tới nhánh gọi publisher, **không xác minh listener chạy xong**. Với `SimpleApplicationEventMulticaster` đồng bộ mặc định, listener nhận event phù hợp trên thread publisher; với `@Async` hoặc multicaster executor, publisher có thể trả về trước khi listener bắt đầu.

Kiểm tra kiểu listener và payload:

```java
@EventListener
public void handle(OrderPlaced event) {
    // Nhận đúng OrderPlaced.
}
```

Nếu publisher gửi `PaymentPlaced`, listener trên không có lý do được gọi. Với POJO, Spring có thể đóng gói trong `PayloadApplicationEvent`; `@EventListener` khai báo kiểu POJO vẫn hợp lệ. Nhưng một listener khai báo kiểu wrapper khác không mặc nhiên khớp mọi payload.

Cũng cần kiểm tra `@EventListener(condition = "...")`: khi biểu thức SpEL trả về false, listener bị **bỏ qua có chủ ý**, không phải lỗi scanning. Với generic event, phải có metadata kiểu đủ để Spring phân biệt ở runtime nếu hợp đồng cần.

### Bước 6: phân biệt event thường với transactional event

Một phương thức:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    // ...
}
```

là **transaction-bound listener**, không tương đương `@EventListener` chạy ngay. Mặc định `fallbackExecution = false`: nếu không có transaction phù hợp, listener **không chạy**, dù bean đã được scan đúng và publisher đã phát event.

Các pha thường dùng:

| Pha | Khi callback chạy |
| --- | --- |
| `BEFORE_COMMIT` | Trước commit transaction nguồn |
| `AFTER_COMMIT` | Sau commit thành công |
| `AFTER_ROLLBACK` | Sau rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất bất kể kết quả |

Ví dụ trong `@Transactional` test được Spring tự rollback sau method, listener `AFTER_COMMIT` **không chạy** nếu transaction chưa commit. Không sửa scan hoặc bật `fallbackExecution = true` chỉ để che một thiết kế transaction sai.

Với reactive transaction, ngữ cảnh giao dịch nằm trong **Reactor Context**, không giống `ThreadLocal` của transaction imperative. Khi phát transactional event trong reactive pipeline, cần tuân thủ API `TransactionalEventPublisher`/`TransactionContext`; context propagation cho logging không tự thay thế transaction propagation.

### Bước 7: kiểm tra timing, async và exception

Một listener bean thông thường chỉ được tạo/đăng ký ở giai đoạn context lifecycle thích hợp. Các sự kiện **Spring Boot startup sớm**, như `ApplicationStartingEvent` hay `ApplicationEnvironmentPreparedEvent`, xảy ra trước lúc các bean ứng dụng sẵn sàng. Dùng `SpringApplication.addListeners(...)` hoặc đăng ký early listener qua `META-INF/spring.factories` theo cơ chế được Spring Boot hỗ trợ nếu cần nhận các event sớm đó.

Với `@Async`:

- Listener có thể chạy sau khi log publisher đã in và request hoàn thành.
- Exception trên worker không tự ném về thread publisher. Với `void` async có thể cần `AsyncUncaughtExceptionHandler` hoặc logging/monitoring phù hợp.
- ThreadLocal/MDC/trace context không tự động truyền qua mọi executor.
- Test cần điểm đồng bộ xác định; không kết luận “không được scan” chỉ vì chưa thấy log sau một khoảng delay ngẫu nhiên.

Với multicaster đồng bộ, nếu **listener đầu tiên ném exception**, các listener sau có thể không được gọi. Điều này có thể tạo biểu hiện “listener B không chạy”, nhưng thực chất bean B đã tồn tại. Kiểm tra stack trace, ErrorHandler và thứ tự listener khi liên quan.

## 5. Sửa scan thế nào cho đúng trong dự án nhiều module?

Một ứng dụng có thể chia thành:

```text
store-app/                   <-- Spring Boot main
store-domain/                <-- OrderPlaced
store-notifications/         <-- OrderPlacedListener
store-data/                  <-- repositories
```

Có **hai điều kiện độc lập**:

1. Module `store-notifications` phải có mặt trong **runtime dependencies/classpath** của `store-app`.
2. Package Java chứa `OrderPlacedListener` phải được đưa vào scan hoặc listener phải được **đăng ký tường minh**.

Ví dụ Maven dependency minh họa (**groupId, artifactId là giả định của dự án**):

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>store-notifications</artifactId>
    <version>1.0.0</version>
</dependency>
```

Chỉ thêm dependency không luôn đủ: nếu jar được load nhưng class nằm ngoài base scan, vẫn không có bean. Ngược lại, chỉ mở rộng `scanBasePackages` cũng không giúp nếu artifact chưa nằm trên classpath.

**Một cách ổn định cho module mở rộng có chủ đích** là đưa một `@Configuration` trong module vào ứng dụng thông qua `@Import`, ví dụ:

```java
@Configuration
@Import(NotificationModuleConfiguration.class)
class StoreIntegrationConfiguration {
}
```

Đoạn này cần một `NotificationModuleConfiguration` thật và import `@Configuration`/`@Import`; configuration được import có thể khai báo `@Bean` listener cần thiết. Cách này rõ ràng hơn việc scan tràn lan tất cả package của thư viện thứ ba.

Nếu có nhiều `ApplicationContext` trong microservices, mỗi service phải đăng ký listener trong **context của chính nó**. Spring in-process events **không truyền event sang JVM khác**; muốn cross-service messaging phải dùng broker/HTTP/outbox và hợp đồng riêng.

## 6. Chẩn đoán khi bean có mặt nhưng listener method không được gọi

Lỗi scan chỉ là một loại nguyên nhân. Một bảng phân loại:

| Bằng chứng | Nguyên nhân nên kiểm tra trước |
| --- | --- |
| `getBeanNamesForType(OrderPlacedListener.class).length == 0` | Sai component scan package, thiếu stereotype, conditional/profile, module thiếu runtime dependency, sai context |
| Có bean nhưng không thấy method trong luồng xử lý | Annotation `@EventListener`, method signature, lifecycle, lazy bean, custom configuration |
| `@EventListener` thường chạy, `@TransactionalEventListener` không chạy | Transaction nguồn, phase và `fallbackExecution` |
| Listener nhận event A nhưng không nhận event B | Event type/generic, condition SpEL, publisher phát B qua context khác |
| Log listener đến rất muộn | `@Async`, executor queue hoặc custom multicaster |
| Publisher báo lỗi trước listener kỳ vọng | Listener khác ném exception, ErrorHandler, thứ tự gọi |
| Chỉ lỗi khi chạy JUnit | Test slice/context package khác, transaction test rollback, mock thay bean thật |
| Có một số listener gọi hai lần | Bean bị đăng ký trùng, context hierarchy, code publish event nhiều lần |

Không nên tạm thời đổi tất cả listeners thành `@EventListener` thường hoặc bật `fallbackExecution = true` để “cho chạy”. Những thay đổi đó có thể phá vỡ invariant: callback vốn chỉ được phép xử lý **sau commit** nay lại chạy trước commit hoặc ngoài transaction.

### Sử dụng Spring Boot Actuator để xem bean và condition

Trong ứng dụng Spring Boot có Actuator, các endpoint như `/actuator/beans` và `/actuator/conditions` có thể giúp xem bean được đăng ký và kết quả điều kiện cấu hình. **Endpoint có thể chưa được expose**; cần cấu hình management exposure theo chính sách bảo mật.

Đối với môi trường development, có thể sử dụng logging phù hợp để xem component scanning:

```properties
logging.level.org.springframework.context.annotation=TRACE
```

Đây là **cấu hình chẩn đoán**, có thể tạo rất nhiều log. Chỉ bật trong phạm vi cần thiết rồi tắt. Không nên mở actuator endpoints nhạy cảm công khai chỉ để debug một listener.

Dữ liệu chính cần đối chiếu là **bean names/types trong context chạy thực tế**, không phải số class được IDE tìm thấy trong project.

## 7. Viết test để không tái diễn lỗi scan

### 7.1. Smoke test cho bean registration

Trong một Spring Boot integration test:

```java
@SpringBootTest
class EventListenerRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void listenerIsRegistered() {
        assertEquals(1,
                context.getBeanNamesForType(
                        OrderPlacedListener.class).length);
    }
}
```

Đây là **mã khung minh họa**, cần imports, dependency JUnit 5/Spring Boot Test và project cụ thể. Nó xác nhận bean theo **type** có mặt trong Spring context của test, không tự chứng minh sự kiện đã đến method.

Cần chú ý: `@SpringBootTest` và một test slice như `@WebMvcTest` có **phạm vi nạp bean khác nhau**. Một listener không có trong context của test slice chưa chắc production cũng thiếu nó. Hãy chọn test context đại diện đúng cho wiring đang kiểm tra.

### 7.2. Test cả publication và listener side effect

Một smoke test mạnh hơn nên:

1. Khởi động context với cấu hình thực tế.
2. Assert có bean listener.
3. Gọi service tạo event đúng payload.
4. Assert listener tạo ra side effect mong đợi, ví dụ cập nhật fake sink/test counter.
5. Nếu listener async hoặc transaction-bound, đợi đúng điểm hoàn tất và xác minh transaction outcome tương ứng.

`@RecordApplicationEvents` của `spring-test` rất hữu ích để kiểm tra **event đã được publish**:

```java
@SpringBootTest
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    OrderService service;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        service.place("PO-42");

        assertEquals(1L,
                events.stream(OrderPlaced.class).count());
    }
}
```

Đây là **mã minh họa tích hợp**, không độc lập. Annotation và API thuộc `org.springframework.test.context.event`. Assertion này cho biết event phù hợp đã được **ghi nhận bởi test framework**, nhưng **không** khẳng định listener nghiệp vụ đã được scan. Vì thế, nên kiểm tra bean registration và side effect riêng.

### 7.3. Test Spring Framework thuần từ ví dụ mục 3

Không cần Spring Boot để kiểm tra bean registration:

```java
try (var context = new AnnotationConfigApplicationContext(
        ServiceAndListenerConfig.class)) {

    assertEquals(1,
            context.getBeanNamesForType(
                    OrderPlacedListener.class).length);
}
```

Đây là **mã khung JUnit minh họa**; ngoài các import trong ví dụ, cần JUnit `assertEquals`. Nó phù hợp để bảo vệ cấu hình scan của một thư viện dùng Spring Framework trực tiếp.

### 7.4. Kiểm tra sau commit

Nếu listener dùng `@TransactionalEventListener(AFTER_COMMIT)`, một test `@Transactional` với default rollback **không phù hợp để xác nhận callback AFTER_COMMIT đã chạy** chỉ bằng assertion trong test body. Có thể dùng `TestTransaction.flagForCommit()`/`TestTransaction.end()` nếu test-managed transaction hợp lệ, hoặc gọi service transactional trong test không bọc transaction ngoài để service commit thật.

Việc `repository.saveAndFlush(...)` hoàn tất không đồng nghĩa transaction đã commit. Hãy query trạng thái sau commit từ connection/transaction khác khi cần.

## 8. Những lỗi sửa sai dễ gây hậu quả mới

**Lỗi 1 — Thêm `@EventListener` cho method nhưng class không được đăng ký thành bean.**  
Phương thức không được Spring phát hiện. Sửa bằng stereotype trong đúng vùng scan hoặc đăng ký bean tường minh.

**Lỗi 2 — Thêm `@Component` nhưng class nằm ngoài base package.**  
Annotation không tự mở rộng `@ComponentScan`. Kiểm tra package của main class hoặc khai báo scan packages có chủ đích.

**Lỗi 3 — Cấu hình `@ComponentScan("com")` hoặc default package chỉ để “quét mọi thứ”.**  
Có thể kích hoạt quá nhiều bean, tạo xung đột tên/condition và làm startup chậm. Quét đúng root package ứng dụng hoặc các module đã biết.

**Lỗi 4 — Quên module runtime dependency.**  
IDE tìm thấy source qua multi-module project nhưng artifact thực tế không có class listener trên runtime classpath.

**Lỗi 5 — Đăng ký listener hai lần.**  
`@Component` đã được scan, lại có `@Bean` trả về instance khác hoặc `@Import` tạo definition trùng; cùng một event có thể làm hai listener chạy.

**Lỗi 6 — Nhầm conditional/profile với lỗi scan.**  
Class nằm trong vùng scan nhưng `@Profile` hoặc `@Conditional...` loại bean. Đọc condition evaluation report và active profiles trước khi thay packages.

**Lỗi 7 — Nhầm lazy initialization với event method registration.**  
Bean listener bị `@Lazy` có thể không được tạo để đăng ký `@EventListener` như mong muốn. Không nên lazy listener dùng để xử lý các event quan trọng nếu chưa hiểu rõ lifecycle.

**Lỗi 8 — Không tính đến event xảy ra trước context refresh.**  
Listener thường là bean nên không có mặt ở event startup sớm của Spring Boot. Cần early `ApplicationListener` đăng ký trước `run()` cho đúng nhóm event.

**Lỗi 9 — Bật `fallbackExecution=true` để “vá” listener transaction không chạy.**  
Nó thay đổi ngữ nghĩa: callback có thể chạy ngoài transaction dù yêu cầu ban đầu là sau commit.

**Lỗi 10 — Nhầm event không được publish với listener không được scan.**  
Dòng log “service bắt đầu” không chứng minh nhánh `publishEvent` đã chạy; kiểm tra call path và recorder/test phù hợp.

**Lỗi 11 — Chờ vài giây rồi kết luận listener async không tồn tại.**  
Tác vụ có thể đang queue hoặc lỗi trên executor. Kiểm tra completion, executor metrics, error handler, correlation ID.

**Lỗi 12 — Sửa một component scan khiến repository/entity ở module khác bị tác động.**  
Component scanning và các cơ chế scan của JPA/Spring Data không hoàn toàn đồng nhất. Luôn chạy integration tests kiểm tra các bean liên quan.

## 9. Quy trình xử lý một incident

Khi báo cáo lỗi “đã phát event mà handler không chạy”, thử theo thứ tự ít xâm lấn:

1. **Xác định lời gọi publish:** có thực sự gọi `ApplicationEventPublisher.publishEvent(...)` không? Payload type là gì?
2. **Xác định context:** producer và listener thuộc context nào; có hierarchy không?
3. **Xác minh bean registration:** lấy `getBeanNamesForType(...)` hoặc Actuator beans trong environment bị lỗi.
4. **Nếu bean không có:** kiểm tra package root, `@Component`/`@Bean`/`@Import`, module classpath, filters, profile/condition và bean lazy.
5. **Nếu bean có:** kiểm tra method `@EventListener`, signature, type, condition, lifecycle và runtime exceptions.
6. **Nếu là `@TransactionalEventListener`:** xác nhận transaction context và phase, không giả định publication đồng nghĩa commit.
7. **Nếu async:** kiểm tra executor, queue, completion và exception handler; bổ sung trace/event ID để nối publisher với listener.
8. **Chọn sửa đổi nhỏ nhất:** move main package, khai báo scan chính xác hoặc import cấu hình, thay vì mở scan toàn project.
9. **Thêm regression test:** assert bean presence **và** quan sát việc xử lý event, cộng thêm transaction outcome nếu liên quan.
10. **Kiểm tra trên runtime thật:** sau deploy, xác minh context và bean graph thực sự, không chỉ kết quả IDE hoặc unit test có mock.

Nếu dữ liệu nghiệp vụ bắt buộc được xử lý bền vững, nhớ rằng **Spring ApplicationEventPublisher không phải broker**. Việc sửa component scan giúp listener nhận event **trong tiến trình**, nhưng không bổ sung persistence, retry, outbox hoặc cơ chế giao nhận xuyên dịch vụ.

## 10. Câu hỏi tự đánh giá

**1. Có `@EventListener` trên method nhưng class không có `@Component`; Spring có tự đăng ký class không?**  
Không. `@EventListener` không phải stereotype cho class. Nếu không dùng component scanning, có thể đăng ký class qua `@Bean` hoặc `@Import`.

**2. Class có `@Component` mà vẫn không nhận event, nguyên nhân nào cần kiểm tra đầu tiên?**  
Base package scan của context, active profiles/conditions và việc bean thực sự có trong `ApplicationContext`. Không suy đoán từ file source.

**3. `StoreApplication` ở `com.acme.app`, listener ở `com.acme.listeners`. Mặc định Spring Boot có quét listener không?**  
Không. Đây là package ngang cấp, không nằm dưới `com.acme.app`. Cần chuyển main class lên root package chung, mở scan có chủ đích hoặc đăng ký bean tường minh.

**4. `applicationContext.getBeanNamesForType(...)` trả về 1 nhưng listener không chạy; còn kết luận thiếu scan được không?**  
Không nên. Bean đã tồn tại. Kiểm tra event type, condition, lifecycle, transaction phase, async hoặc listener khác ném exception.

**5. `@TransactionalEventListener(AFTER_COMMIT)` không chạy khi publish ngoài transaction. Có chắc listener không được scan không?**  
Không. Vì `fallbackExecution` mặc định false, callback bị bỏ qua khi không có transaction phù hợp.

**6. Spring Boot event `ApplicationStartingEvent` có thể được nhận chắc chắn bởi bean `@Component` thông thường không?**  
Không. Event này phát rất sớm trước khi các bean ứng dụng được tạo; phải đăng ký early listener theo cơ chế Boot thích hợp.

**7. Vì sao không nên dùng test chỉ assert `@RecordApplicationEvents` có event để kết luận listener đã được scan?**  
Recorder kiểm tra **publication**; listener nghiệp vụ có thể hoàn toàn vắng mặt mà event vẫn được publish và ghi nhận.

**8. Nếu listener nằm trong dependency JAR nhưng vẫn không được scan, điều nào khác cần kiểm tra?**  
Bean phải nằm trong base scan phù hợp và đáp ứng stereotype/filter/condition. JAR có trên classpath là điều kiện cần nhưng không đủ.

## 11. Tài liệu chính thức

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html)
- [Spring Framework 6.2 — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2.9 Javadoc — EventListenerMethodProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [Spring Boot 3.3 — Structuring Your Code / Locating the Main Application Class](https://docs.spring.io/spring-boot/3.3/reference/using/structuring-your-code.html)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

