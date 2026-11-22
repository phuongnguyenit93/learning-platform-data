# Component scan và listener tự động

Spring Framework cho phép đăng ký event listener bằng annotation `@EventListener`. Khi một object chứa method được Spring quản lý như một bean trong ApplicationContext, hạ tầng annotation của Spring có thể phát hiện method đó và đăng ký nó với cơ chế dispatch event. Nhờ vậy, service chỉ cần publish event; nó không phải tự tìm hoặc gọi từng listener.

Để cơ chế này hoạt động, cần phân biệt hai bước:

1. **Bean discovery:** Spring tìm và tạo bean chứa listener thông qua component scan, `@Bean`, `@Import` hoặc một cơ chế đăng ký bean khác.
2. **Listener method registration:** Spring phát hiện các method `@EventListener` trên bean đã quản lý và tạo adapter để chúng nhận event.

Component scan không tự biến mọi class có `@EventListener` thành bean. Annotation trên method chỉ được xử lý khi object chứa method đã nằm trong ApplicationContext thích hợp.

## 1. Một listener cần được đăng ký thành bean

Ví dụ:

~~~java
@Component
class ShipmentListener {
    @EventListener
    public void onShipmentCreated(ShipmentCreated event) {
        System.out.println("Shipment created: " + event.shipmentId());
    }
}
~~~

Hai annotation có vai trò khác nhau:

- `@Component` đánh dấu class là ứng viên bean để component scan phát hiện.
- `@EventListener` đánh dấu method là handler của event.

Tham số `ShipmentCreated` cho Spring biết kiểu event method cần nhận. Khi ứng dụng publish một object tương thích với kiểu này, Spring có thể gọi method.

Nếu chỉ có `@EventListener` mà class không được đăng ký thành bean, Spring không tự tạo instance cho class đó. Tương tự, một object được tạo bằng `new` bên ngoài container không tự trở thành listener chỉ vì method có annotation.

~~~java
// Object này nằm ngoài ApplicationContext.
ShipmentListener listener = new ShipmentListener();
~~~

Muốn method được Spring quản lý, hãy đưa object vào container bằng component scan, khai báo `@Bean`, import cấu hình hoặc dùng một cơ chế đăng ký bean phù hợp.

## 2. Phạm vi quét mặc định của @SpringBootApplication

Trong Spring Boot, `@SpringBootApplication` bao gồm chức năng component scan. Khi không chỉ định package, phạm vi quét bắt đầu từ package chứa class application và đi xuống các package con.

Ví dụ:

~~~text
com.acme.store
├── StoreApplication.java
├── order
│   ├── OrderService.java
│   └── OrderPlaced.java
├── listener
│   └── OrderPlacedListener.java
└── audit
    └── OrderAuditListener.java
~~~

Nếu `StoreApplication` nằm trong `com.acme.store`, các bean trong `com.acme.store.order`, `com.acme.store.listener` và `com.acme.store.audit` thuộc phạm vi quét mặc định.

Đặt class khởi động ở package gốc của ứng dụng thường giúp cấu trúc dễ hiểu. Nếu class application nằm trong `com.acme.store.bootstrap`, các package ngang hàng như `com.acme.store.listener` có thể nằm ngoài phạm vi quét mặc định.

Có thể chỉ định package scan:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.acme.store",
        "com.acme.shared.events"
})
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

Hoặc cấu hình bằng `@ComponentScan`:

~~~java
@Configuration
@ComponentScan(basePackages = {
        "com.acme.store",
        "com.acme.shared.events"
})
class StoreComponentConfiguration {}
~~~

Với codebase lớn, có thể dùng `basePackageClasses` để tránh tên package dạng chuỗi:

~~~java
@Configuration
@ComponentScan(basePackageClasses = {
        StoreApplication.class,
        SharedEventListenersMarker.class
})
class StoreComponentConfiguration {}
~~~

