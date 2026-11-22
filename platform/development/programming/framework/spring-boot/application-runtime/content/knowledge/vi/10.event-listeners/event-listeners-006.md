# Điều phối listener bằng Ordered và @Order trong Spring Boot

## 1. Vì sao cần điều phối thứ tự listener?

Một sự kiện trong Spring có thể được nhiều thành phần quan tâm: ghi audit, cập nhật chỉ số, ghi log chẩn đoán, làm nóng cache, gửi notification hoặc kiểm tra một điều kiện sau startup. Khi `ApplicationEventPublisher.publishEvent(...)` công bố sự kiện, Spring tìm **những listener phù hợp với loại sự kiện** rồi phân phối sự kiện tới chúng.

Nếu nhiều listener phản ứng với cùng một event, đôi khi ta muốn listener A được gọi trước listener B. Spring hỗ trợ hai cách thông dụng:

- Triển khai interface **`org.springframework.core.Ordered`** trên một `ApplicationListener`, trả về thứ tự động qua `getOrder()`.
- Đặt annotation **`org.springframework.core.annotation.Order`**, đặc biệt là **trên phương thức mang `@EventListener`**; hoặc trên class listener khi muốn khai báo thứ tự bằng metadata.

Cả hai mô tả **độ ưu tiên trong danh sách callback phù hợp** chứ không bắt hệ thống phải tạo bean theo thứ tự đó, không thay đổi thứ tự các loại sự kiện khác nhau và **không bảo đảm tác vụ bất đồng bộ hoàn thành theo thứ tự**.

Nội dung tập trung vào Spring Framework **6.1.x**, Spring Boot **3.3.x** và Java **17+**. Khi có custom `ApplicationEventMulticaster`, `@Async`, nhiều `ApplicationContext` hoặc transactional listener, cần đọc thêm các giới hạn ở cuối bài.

**Nguyên tắc nhớ nhanh: giá trị `order` càng nhỏ thì callback càng được ưu tiên gọi sớm.**

## 2. Listener trong Spring thực chất là gì?

Có hai hình thức rất phổ biến.

### 2.1. ApplicationListener dạng interface

```java
@Component
class AuditListener implements ApplicationListener<OrderCreatedEvent> {
    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Xử lý khi có OrderCreatedEvent.
    }
}
```

Đây là **đoạn minh họa**, chưa phải file Java độc lập: `OrderCreatedEvent` cần được định nghĩa là một `ApplicationEvent`, đồng thời cần import `ApplicationListener` và `@Component`. Khi bean listener đã được đăng ký, event multicaster có thể gọi `onApplicationEvent(...)`.

Với class tự tạo qua `new`, để tham gia vào cơ chế dispatch của Boot từ giai đoạn sớm, phải đăng ký listener từ bootstrap, ví dụ `SpringApplication.addListeners(...)`. Chỉ tồn tại một object Java chưa đủ để nó tự trở thành listener.

### 2.2. Phương thức @EventListener trong bean Spring

```java
@Component
class NotificationListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Xử lý khi có OrderCreatedEvent.
    }
}
```

Đây cũng là đoạn minh họa. Spring xử lý annotation `@EventListener` trên bean và đăng ký adapter listener cho phương thức. Lợi thế: một bean có thể có nhiều method cho những loại event khác nhau.

**Phân biệt loại listener trước khi chọn `@Order`:**

- Với `ApplicationListener` triển khai trực tiếp, dùng `Ordered` hoặc khai báo `@Order` ở class theo cơ chế annotation-aware.
- Với một method mang `@EventListener`, **đặt `@Order` trực tiếp lên method đó** là cách được tài liệu Spring hướng dẫn. Đây là vị trí rõ nghĩa và được adapter của `@EventListener` hỗ trợ.
- Không nên chỉ đặt `@Order` ở class chứa các method `@EventListener` rồi suy diễn mỗi method chắc chắn nhận cùng thứ tự. Khi cần điều phối method listener, gắn annotation ở từng method.

## 3. Quy tắc sắp xếp: số nhỏ chạy trước

Interface `Ordered` định nghĩa:

```java
public interface Ordered {
    int HIGHEST_PRECEDENCE = Integer.MIN_VALUE;
    int LOWEST_PRECEDENCE = Integer.MAX_VALUE;
    int getOrder();
}
```

Đoạn trên tóm tắt API để học; dự án thực dùng interface Spring có sẵn. `getOrder()` trả về một số nguyên, nhỏ hơn nghĩa là độ ưu tiên cao hơn.