Mỗi class marker đại diện cho package cần quét. Cách này giúp refactor package an toàn hơn vì IDE và compiler có thể theo dõi tham chiếu class.

Component scan còn hỗ trợ include/exclude filters. Vì vậy, class nằm trong package được quét vẫn có thể bị loại bởi filter hoặc điều kiện đăng ký bean.

## 3. Những stereotype thường dùng cho listener

Các annotation stereotype giúp Spring nhận diện class là ứng viên component:

| Annotation | Vai trò thường gặp |
|---|---|
| `@Component` | Bean dùng chung |
| `@Service` | Bean chứa logic nghiệp vụ |
| `@Repository` | Bean truy cập dữ liệu |
| `@Controller` | Bean xử lý Spring MVC |
| `@RestController` | Controller trả response body |
| `@Configuration` | Bean cấu hình, thường khai báo bean khác qua `@Bean` |

Các annotation như `@Service`, `@Repository`, `@Controller` và `@Configuration` có quan hệ meta-annotation với `@Component`, nên được component scan mặc định nhận diện.

Listener thường dùng `@Component` hoặc `@Service`, tùy trách nhiệm:

~~~java
record OrderPlaced(String orderId) {}

@Service
class OrderAuditListener {
    @EventListener
    public void record(OrderPlaced event) {
        System.out.println("Audit order: " + event.orderId());
    }
}
~~~

Không cần thêm nhiều stereotype cho một listener. Điều quan trọng là class được đăng ký thành bean và method được đánh dấu đúng.

## 4. Đăng ký listener qua @Bean

Component scan không phải cách duy nhất tạo bean. Một method `@Bean` trong class cấu hình cũng có thể đăng ký listener:

~~~java
record ShipmentCreated(String shipmentId) {}

@Configuration
class EventListenerConfiguration {
    @Bean
    ShipmentListener shipmentListener() {
        return new ShipmentListener();
    }
}

class ShipmentListener {
    @EventListener
    public void onShipmentCreated(ShipmentCreated event) {
        System.out.println("Shipment created: " + event.shipmentId());
    }
}
~~~

Trong ví dụ này, `ShipmentListener` không cần `@Component`, vì phương thức `shipmentListener()` đã đưa instance vào ApplicationContext. Spring vẫn có thể phát hiện method `@EventListener` trên bean đó.

Cách khai báo này phù hợp khi:

- Listener thuộc thư viện bên ngoài và không thể thêm stereotype vào source.
- Muốn tự kiểm soát constructor hoặc cách khởi tạo listener.
- Bean chỉ được tạo theo profile hoặc điều kiện cấu hình.
- Muốn gom cấu hình tích hợp của một module vào class cấu hình riêng.

Class cấu hình cũng phải được Spring đăng ký. Có thể để component scan tìm thấy nó hoặc import tường minh:

~~~java
@Configuration
@Import(EventListenerConfiguration.class)
class ApplicationConfiguration {}
~~~

Nếu `EventListenerConfiguration` không được scan, import hoặc đăng ký theo cách khác, các method `@Bean` bên trong sẽ không được xử lý.

## 5. Spring tự đăng ký method @EventListener ra sao?

Khi annotation configuration infrastructure hoạt động, Spring dùng `EventListenerMethodProcessor` để phát hiện method có `@EventListener` trên các bean do container quản lý. Processor làm việc trong lifecycle của ApplicationContext sau khi các singleton bean đã được khởi tạo.

Ở mức khái niệm, quy trình gồm:

1. Spring đọc cấu hình và tạo bean definitions từ component scan, `@Bean`, `@Import` và các nguồn đăng ký khác.
2. ApplicationContext tạo các bean theo lifecycle của container.
3. `EventListenerMethodProcessor` kiểm tra các bean và tìm method có `@EventListener`.
4. Spring dùng `EventListenerFactory` thích hợp để tạo adapter cho method. Adapter thông dụng là `ApplicationListenerMethodAdapter`.
5. Adapter được đăng ký vào cơ chế event của ApplicationContext để nhận event phù hợp.
6. Khi publisher phát event, `ApplicationEventMulticaster` dispatch đến các listener đã đăng ký.

Nhờ cơ chế này, ứng dụng không cần tự viết reflection để quét method hoặc tự gọi `addApplicationListener` cho từng method annotation.

Một bean có thể có nhiều method `@EventListener`; mỗi method là một handler riêng. Một method cũng có thể nhận nhiều kiểu event bằng thuộc tính `classes` của annotation, nếu chữ ký method phù hợp với cách khai báo đó.

Điểm cần nhớ: processor làm việc trên bean của container. Annotation đặt trên một class không được quản lý sẽ không đủ để Spring đăng ký listener.

## 6. Ví dụ chạy được: component scan tự tìm listener

Ví dụ sau dùng Java 17+ và Spring Boot. Các class nằm trong cùng package `com.example.events`; class khởi động ở package này nên component scan mặc định tìm thấy service và listener.

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class EventScanApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventScanApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> orderService.place("ORD-42");
    }
}

record OrderPlaced(String orderId) {}

@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void place(String orderId) {
        publisher.publishEvent(new OrderPlaced(orderId));
        System.out.println("Publisher returned");
    }
}

@Component
class OrderPlacedListener {
    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Listener received: " + event.orderId());
    }
}
~~~

Các dòng output do ví dụ tạo ra:

~~~text
Listener received: ORD-42
Publisher returned
~~~

Giải thích:

1. Spring Boot khởi tạo ApplicationContext và component scan package `com.example.events`.
2. `OrderService` được tạo vì có `@Service`.
3. `OrderPlacedListener` được tạo vì có `@Component`.
4. Spring phát hiện method `handle` và đăng ký adapter nhận `OrderPlaced`.
5. Service chỉ gọi `ApplicationEventPublisher.publishEvent`; service không cần biết listener nào đang tồn tại.
6. Với `SimpleApplicationEventMulticaster` mặc định và listener đồng bộ, listener xử lý xong trước khi `publishEvent` trả về.

Log khởi động của Spring Boot không được liệt kê. Project cần dependency Spring Boot có hỗ trợ context, ví dụ `spring-boot-starter`. Có thể chạy bằng Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ví dụ minh họa việc đăng ký tự động trong một ApplicationContext. Nếu chuyển listener sang package khác ngoài phạm vi scan, cần điều chỉnh package scan hoặc đăng ký bean bằng cách khác.

## 7. Spring chọn listener theo kiểu event

Kiểu tham số method xác định event mà listener nhận. Ví dụ:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

record OrderPlaced(String orderId) {}

@Component
class OrderListeners {
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("Order: " + event.orderId());
    }

    @EventListener
    public void onApplicationEvent(ApplicationEvent event) {
        System.out.println("Application event: " + event.getClass().getSimpleName());
    }
}
~~~

Một listener có thể nhận kiểu cha hoặc interface tương thích. Với event là object Java thông thường, Spring xét kiểu object được publish và kiểu tham số method.

Có thể giới hạn listener bằng điều kiện SpEL:

~~~java
import java.math.BigDecimal;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

record PaymentCompleted(String paymentId, BigDecimal amount) {}

@Component
class LargePaymentListener {
    @EventListener(condition = "#root.event.amount().compareTo(T(java.math.BigDecimal).valueOf(1000000)) >= 0")
    public void onLargePayment(PaymentCompleted event) {
        System.out.println("Large payment: " + event.paymentId());
    }
}
~~~

Điều kiện chỉ cho method chạy khi biểu thức trả về true. Ví dụ giả định `PaymentCompleted` là record có accessor `amount()` trả về `BigDecimal`.

Nếu method trả về một object event khác null, Spring có thể publish giá trị trả về đó như event dẫn xuất. Nếu trả về một collection, từng phần tử được publish riêng. Với listener bất đồng bộ, không dựa vào return value để phát event; hãy dùng `ApplicationEventPublisher` tường minh.