| Giá trị order | Độ ưu tiên tương đối | Khi nên dùng |
| --- | --- | --- |
| `Ordered.HIGHEST_PRECEDENCE`, tương đương `Integer.MIN_VALUE` | Cao nhất theo hệ thống so sánh order | Rất hiếm; hãy cẩn thận vì framework cũng có listener mức cao |
| `-100` | Trước `0`, `10`, `100` | Callback cần chạy khá sớm |
| `0` | Trước `10` | Mốc ưu tiên thông dụng |
| `10` | Trước `20` | Bước 1 trong nhóm callback cùng loại |
| `20` | Sau `10`, trước `30` | Bước 2 |
| `Ordered.LOWEST_PRECEDENCE`, tương đương `Integer.MAX_VALUE` | Thấp nhất theo giá trị order | Listener không cần ưu tiên |

Spring sử dụng comparator phù hợp để sắp danh sách listener. Trong cơ chế event multicasting thông thường, những listener phù hợp được sắp xếp theo order trước khi dispatch.

### 3.1. @Order(value) là metadata, Ordered#getOrder() là contract

Hai cách diễn đạt một giá trị tương đương:

```java
// Cách A: class có phương thức getOrder() trả về 10.
@Component
class FirstListener
        implements ApplicationListener<OrderCreatedEvent>, Ordered {
    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // ...
    }
}
```

```java
// Cách B: method annotation @EventListener với @Order(10).
@Component
class AnotherListener {
    @EventListener
    @Order(10)
    public void onOrderCreated(OrderCreatedEvent event) {
        // ...
    }
}
```

Đây là các đoạn minh họa, **không phải hai file độc lập**, cần định nghĩa `OrderCreatedEvent` và import tương ứng. Trong phần thí nghiệm bên dưới sẽ có mã hoàn chỉnh chạy được.

**Điểm khác:** `Ordered` có thể trả giá trị do constructor/cấu hình tính ra ở runtime, trong khi `@Order(10)` là metadata hằng số đặt trên code. Khi một object triển khai `Ordered` và đồng thời mang `@Order`, bộ so sánh thông thường ưu tiên giá trị `Ordered#getOrder()` của chính object đó. Tránh khai báo hai số khác nhau cho cùng một listener vì tạo hiểu nhầm khi review.

### 3.2. Cùng số order thì sao?

Nếu hai listener có cùng order hoặc không có cấu hình order rõ ràng, **không được dùng thứ tự tình cờ quan sát được làm contract nghiệp vụ**. Thứ tự thực tế có thể bị ảnh hưởng bởi đăng ký bean, classpath, comparator, factory hoặc thay đổi framework.

Ví dụ hai listener đều `@Order(10)` thì không thể suy ra cái nào phải gọi trước. Nếu B thực sự cần kết quả của A, gán thứ tự khác nhau **và đánh giá xem coupling qua listener có hợp lý không**.

### 3.3. Không cấu hình order thì mặc định là gì?

Với các listener theo Spring order semantics, không có thông tin thứ tự rõ ràng thường tương đương mức thấp `Ordered.LOWEST_PRECEDENCE` trong những cơ chế so sánh chuẩn. **Không nên phụ thuộc vào vị trí của chúng trong nhóm cùng mức**, kể cả khi một lần chạy cho ra thứ tự ổn định.

### 3.4. PriorityOrdered có thể ảnh hưởng comparator

Spring còn có interface `PriorityOrdered`, thuộc họ `Ordered`. Nó là cơ chế ưu tiên chuyên biệt ở những chỗ comparator có hỗ trợ, nên không nên trộn tùy tiện `PriorityOrdered`, `Ordered` và `@Order` rồi suy ra thứ tự chỉ từ số nguyên. Khi yêu cầu thông thường là thứ tự listener nghiệp vụ, hãy bắt đầu bằng các giá trị `Ordered`/`@Order` minh bạch và tránh tranh chấp mức cực cao của framework.

## 4. Chọn vị trí khai báo order đúng