## 8. Thứ tự listener và các cơ chế bổ sung

Có thể dùng `@Order` để sắp thứ tự các listener cùng nhận một event:

~~~java
@Component
class OrderedOrderListeners {
    @EventListener
    @Order(1)
    public void first(OrderPlaced event) {
        System.out.println("First listener");
    }

    @EventListener
    @Order(2)
    public void second(OrderPlaced event) {
        System.out.println("Second listener");
    }
}
~~~

Giá trị order nhỏ hơn được ưu tiên trước trong cùng lần dispatch. Không dựa vào thứ tự component scan hoặc thứ tự file để quyết định thứ tự nghiệp vụ.

Một số cơ chế khác có thể dùng cùng listener:

- `@Async` kết hợp `@EnableAsync` để chạy listener trên executor. Publisher không chờ listener async hoàn tất; cần cấu hình executor và xử lý exception riêng.
- `@TransactionalEventListener` để gắn thời điểm xử lý với transaction, chẳng hạn `AFTER_COMMIT`.
- `condition` để lọc event theo dữ liệu payload.
- `@Profile` hoặc `@Conditional` để quyết định bean listener có tồn tại trong context hay không.

Các cơ chế này không thay thế bước đăng ký bean. Listener vẫn cần được đưa vào ApplicationContext để annotation method được phát hiện.

## 9. Phân biệt @EventListener và ApplicationListener

Spring hỗ trợ cả listener khai báo bằng annotation lẫn listener triển khai interface:

| Tiêu chí | `@EventListener` | `ApplicationListener<E>` |
|---|---|---|
| Khai báo | Annotation trên method | Class triển khai interface |
| Nhiều handler trong một class | Có thể khai báo nhiều method | Thường tách thành các listener riêng hoặc tự phân nhánh |
| Điều kiện SpEL | Có thuộc tính `condition` | Không có thuộc tính tương đương tích hợp |
| Cách container nhận diện | Annotation processor tạo adapter | Bean implement interface được nhận diện là listener |
| Phù hợp | Handler gọn, muốn khai báo ngay trong bean | Listener tường minh theo kiểu interface |

Ví dụ:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedApplicationListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("Interface listener: " + event.orderId());
    }
}
~~~

Không nên đăng ký hai cách cho cùng một tác vụ nếu không có chủ đích. Một bean vừa triển khai `ApplicationListener<OrderPlaced>` vừa có method `@EventListener` nhận `OrderPlaced` có thể xử lý cùng event qua hai đường khác nhau.

## 10. Vòng đời context và thời điểm publish

Spring phát hiện method listener trong quá trình khởi tạo ApplicationContext. Vì vậy, không nên phát event từ constructor hoặc `@PostConstruct` với giả định mọi listener đều đã sẵn sàng.

Nếu công việc cần chạy sau khi context đã refresh, có thể lắng nghe `ContextRefreshedEvent`. Trong Spring Boot, `ApplicationReadyEvent` thường phù hợp khi logic cần đợi ứng dụng hoàn tất các bước khởi động chính:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ApplicationStartupListener {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

`ApplicationReadyEvent` là event của Spring Boot, không phải class lõi của Spring Framework. Cần import đúng package `org.springframework.boot.context.event.ApplicationReadyEvent`.

Không dùng startup event để thay thế dependency injection. Nếu bean cần một dependency khác, hãy khai báo qua constructor. Startup event chỉ phù hợp cho công việc có ý nghĩa ở mốc context hoặc ứng dụng đã sẵn sàng.

## 11. Chẩn đoán listener không được gọi

Khi publisher phát event nhưng listener không chạy, kiểm tra lần lượt:

1. **Package không được quét:** listener nằm ngoài package gốc của `@SpringBootApplication`. Điều chỉnh `scanBasePackages`, `@ComponentScan` hoặc dùng `@Import`.
2. **Thiếu bean registration:** class không có stereotype và không được khai báo bằng `@Bean` hay cơ chế đăng ký bean khác.
3. **Bean bị điều kiện loại bỏ:** `@Profile`, `@Conditional` hoặc scan filter không cho bean tồn tại trong môi trường hiện tại.
4. **Object nằm ngoài container:** class được tạo bằng `new` và không được đăng ký làm bean.
5. **Sai kiểu event:** tham số method không tương thích với object được publish.
6. **SpEL condition không thỏa:** biểu thức `condition` trả về false.
7. **Publish quá sớm:** event được phát trước khi annotation listener được phát hiện và đăng ký đầy đủ.
8. **Nhầm ApplicationContext:** publisher và listener thuộc các context khác nhau.
9. **Listener chạy nhưng ném exception:** kiểm tra log và stack trace; phân biệt dispatch đồng bộ với listener async.

Có thể kiểm tra bean trong context bằng cách inject `ApplicationContext` và truy vấn theo type:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

// Giả định OrderPlacedListener đã được khai báo trong ứng dụng.
@Component
class ListenerDiagnostics {
    ListenerDiagnostics(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(OrderPlacedListener.class);
        System.out.println("OrderPlacedListener beans: " + names.length);
    }
}
~~~

Nếu số bean bằng 0, kiểm tra package scan và điều kiện đăng ký trước khi kiểm tra event dispatch.

## 12. Tránh đăng ký cùng listener hai lần

Một class có thể bị tạo thành nhiều bean nếu vừa được component scan vừa được khai báo lại bằng `@Bean`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId) {}

@Component
class OrderPlacedListener {
    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Handled: " + event.orderId());
    }
}

@Configuration
class DuplicateListenerConfiguration {
    @Bean
    OrderPlacedListener anotherOrderPlacedListener() {
        return new OrderPlacedListener();
    }
}
~~~

Nếu cả hai bean đều tồn tại, method listener có thể được đăng ký trên cả hai instance và cùng xử lý một event. Hệ quả có thể là gửi email hai lần, ghi audit trùng hoặc cập nhật số liệu lặp.

Cách phòng tránh:

- Chọn một nguồn tạo bean cho mỗi listener.
- Không khai báo lại một class đã được scan nếu không chủ đích tạo instance thứ hai.
- Không gọi đăng ký thủ công thêm lần nữa khi annotation infrastructure đã tự đăng ký method.
- Dùng tên bean rõ ràng và kiểm tra số bean theo type khi nghi ngờ.
- Với tác động nghiệp vụ quan trọng, thiết kế idempotency để việc xử lý lặp không gây sai dữ liệu.

## 13. Checklist cấu hình

- [ ] Listener class đã được đăng ký thành bean trong ApplicationContext cần nhận event?
- [ ] Package listener thuộc phạm vi scan hoặc được import/khai báo bằng `@Bean`?
- [ ] Class application được đặt ở package gốc hợp lý?
- [ ] Method có `@EventListener` và khai báo kiểu event phù hợp?
- [ ] Có `condition`, `@Profile`, `@Conditional` hoặc scan filter làm listener không hoạt động?
- [ ] Event có được publish sau khi listener sẵn sàng?
- [ ] Có tạo trùng bean listener qua component scan và `@Bean`?
- [ ] Có đăng ký cùng tác vụ bằng cả `@EventListener` và `ApplicationListener`?
- [ ] Nếu dùng async hoặc transactional listener, đã cấu hình executor/transaction và xử lý lỗi?
- [ ] Đã kiểm tra đúng ApplicationContext và log thực tế?

Component scan tìm các class đủ điều kiện và đăng ký chúng thành bean. Hạ tầng `@EventListener` phát hiện method trên các bean đó và kết nối chúng với event multicaster. Khi tách rõ bean discovery khỏi listener method registration, ứng dụng có thể tổ chức listener theo module mà vẫn kiểm soát được phạm vi quét, điều kiện tạo bean và nguy cơ đăng ký trùng.