| Kiểu xử lý | Cách khai báo ưu tiên phù hợp | Ghi chú |
| --- | --- | --- |
| Bean triển khai `ApplicationListener<MyEvent>` | `implements Ordered` và `getOrder()` | Kiểm soát runtime order rõ ràng |
| Bean triển khai `ApplicationListener<MyEvent>` | `@Order(20)` ở class | Thích hợp thứ tự cố định; kiểm tra annotation comparator của cơ chế đang dùng |
| Bean chứa `@EventListener` method | `@Order(20)` đặt **ở method** | Cách tài liệu Spring hướng dẫn cho annotated event listener |
| Một bean có hai method `@EventListener` cùng event | Mỗi method có thể có `@Order` riêng | Điều phối ở cấp callback, không mặc định toàn bean cùng order |
| Listener đăng ký qua `SpringApplication.addListeners(...)` | Instance triển khai `Ordered` hoặc class có metadata `@Order` | Có thể nghe event startup trước lúc context tồn tại |
| `@TransactionalEventListener` | `@Order` cùng với phase transaction thích hợp | Order không thay thế phase `BEFORE_COMMIT`/`AFTER_COMMIT` |
| Listener `@Async` | Có thể khai báo `@Order` nhưng không dùng để chờ hoàn thành | Thứ tự bắt đầu/scheduling không phải thứ tự kết thúc |
| `ApplicationRunner` / `CommandLineRunner` | `@Order`/`Ordered` áp dụng cho **runner**, không phải event listener | Cùng họ ordering nhưng khác contract |

**Lưu ý:** Không dùng `@Order` để yêu cầu singleton X phải được khởi tạo trước singleton Y. Thứ tự khởi tạo bean chịu ảnh hưởng dependency graph, `@DependsOn` và lifecycle container. `@Order` ở đây dùng để sắp **callback/listener**.

## 5. Ví dụ chạy được: Ordered và @EventListener @Order cùng nhận một event

Mục tiêu: trong **một ứng dụng Spring Boot 3.3.x**, có hai listener cho event startup sớm và ba callback cho một custom event sau refresh. Ta đo được:

1. Hai listener `ApplicationStartingEvent` được đăng ký từ `SpringApplication` và điều phối bằng `Ordered`.
2. Một method `@EventListener @Order(10)` được gọi trước listener interface `Ordered(20)`.
3. Method `@EventListener @Order(30)` được gọi cuối cùng.
4. Với multicaster đồng bộ mặc định, `publishEvent(...)` trở về **sau khi** ba callback đồng bộ chạy xong.

### 5.1. Dự án Gradle Java 17+

Tạo dự án Java 17 từ Spring Initializr hoặc từ Gradle, có Gradle Wrapper. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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

`settings.gradle`:

```groovy
rootProject.name = 'listener-order-lab'
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Dự án dùng `spring-boot-starter` **không kèm web server**; event dispatch hoạt động bình thường trong non-web `ApplicationContext`. Tắt banner và log startup INFO để dễ đọc stdout do code tạo ra.

### 5.2. Một file Java hoàn chỉnh

Tạo đúng file `src/main/java/com/example/listener/ListenerOrderApplication.java`:

```java
package com.example.listener;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ListenerOrderApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ListenerOrderApplication.class);

        // Early events xảy ra trước khi context có bean.
        application.addListeners(
                new EarlyListener(-10, "01 early: order=-10"),
                new EarlyListener(10, "02 early: order=10")
        );

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // SpringApplication.run đã thực thi runner và các listener.
        }
    }

    // Một custom event với type rõ ràng.
    public static final class CheckEvent extends ApplicationEvent {
        public CheckEvent(Object source) {
            super(source);
        }
    }

    // Đăng ký trực tiếp từ bootstrap; không cần là Spring bean.
    static final class EarlyListener
            implements ApplicationListener<ApplicationStartingEvent>, Ordered {

        private final int order;
        private final String label;

        EarlyListener(int order, String label) {
            this.order = order;
            this.label = label;
        }

        @Override
        public int getOrder() {
            return order;
        }

        @Override
        public void onApplicationEvent(ApplicationStartingEvent event) {
            System.out.println(label);
        }
    }

    // Bean listener: triển khai interface ApplicationListener + Ordered.
    @Component
    public static class ClassBasedListener
            implements ApplicationListener<CheckEvent>, Ordered {

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void onApplicationEvent(CheckEvent event) {
            System.out.println("05 event: interface Ordered(20)");
        }
    }

    // Bean listener: hai method cùng event, order độc lập.
    @Component
    public static class MethodBasedListener {

        @EventListener
        @Order(10)
        public void first(CheckEvent event) {
            System.out.println("04 event: method @Order(10)");
        }

        @EventListener
        @Order(30)
        public void last(CheckEvent event) {
            System.out.println("06 event: method @Order(30)");
        }
    }

    @Bean
    ApplicationRunner publishCheckEvent(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("03 publish: before");
            publisher.publishEvent(new CheckEvent(this));
            System.out.println("07 publish: after");
        };
    }
}
```

**Vì sao đây là chương trình Spring Boot hợp lệ?**

- `@SpringBootApplication` kích hoạt auto-configuration và component scan cho package `com.example.listener`. Hai nested class `public static` có `@Component` được tạo thành các bean listener khi context refresh.
- `EarlyListener` được đăng ký trực tiếp **trước `run(...)`**, nên có thể nhận `ApplicationStartingEvent` — một sự kiện phát khi bean trong context chưa tồn tại.
- `CheckEvent extends ApplicationEvent` bảo đảm `ApplicationListener<CheckEvent>` là generic type hợp lệ. Event có source là chính instance cấu hình ứng dụng (`this`) và được phát trong runner.
- `ClassBasedListener` triển khai `Ordered` và trả về `20`; Spring dùng giá trị đó để xếp listener phù hợp.
- Hai method `@EventListener` nằm trong cùng bean nhưng mang `@Order(10)` và `@Order(30)` khác nhau. Spring đăng ký chúng thành hai callback độc lập.
- `ApplicationRunner` chạy sau context refresh, khi bean listeners đã tồn tại, và chủ động phát sự kiện `CheckEvent`.
- `try` đóng context sau khi `run` hoàn tất. Ví dụ không cần embedded server hay tài nguyên ngoài.

### 5.3. Chạy ứng dụng

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trên macOS hoặc Linux:

```bash
./gradlew bootRun
```

Nếu dùng Gradle Wrapper và project đã resolve dependencies, các dòng **do chương trình Java tự in** khi không có listener/custom multicaster khác là:

```text
01 early: order=-10
02 early: order=10
03 publish: before
04 event: method @Order(10)
05 event: interface Ordered(20)
06 event: method @Order(30)
07 publish: after
```

Gradle vẫn có thể in thông báo task/build; ta chỉ đối chiếu những dòng bắt đầu bằng số của ứng dụng. Hai listener đầu cùng nhận `ApplicationStartingEvent` và được sắp `-10` trước `10`. Ba callback giữa cùng nhận `CheckEvent`, được sắp `10`, `20`, `30`. Vì dispatch mặc định đồng bộ, dòng `07` xuất hiện sau khi cả ba callback trả về.

Đây là hai **lần phân phối event độc lập**. Không so sánh trực tiếp `early @Order(10)` với `custom event @Order(10)` để nói callback của hai event phải chạy cùng nhau; thứ tự giữa các event do chuỗi bootstrap quyết định.

### 5.4. Tự thay đổi và dự đoán stdout

**Thí nghiệm A — thay `getOrder()`:** Chuyển `ClassBasedListener.getOrder()` từ `20` sang `5`. Khi phát `CheckEvent`, callback interface sẽ được gọi trước method `@Order(10)` và `@Order(30)`. Nội dung dòng in vẫn có chữ `Ordered(20)` do ta hard-code trong ví dụ; để tránh hiểu lầm, **đổi luôn nhãn log thành `Ordered(5)`** khi thực hành.

**Thí nghiệm B — hoán đổi annotation:** Đổi `@Order(10)` của method `first` thành `@Order(40)`. Khi đó callback `Ordered(20)` và `@Order(30)` chạy trước method mang số `40`. Một lần nữa, sửa nhãn log để phản ánh giá trị mới.

**Thí nghiệm C — bỏ @Order:** Bỏ cả hai annotation `@Order` ở method listener. Không nên viết test phụ thuộc vào thứ tự hai method đó. Chúng đều có order mặc định không ưu tiên theo contract rõ ràng.

**Thí nghiệm D — lỗi callback:** Trong method `first`, ném `IllegalStateException`. Với multicaster đồng bộ mặc định **không có error handler nuốt exception**, lỗi được truyền ngược về publisher; các listener nằm sau có thể không được gọi, runner có thể thất bại, và ứng dụng Boot có thể kết thúc startup bằng lỗi. Vì vậy order không thay thế xử lý lỗi.

**Thí nghiệm E — đổi sang @Async:** Nếu method listener chạy bất đồng bộ, vị trí trong danh sách dispatch không còn bảo đảm thời điểm công việc kết thúc. Đừng viết assertion về thứ tự completion như trong stdout đồng bộ.

## 6. @Order trên class và @Order trên method: tránh nhầm cấp tác dụng

Một class `ApplicationListener` có thể khai báo order ở cấp class:

```java
@Component
@Order(25)
class InventoryListener implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // xử lý...
    }
}
```

Đây là **phương án minh họa riêng**, không thêm nguyên vào dự án runnable ở mục 5 nếu chưa định nghĩa `OrderCreatedEvent`. Khi framework sử dụng annotation-aware ordering trên listener objects, metadata ở class đóng vai trò khai báo mức ưu tiên cố định.

Ngược lại, class sau có **hai callback cùng event**:

```java
@Component
class EventMethods {

    @EventListener
    @Order(10)
    void record(OrderCreatedEvent event) {
        // callback 1
    }

    @EventListener
    @Order(50)
    void notifyClient(OrderCreatedEvent event) {
        // callback 2
    }
}
```

Ở đây hai method là hai listener adapters với order khác nhau, dù cùng nằm trong `EventMethods`. Đặt `@Order` lên method là cách diễn đạt mục tiêu rõ nhất; không nên cho rằng class order dùng để áp cùng thứ tự cho tất cả method nếu adapter đang đọc metadata của từng method.

**Khi nào chọn cách nào?**

- Cần một class listener có logic phức tạp và priority runtime: `ApplicationListener + Ordered`.
- Cần order cố định trên toàn class listener interface: `@Order` ở class.
- Cần các callback ngắn và có thể điều phối riêng ngay trong cùng một bean: `@EventListener + @Order` ở từng method.
- Muốn một bean chỉ đăng ký từ giai đoạn Boot bootstrap sớm: `SpringApplication.addListeners`; có thể chọn `Ordered` trên listener instance.

## 7. Sự kiện Boot khởi động sớm và khả năng đăng ký listener

Một số Spring Boot events xảy ra **trước khi `ApplicationContext` được tạo**:

- `ApplicationStartingEvent`: rất sớm trong `SpringApplication.run(...)`.
- `ApplicationEnvironmentPreparedEvent`: đã có `Environment` nhưng context chưa tạo.
- `ApplicationContextInitializedEvent`: context đã tạo, initializer đã chạy nhưng primary definitions chưa nạp.
- `ApplicationPreparedEvent`: definitions chính đã được nạp nhưng context chưa refresh.

Với các sự kiện này, callback chỉ được phát hiện khi nó **đã được đăng ký từ bootstrap**, chẳng hạn:

```java
SpringApplication app = new SpringApplication(MyApp.class);
app.addListeners(new EarlyApplicationListener());
app.run(args);
```

Đây là **đoạn minh họa**, cần class `EarlyApplicationListener` tự định nghĩa. Các lựa chọn khác là `SpringApplicationBuilder.listeners(...)` hoặc đăng ký `org.springframework.context.ApplicationListener` trong `META-INF/spring.factories` trên runtime classpath.

Ví dụ cấu hình `spring.factories`:

```properties
org.springframework.context.ApplicationListener=\
com.example.boot.EarlyApplicationListener
```

Phải có class thật và constructor phù hợp trước khi dùng. Không thêm file này vào project thí nghiệm mục 5 nếu bạn không định nghĩa đúng class.

**Sai lầm phổ biến:** Một bean chỉ có

```java
@EventListener
@Order(-100)
void onStarting(ApplicationStartingEvent event) {
    // ...
}
```

sẽ **không tự bắt được sự kiện rất sớm** `ApplicationStartingEvent`, dù order âm “cao”. Khi event được phát, bean method listener chưa được đăng ký. **Order chỉ áp dụng cho listener đã tồn tại và đủ điều kiện nhận event**, không đưa listener trở ngược thời gian.

Các event muộn hơn, như `ApplicationStartedEvent` hay `ApplicationReadyEvent`, thường đến khi context đã refresh nên bean `@EventListener` có thể nhận chúng. Chỉ nên dùng thông tin về **loại event** và **đúng mốc đăng ký**, không suy rằng event nào chứa chữ “start” cũng xảy ra trước context.

## 8. Điều phối theo một event, không sắp lại toàn bộ vòng đời Boot

Giả sử có hai listener:

- `@EventListener @Order(-100)` nghe `ApplicationReadyEvent`.
- `@EventListener @Order(100)` nghe `ApplicationStartedEvent`.

Mặc dù `-100` nhỏ hơn `100`, event `ApplicationReadyEvent` vẫn diễn ra **sau** `ApplicationStartedEvent` trong chuỗi khởi động thông thường. `@Order` **không vượt qua** thứ tự các sự kiện do `SpringApplication` phát.

Một timeline rút gọn:

```text
Context refresh
    |
    +--> ApplicationStartedEvent
    |      listeners phù hợp được sắp theo order cho event này
    |
    +--> ApplicationRunner / CommandLineRunner
    |
    +--> ApplicationReadyEvent
           listeners phù hợp được sắp theo order cho event này
```

Tương tự, khi listener A đang xử lý event X và tự gọi `publishEvent(Y)` đồng bộ, listener của Y có thể chạy **lồng bên trong callback A** trước khi những listener còn lại của X được gọi. Đây là nested event publication chứ không phải comparator bị lỗi.

Không nên dùng `@Order` để diễn tả luồng nghiệp vụ dạng transaction A → database write B → notification C một cách ngầm định khi các bước cần trạng thái kết quả của nhau. Khi nghiệp vụ thực sự phụ thuộc lẫn nhau, dùng service orchestration, workflow hoặc event có hợp đồng rõ ràng, không chỉ tăng dần số order.

## 9. Đồng bộ và bất đồng bộ: thứ tự gọi khác thứ tự hoàn tất

### 9.1. Chế độ mặc định là đồng bộ

`SimpleApplicationEventMulticaster` trong Spring Framework thường gọi các listener phù hợp **ngay trên thread phát event**, theo danh sách sắp xếp. Hình dung:

```text
publisher.publishEvent(event)
     |
     +--> listener @Order(10): chạy và return
     +--> listener Ordered(20): chạy và return
     +--> listener @Order(30): chạy và return
     |
     +--> publishEvent return
```

Vì vậy một listener đồng bộ bị block có thể kéo dài `publishEvent(...)`, giữ thread request hoặc khiến startup chậm nếu event được phát trong chuỗi bootstrap. Lỗi chưa xử lý của listener đồng bộ có thể truyền ngược về publisher và ảnh hưởng các listener tiếp theo.

**Lời khuyên:** không đặt I/O dài hoặc chờ vô hạn trong early startup listener. Nếu cần tác vụ sau refresh để chuẩn bị trước readiness, cân nhắc `ApplicationRunner`/`CommandLineRunner`. Nếu cần công việc nền, thiết kế executor, retry và monitoring rõ ràng.

### 9.2. @Async @EventListener

Có thể dùng `@EnableAsync` và `@Async` trên method listener, ví dụ:

```java
@Async
@EventListener
@Order(10)
public void sendNotification(OrderCreatedEvent event) {
    // Thực hiện trên executor đã cấu hình.
}
```

Đây là **đoạn minh họa**, không độc lập và chỉ chạy bất đồng bộ khi cơ chế async Spring được bật/cấu hình thích hợp. Cần import `org.springframework.scheduling.annotation.Async`, `org.springframework.context.event.EventListener` và `Order`.

Dù method được sắp trong danh sách listener theo order, công việc thực tế được schedule/đưa qua proxy async. Nếu listener `@Order(10)` mất 2 giây còn `@Order(20)` chỉ mất 5 ms, listener 20 có thể **hoàn thành trước** listener 10. `@Order` không tạo cơ chế `join` hoặc `await`.

Với async method listener, exception không truyền ngược về publisher theo cùng cách như listener đồng bộ; cần kiểm tra `AsyncUncaughtExceptionHandler` hoặc kết quả async thích hợp. Những method async listener cũng có hạn chế khi trả về event để phát tiếp bằng cơ chế return-value của `@EventListener`.

### 9.3. Custom ApplicationEventMulticaster có TaskExecutor

Một số ứng dụng cấu hình `applicationEventMulticaster` và đặt `TaskExecutor` để phân phối listener trên thread khác. Khi đó comparator vẫn có thể quyết định **thứ tự duyệt/schedule**, nhưng task trên nhiều thread hoàn thành không nhất thiết cùng thứ tự. Hệ thống còn có các listener tuyên bố không hỗ trợ async execution; chúng phải được gọi trên thread publisher theo API tương ứng, ví dụ một số transactional listener.

Nếu thiết kế yêu cầu thứ tự **hoàn thành** nghiêm ngặt, dùng xử lý đồng bộ có kiểm soát, một chuỗi công việc rõ ràng, hoặc executor một luồng với ràng buộc thích hợp. Không coi `@Order` một mình là đủ để bảo đảm thứ tự giữa các thread.

### 9.4. Lỗi listener làm thay đổi thứ quan sát được

Với multicaster đồng bộ mặc định **không có `ErrorHandler` bắt và xử lý exception**, một listener đầu tiên ném lỗi có thể chặn quá trình multicast và làm các listener phía sau không được gọi. Nếu có custom error handler hoặc executor, hành vi lỗi có thể thay đổi.

Khi debug “listener order không đúng”, hãy kiểm tra có listener nào ném exception/đang chạy async hay không trước khi kết luận Spring sắp sai.

## 10. TransactionalEventListener và thứ tự theo transaction

`@TransactionalEventListener` khác `@EventListener` thường ở chỗ callback được gắn với một **transaction phase**, ví dụ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void onPaymentCommitted(PaymentEvent event) {
    // Chạy sau khi transaction commit thành công.
}
```

Đây là **đoạn minh họa**, cần import `TransactionalEventListener`, `TransactionPhase`, `Order` và định nghĩa `PaymentEvent`. Trong các ứng dụng giao dịch, listener kiểu này thường được hoãn đến phase đã chọn thay vì thực thi ngay khi event được phát.

**Không được dùng số order để đảo lộn ranh giới transaction.** Listener `AFTER_COMMIT @Order(-10)` không thể chạy trước sự kiện `BEFORE_COMMIT` chỉ vì số âm. Khi cần điều phối nhiều transactional listener trong cùng phase, `@Order` là một tham số; nhưng điều kiện có transaction, phase, thread và thứ tự callback còn phụ thuộc cơ chế transaction synchronization.

Nếu event phát ngoài transaction, `@TransactionalEventListener` thường không chạy trừ khi cho phép fallback theo cấu hình của annotation. Đó là lý do listener “mất” callback không hẳn là lỗi ordering.

## 11. Listener trong context hierarchy có thể nhận event nhiều lần

Spring Boot có thể chạy context cha/con. Event được published trong child context cũng có thể được gửi lên ancestor contexts. Kết quả: listener quan tâm một loại event **có thể được gọi nhiều lần** đối với những event từ nhiều context.

`@Order` chỉ sắp các listener trong tập dispatch đang xét; nó không bảo đảm **một thứ tự toàn cục giữa mọi context** và không có chức năng chống phát event lặp. Khi có hierarchy:

- Xác định event được published từ context nào.
- Kiểm tra listener đang nằm ở context nào.
- Với SpringApplication events mang context, so sánh event context và injected local context nếu cần lọc.
- Dùng correlation ID trong log để phân biệt các lần dispatch.

Đừng nhầm việc cùng một callback xuất hiện hai lần với việc comparator chọn hai vị trí.

## 12. Các sai lầm phổ biến và cách xử lý

| Triệu chứng/nhận định | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| “`@Order(100)` chạy trước `@Order(10)`” | Hai callback thuộc hai event khác nhau hoặc có async | So event type và thread; chỉ so order trong cùng một dispatch |
| “Listener nào đăng ký trước luôn chạy trước” | Spring sắp theo order, không đơn thuần theo thứ tự khai báo | Đặt `Ordered`/`@Order` rõ ràng |
| “`@Order` làm bean được khởi tạo trước” | Nhầm callback sorting với bean lifecycle | Xem `@DependsOn` và dependency graph |
| “`@Order(-100)` giúp `@EventListener` nhận `ApplicationStartingEvent`” | Listener bean chưa được tạo/đăng ký ở mốc sớm | Đăng ký bằng `SpringApplication.addListeners` hoặc `spring.factories` |
| “`@Order` trên class điều khiển mọi method @EventListener” | Adapter của method listener đọc metadata ở method | Đặt `@Order` ở từng method cần điều phối |
| “Cùng số order vẫn phải cố định thứ tự” | Thứ tự tie không phải contract đáng dựa vào | Gán số khác nhau hoặc bỏ phụ thuộc |
| “`Ordered#getOrder()` và `@Order` trên cùng instance luôn cộng dồn” | Chúng cùng diễn tả giá trị order | Chọn một nguồn order rõ ràng |
| “`@Order(10)` async chắc chắn xong trước `@Order(20)`” | Completion phụ thuộc executor và task duration | Dùng completion coordination riêng nếu cần |
| “Listener 20 không chạy nên order sai” | Listener 10 ném exception, filter/condition không đạt hoặc event type không khớp | Xem exception, `@EventListener(condition=...)`, event payload |
| “Order điều khiển luôn transaction phase” | Phase có lifecycle riêng | Dùng `@TransactionalEventListener` và phase đúng |
| “Một event được nghe hai lần là do `@Order`” | Context hierarchy hoặc đăng ký listener trùng | Kiểm tra context/event identity và registration |
| “Callback luôn nằm cùng thread publisher” | Custom multicaster hoặc `@Async` | Kiểm tra executor, thread name, error propagation |

### 12.1. Checklist debug listener order

1. Ghi rõ **tên loại event** và context phát event. Các event khác nhau phải được phân tích riêng.
2. Liệt kê **những listener phù hợp**: `ApplicationListener<T>`, method `@EventListener`, có condition hay không, được đăng ký trước thời điểm event hay chưa.
3. Ghi **order value**: `Ordered#getOrder()` hoặc `@Order` trên method/class. Phân biệt hai listener cùng order.
4. Ghi **thread name** và xem có `@Async` hoặc custom multicaster executor.
5. Kiểm tra exception/`ErrorHandler`; một callback lỗi có thể chặn những callback sau.
6. Nếu event liên quan DB transaction, xem `TransactionPhase` và transaction thực tế.
7. Nếu có parent/child contexts, kiểm tra lặp event và context của listener.
8. Viết test với event riêng và các order khác nhau, tránh phụ thuộc vào thứ tự khai báo bean.

Các log chẩn đoán nên chứa timestamp, event class, callback, order, thread và correlation ID **không nhạy cảm**. Không ghi token, dữ liệu khách hàng hoặc payload bí mật vào log chỉ để theo dõi sorting.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `@EventListener @Order(5)` và một `ApplicationListener` triển khai `Ordered#getOrder() == 20` cùng nghe một event đồng bộ. Ai được gọi trước?

**Đáp:** Method `@Order(5)` thường được gọi trước vì 5 nhỏ hơn 20, với dispatcher/ordering chuẩn.

**Câu 2.** Hai method cùng có `@EventListener @Order(10)` thì ai chạy trước?

**Đáp:** Không nên dựa vào thứ tự giữa các method có cùng order; cần đặt order khác nhau nếu bắt buộc.

**Câu 3.** Đặt `@Order(-100)` trên bean nghe `ApplicationStartingEvent` đã đủ chưa?

**Đáp:** Chưa. `ApplicationStartingEvent` phát rất sớm; phải đăng ký listener từ bootstrap chứ không chờ component scanning.

**Câu 4.** `@Order(10)` có làm `ApplicationReadyEvent` xảy ra trước `ApplicationStartedEvent` không?

**Đáp:** Không. Order của listener không thay đổi thứ tự các loại event trong vòng đời Spring Boot.

**Câu 5.** Vì sao `@Async @EventListener @Order(10)` có thể in log sau `@Order(20)`?

**Đáp:** Sắp thứ tự listener không đảm bảo thứ tự **hoàn thành** của những task bất đồng bộ.

**Câu 6.** Có nên dùng `@Order` để ép singleton A tạo trước singleton B?

**Đáp:** Không. Dùng dependency injection và `@DependsOn` khi cần điều khiển ràng buộc lifecycle hợp lệ.

**Câu 7.** Runner trong ví dụ in `07 publish: after` trước hay sau ba callback custom event?

**Đáp:** Sau cả ba callback trong cấu hình mặc định vì multicaster đồng bộ và không có callback ném exception.

**Câu 8.** Listener `@TransactionalEventListener(AFTER_COMMIT)` có thể được điều phối để chạy trước commit nhờ order âm không?

**Đáp:** Không. Transaction phase là ranh giới về thời điểm, order chỉ có ý nghĩa trong cơ chế callback phù hợp với phase đó.

## 14. Tóm tắt và tài liệu tham khảo

- **`Ordered#getOrder()`** là cách lập trình giá trị ưu tiên của một listener class; **`@Order`** khai báo giá trị cố định, đặc biệt dễ dùng ngay trên method `@EventListener`.
- **Số nhỏ hơn được ưu tiên trước**, nhưng **chỉ so sánh những listener cùng tham gia dispatch của một event**.
- **Mặc định đồng bộ:** callback thường được gọi tuần tự; `publishEvent` trở về sau các callback thành công. **Async:** `@Order` không bảo đảm thứ tự hoàn thành.
- **Bean listener không nhận được event trước khi nó được đăng ký.** Startup early events cần `SpringApplication.addListeners(...)`/`spring.factories`.
- **Thứ tự listener ≠ thứ tự bean initialization ≠ thứ tự phát event ≠ transaction phase.** Phân biệt chúng trước khi dùng `@Order` làm công cụ điều phối.

Nguồn chính thức phù hợp với Spring Boot 3.x / Spring Framework 6.1:

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), cách đăng ký early listener và chuỗi startup events.
- [Spring Framework 6.1 — Ordered API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html), ý nghĩa giá trị order và các hằng số priority.
- [Spring Framework 6.1 — EventListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/EventListener.html), `@Order` trên event listener method.
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html), đồng bộ mặc định, executor và error handler.
- [Spring Framework — Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html), ví dụ `@Order` trên method `@EventListener`.

Khi thiết kế production, nên xem ordering là **độ ưu tiên xử lý callback** chứ không phải engine điều phối workflow có dependency, transaction và retry. Nếu B bắt buộc dựa trên kết quả thành công của A, hãy thể hiện quan hệ đó bằng API/service/workflow rõ ràng thay vì chỉ để `@Order(10)` đứng trước `@Order(20)`.
